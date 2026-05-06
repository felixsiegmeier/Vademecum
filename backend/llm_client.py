import asyncio
import base64
import io
import logging
import os
from typing import TYPE_CHECKING, AsyncGenerator

from openai import APIStatusError, AsyncOpenAI

if TYPE_CHECKING:
    pass  # Nur für Type-Checker-Zwecke importiert

logger = logging.getLogger(__name__)

# Unterstützte LLM-Backends — über Env-Variable LLM_BACKEND auswählbar.
# Beide nutzen das OpenAI-kompatible API-Format, daher ein einziger Client.
_BACKENDS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-3-flash-preview",
    },
    "lmstudio": {
        "base_url": "http://localhost:1234/v1",
        "api_key_env": None,  # LM Studio doesn't require a real key
        "model": "qwen/qwen3-14b",
    },
}


class LLMClient:
    def __init__(self):
        backend_name = os.environ.get("LLM_BACKEND", "gemini")
        backend = _BACKENDS.get(backend_name)
        if backend is None:
            raise ValueError(f"Unbekanntes LLM_BACKEND: '{backend_name}'. Erlaubt: {list(_BACKENDS)}")

        if backend["api_key_env"]:
            api_key = os.environ.get(backend["api_key_env"])
            if not api_key:
                raise ValueError(f"{backend['api_key_env']} not set")
        else:
            api_key = "lm-studio"  # LM Studio ignores the key but the client requires one

        self._client = AsyncOpenAI(api_key=api_key, base_url=backend["base_url"])
        self.model: str = backend["model"]

    @property
    def client(self) -> AsyncOpenAI:
        return self._client

    async def chat_completion(self, messages: list[dict], thinking_budget: int | None = None, timeout_s: int = 90, **kwargs):
        # Thinking-Budget: None = kein Thinking (Budget 0), sonst Gemini-spezifische Config.
        budget = thinking_budget if thinking_budget is not None else 0
        caller_extra = kwargs.pop("extra_body", {})
        google_config = {"thinking_config": {"thinking_budget": budget}}
        kwargs["extra_body"] = {"extra_body": {**{"google": google_config}, **caller_extra}}
        logger.debug(
            "[LLM-CALL] model=%s tools=%s parallel_tool_calls=%s extra_body=%s",
            self.model,
            [t["function"]["name"] for t in kwargs.get("tools") or []],
            kwargs.get("parallel_tool_calls"),
            kwargs.get("extra_body"),
        )
        try:
            return await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,  # type: ignore[arg-type]
                    **kwargs,
                ),
                timeout=timeout_s,
            )
        except Exception as e:
            logger.error("[LLM-FAIL] %s: %s", type(e).__name__, e)
            raise

    async def stream_chat(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """Streamt Antwort-Tokens für den allgemeinen Chat (Server-Sent Events)."""
        response = await self.chat_completion(messages, stream=True)
        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                yield content


async def call_with_pdf_fallback(
    client: "LLMClient",
    file_bytes: bytes,
    mime_type: str,
    system_prompt: str,
    tools: list[dict],
    **call_kwargs,
) -> object:
    """Ruft das LLM mit File-Parts. Bei APIStatusError + PDF: Retry mit Image-Konversion.

    call_kwargs werden an client.chat_completion durchgereicht
    (z.B. max_tokens=8192, temperature=0).
    """
    call_kwargs.pop("model", None)  # chat_completion nutzt client.model intern

    parts_a = file_to_content_parts(file_bytes, mime_type)
    messages_a = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": parts_a},
    ]
    try:
        return await client.chat_completion(messages=messages_a, tools=tools, **call_kwargs)
    except APIStatusError:
        if mime_type != "application/pdf":
            raise
        parts_b = convert_pdf_to_image_parts(file_bytes)
        messages_b = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": parts_b},
        ]
        return await client.chat_completion(messages=messages_b, tools=tools, **call_kwargs)


def file_to_content_parts(file_bytes: bytes, mime_type: str) -> list[dict]:
    """Wandelt Datei-Bytes in ein OpenAI-kompatibles Content-Part um (base64 data-URL).

    Funktioniert für PDFs (direkte PDF-Unterstützung des Modells vorausgesetzt)
    und Bilder gleichermaßen.
    """
    b64 = base64.b64encode(file_bytes).decode("ascii")
    return [{"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}}]


def convert_pdf_to_image_parts(pdf_bytes: bytes, dpi: int = 144) -> list[dict]:
    """Plan B: PDF → PNG-Seiten via pypdfium2, falls das Modell kein PDF direkt liest.

    Jede Seite wird separat als base64-PNG ins Content-Array aufgenommen.
    144 DPI ist ein guter Kompromiss zwischen Lesbarkeit und Token-Verbrauch.
    """
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    parts = []
    scale = dpi / 72  # pypdfium2 arbeitet mit 72 DPI als Basis
    for i in range(len(pdf)):
        page = pdf[i]
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
    return parts
