import asyncio
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Literal

import yaml
from openai import APIConnectionError, APIStatusError, RateLimitError

from workflows.document_extraction.tool_loop import (
    MAX_ITERATIONS_BLOCK_1,
    MAX_TOTAL_TOKENS_BLOCK_1,
    MAX_TOTAL_TOKENS_BLOCK_2,
    THINKING_BUDGET_BLOCK_1,
    THINKING_BUDGET_BLOCK_2,
    Proposal,
    group_proposals,
    run_pass,
    run_pass_streaming,
)
from tools.patient_tools import (
    ADD_VERLAUFSEINTRAG_SCHEMA,
    DELETE_ENTRY_SCHEMA,
    TOOL_SCHEMAS,
)
from llm_client import LLMClient, convert_pdf_to_image_parts, file_to_content_parts
from models.patient import Patient
from utils.prompts import get_prompt

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Pass 1: alle Tools außer add_verlaufseintrag
_PASS1_TOOLS = [s for s in TOOL_SCHEMAS if s["function"]["name"] != "add_verlaufseintrag"]

# Pass 2: nur add_verlaufseintrag + delete_entry (für Korrekturen des letzten Eintrags)
_PASS2_TOOLS = [ADD_VERLAUFSEINTRAG_SCHEMA, DELETE_ENTRY_SCHEMA]


def _build_block1_system(patient: Patient | None) -> str:
    """System-Prompt für Pass 1 (themen-quer) mit aktuellem Patientenstand."""
    today = date.today().isoformat()

    if patient is not None:
        state_yaml = yaml.dump(
            patient.model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        )
        state_block = f"<aktueller_stand>\n{state_yaml}</aktueller_stand>"
    else:
        state_block = "<aktueller_stand>leer</aktueller_stand>"

    return get_prompt("extraction_block1.txt", _PROMPTS_DIR).replace("{HEUTE}", today).replace("{STATE_BLOCK}", state_block)


_VERLAUF_PREVIEW_LEN = 250


def _compact_verlauf_overview(patient: Patient | None) -> str:
    """Kompakte Übersicht aller existierenden Verlaufseinträge für Block-2-Kontext.

    Format pro Eintrag: [YYYY-MM-DD] (id=...) Preview (max. 250 Zeichen)
    """
    if patient is None or not patient.verlaufseintraege:
        return "<existierende_verlaufseintraege>keine</existierende_verlaufseintraege>"
    sorted_entries = sorted(patient.verlaufseintraege, key=lambda e: e.datum)
    lines = []
    for e in sorted_entries:
        preview = e.text[:_VERLAUF_PREVIEW_LEN] + ("…" if len(e.text) > _VERLAUF_PREVIEW_LEN else "")
        lines.append(f"[{e.datum.isoformat()}] (id={e.id}) {preview}")
    content = "\n".join(lines)
    return f"<existierende_verlaufseintraege>\n{content}\n</existierende_verlaufseintraege>"


def _build_block2_system(patient: Patient | None) -> str:
    """System-Prompt für Pass 2 (chronologisch) mit allen existierenden Verlaufseinträgen."""
    today = date.today().isoformat()
    verlauf_block = _compact_verlauf_overview(patient)
    return get_prompt("extraction_block2.txt", _PROMPTS_DIR).replace("{HEUTE}", today).replace("{VERLAUF_BLOCK}", verlauf_block)


async def extract_proposals(
    llm: LLMClient,
    patient: Patient | None,
    content: str | bytes,
    content_type: Literal["pdf", "image", "text"],
    image_mime_type: str = "image/jpeg",
) -> list[Proposal]:
    """2-Pass-Extraktion: Pass 1 (themen-quer) + Pass 2 (chronologisch).

    Bei PDF: versucht native PDF-Parts, fällt bei APIStatusError auf
    Image-Konversion zurück (gleiches Verhalten wie call_with_pdf_fallback).
    """
    if content_type == "text":
        user_messages = [{"role": "user", "content": content}]
    elif content_type == "pdf":
        assert isinstance(content, bytes)
        user_messages = [{"role": "user", "content": file_to_content_parts(content, "application/pdf")}]
    else:  # image
        assert isinstance(content, bytes)
        user_messages = [{"role": "user", "content": file_to_content_parts(content, image_mime_type)}]

    block1_system = _build_block1_system(patient)
    block2_system = _build_block2_system(patient)

    # Pass 1: themen-quer (Stammdaten, Diagnosen, Befunde, Therapien, Prozeduren)
    try:
        pass1_iters = await run_pass(
            llm=llm,
            system_prompt=block1_system,
            user_messages=user_messages,
            tools=_PASS1_TOOLS,
            thinking_budget=THINKING_BUDGET_BLOCK_1,
            max_iterations=MAX_ITERATIONS_BLOCK_1,
            max_total_tokens=MAX_TOTAL_TOKENS_BLOCK_1,
            pass_name="Block1",
        )
    except APIStatusError:
        if content_type != "pdf":
            raise
        # PDF-Fallback: Seiten als PNG-Bilder
        assert isinstance(content, bytes)
        user_messages = [{"role": "user", "content": convert_pdf_to_image_parts(content)}]
        pass1_iters = await run_pass(
            llm=llm,
            system_prompt=block1_system,
            user_messages=user_messages,
            tools=_PASS1_TOOLS,
            thinking_budget=THINKING_BUDGET_BLOCK_1,
            max_iterations=MAX_ITERATIONS_BLOCK_1,
            max_total_tokens=MAX_TOTAL_TOKENS_BLOCK_1,
            pass_name="Block1",
        )

    # Pass 2: chronologisch (Verlaufseinträge)
    pass2_iters = await run_pass(
        llm=llm,
        system_prompt=block2_system,
        user_messages=user_messages,
        tools=_PASS2_TOOLS,
        thinking_budget=THINKING_BUDGET_BLOCK_2,
        max_tokens=16384,
        max_total_tokens=MAX_TOTAL_TOKENS_BLOCK_2,
        pass_name="Block2",
    )

    return group_proposals(pass1_iters + pass2_iters)


async def extract_proposals_streaming(
    llm,
    patient,
    content: str | bytes,
    content_type: Literal["pdf", "image", "text"],
    image_mime_type: str = "image/jpeg",
    extra_context: str = "",
) -> AsyncGenerator[dict, None]:
    """2-Pass-Extraktion mit Live-Event-Stream (NDJSON über chunked HTTP).

    Yields in order: status → heartbeat → proposals (per block) → done.
    On error: yields an error event and returns immediately (no resume).

    Why NDJSON instead of SSE: this endpoint is POST (file upload). The browser's
    EventSource API only supports GET/HEAD, so SSE is not applicable here.
    """
    if content_type == "text":
        user_messages = [{"role": "user", "content": content}]
    elif content_type == "pdf":
        assert isinstance(content, bytes)
        user_messages = [{"role": "user", "content": file_to_content_parts(content, "application/pdf")}]
    else:  # image
        assert isinstance(content, bytes)
        user_messages = [{"role": "user", "content": file_to_content_parts(content, image_mime_type)}]

    if extra_context:
        user_messages.append({"role": "user", "content": f"Zusätzlicher Kontext vom Nutzer:\n{extra_context}"})

    block1_system = _build_block1_system(patient)
    block2_system = _build_block2_system(patient)
    total_proposals = 0

    def _ts() -> str:
        return datetime.now(timezone.utc).isoformat()

    yield {"type": "stream_opened", "ts": _ts()}

    # Pass 1: themen-quer — catch APIStatusError for PDF-fallback to images
    t0 = time.monotonic()
    yield {"type": "phase_start", "phase": "block1", "ts": _ts()}
    try:
        async for event in run_pass_streaming(
            llm=llm,
            system_prompt=block1_system,
            user_messages=user_messages,
            tools=_PASS1_TOOLS,
            thinking_budget=THINKING_BUDGET_BLOCK_1,
            phase="block1",
            max_iterations=MAX_ITERATIONS_BLOCK_1,
            max_total_tokens=MAX_TOTAL_TOKENS_BLOCK_1,
            pass_name="Block1",
        ):
            if event.get("type") == "error":
                yield event
                return
            yield event
            if event["type"] == "proposals":
                total_proposals += len(event["items"])
    except asyncio.TimeoutError:
        yield {
            "type": "error",
            "phase": "block1",
            "reason": "llm_timeout",
            "message": "LLM-Timeout in Block 1 (>90s) — bitte erneut hochladen",
            "retryable": True,
            "duration_s": round(time.monotonic() - t0, 1),
        }
        return
    except APIStatusError:
        if content_type != "pdf":
            yield {"type": "error", "message": "LLM API error in Block1", "retryable": False}
            return
        # PDF-Fallback: Seiten als PNG-Bilder
        assert isinstance(content, bytes)
        user_messages = [{"role": "user", "content": convert_pdf_to_image_parts(content)}]
        total_proposals = 0
        try:
            async for event in run_pass_streaming(
                llm=llm,
                system_prompt=block1_system,
                user_messages=user_messages,
                tools=_PASS1_TOOLS,
                thinking_budget=THINKING_BUDGET_BLOCK_1,
                phase="block1",
                max_iterations=MAX_ITERATIONS_BLOCK_1,
                max_total_tokens=MAX_TOTAL_TOKENS_BLOCK_1,
                pass_name="Block1-fallback",
            ):
                if event.get("type") == "error":
                    yield event
                    return
                yield event
                if event["type"] == "proposals":
                    total_proposals += len(event["items"])
        except asyncio.TimeoutError:
            yield {
                "type": "error",
                "phase": "block1",
                "reason": "llm_timeout",
                "message": "LLM-Timeout in Block 1 Fallback (>90s) — bitte erneut hochladen",
                "retryable": True,
                "duration_s": round(time.monotonic() - t0, 1),
            }
            return
        except (APIStatusError, RateLimitError, APIConnectionError) as e:
            yield {"type": "error", "message": str(e), "retryable": False}
            return
    except RateLimitError as e:
        yield {"type": "error", "message": f"Rate-Limit erreicht: {e}", "retryable": True}
        return
    except APIConnectionError as e:
        yield {"type": "error", "message": f"LLM nicht erreichbar: {e}", "retryable": True}
        return

    yield {"type": "phase_done", "phase": "block1", "duration_s": round(time.monotonic() - t0, 1), "ts": _ts()}

    # Pass 2: chronologisch
    t1 = time.monotonic()
    yield {"type": "phase_start", "phase": "block2", "ts": _ts()}
    try:
        async for event in run_pass_streaming(
            llm=llm,
            system_prompt=block2_system,
            user_messages=user_messages,
            tools=_PASS2_TOOLS,
            thinking_budget=THINKING_BUDGET_BLOCK_2,
            phase="block2",
            max_tokens=16384,
            max_total_tokens=MAX_TOTAL_TOKENS_BLOCK_2,
            pass_name="Block2",
        ):
            if event.get("type") == "error":
                yield event
                return
            yield event
            if event["type"] == "proposals":
                total_proposals += len(event["items"])
    except asyncio.TimeoutError:
        yield {
            "type": "error",
            "phase": "block2",
            "reason": "llm_timeout",
            "message": "LLM-Timeout in Block 2 (>90s) — bitte erneut hochladen",
            "retryable": True,
            "duration_s": round(time.monotonic() - t1, 1),
        }
        return
    except (APIStatusError, RateLimitError, APIConnectionError) as e:
        yield {"type": "error", "message": str(e), "retryable": False}
        return

    yield {"type": "phase_done", "phase": "block2", "duration_s": round(time.monotonic() - t1, 1), "ts": _ts()}

    yield {"type": "done", "total_proposals": total_proposals, "auto_skipped": total_proposals == 0}
