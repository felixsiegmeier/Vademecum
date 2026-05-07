"""Einzel-LLM-Call zur Stammdaten-Extraktion (JSON-Mode, kein Tool-Calling)."""
import json
import logging
from pathlib import Path

from openai import APIStatusError

from llm_client import LLMClient, convert_pdf_to_image_parts, file_to_content_parts
from utils.prompts import get_prompt
from .schema import StammdatenExtractResult  # noqa: F401

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent


async def extract_stammdaten(
    client: LLMClient,
    file_bytes: bytes,
    mime_type: str,
) -> StammdatenExtractResult:
    """
    Extrahiert Patientenstammdaten aus einem Dokument (PDF oder Bild).
    Single-LLM-Call mit JSON-Mode. Unbekannte Felder sind None.
    Bei nicht-parsebarer Antwort wird ein leeres Ergebnis zurückgegeben.
    """
    system_prompt = get_prompt("prompt.md", _PROMPTS_DIR)
    parts = file_to_content_parts(file_bytes, mime_type)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": parts},
    ]

    try:
        response = await client.chat_completion(
            messages,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=512,
        )
    except APIStatusError:
        if mime_type != "application/pdf":
            raise
        # PDF-Fallback: Seiten als PNG-Bilder konvertieren
        img_parts = convert_pdf_to_image_parts(file_bytes)
        messages_img = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": img_parts},
        ]
        response = await client.chat_completion(
            messages_img,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=512,
        )

    raw = (response.choices[0].message.content or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[extract_stammdaten] Modell-Antwort kein valides JSON: %s", raw[:200])
        return StammdatenExtractResult()

    try:
        return StammdatenExtractResult.model_validate(data)
    except Exception:
        logger.warning("[extract_stammdaten] Pydantic-Validation fehlgeschlagen für: %s", data)
        return StammdatenExtractResult()
