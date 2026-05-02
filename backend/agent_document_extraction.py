from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from openai import APIStatusError

from agent_extraction_core import (
    MAX_ITERATIONS_BLOCK_1,
    THINKING_BUDGET_BLOCK_1,
    THINKING_BUDGET_BLOCK_2,
    Proposal,
    group_proposals,
    run_pass,
)
from agent_tools import (
    ADD_VERLAUFSEINTRAG_SCHEMA,
    DELETE_ENTRY_SCHEMA,
    TOOL_SCHEMAS,
)
from llm_client import LLMClient, convert_pdf_to_image_parts, file_to_content_parts
from models.patient import Patient

# Pass 1: alle Tools außer add_verlaufseintrag
_PASS1_TOOLS = [s for s in TOOL_SCHEMAS if s["function"]["name"] != "add_verlaufseintrag"]

# Pass 2: nur add_verlaufseintrag + delete_entry (für Korrekturen des letzten Eintrags)
_PASS2_TOOLS = [ADD_VERLAUFSEINTRAG_SCHEMA, DELETE_ENTRY_SCHEMA]

_BLOCK1_PROMPT_CACHE: str | None = None
_BLOCK2_PROMPT_CACHE: str | None = None


def _load_block1_prompt() -> str:
    global _BLOCK1_PROMPT_CACHE
    if _BLOCK1_PROMPT_CACHE is None:
        path = Path(__file__).parent / "prompts" / "extraction_block1.txt"
        _BLOCK1_PROMPT_CACHE = path.read_text(encoding="utf-8")
    return _BLOCK1_PROMPT_CACHE


def _load_block2_prompt() -> str:
    global _BLOCK2_PROMPT_CACHE
    if _BLOCK2_PROMPT_CACHE is None:
        path = Path(__file__).parent / "prompts" / "extraction_block2.txt"
        _BLOCK2_PROMPT_CACHE = path.read_text(encoding="utf-8")
    return _BLOCK2_PROMPT_CACHE


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

    return _load_block1_prompt().replace("{HEUTE}", today).replace("{STATE_BLOCK}", state_block)


def _build_block2_system(patient: Patient | None) -> str:
    """System-Prompt für Pass 2 (chronologisch) mit letztem Verlaufseintrag."""
    today = date.today().isoformat()

    if patient is not None and patient.verlaufseintraege:
        last = sorted(patient.verlaufseintraege, key=lambda e: e.datum, reverse=True)[0]
        verlauf_block = (
            f'<letzter_verlaufseintrag id="{last.id}" datum="{last.datum.isoformat()}">\n'
            f"{last.text}\n"
            f"</letzter_verlaufseintrag>"
        )
    else:
        verlauf_block = "<letzter_verlaufseintrag>keiner</letzter_verlaufseintrag>"

    return _load_block2_prompt().replace("{HEUTE}", today).replace("{VERLAUF_BLOCK}", verlauf_block)


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
        )

    # Pass 2: chronologisch (Verlaufseinträge)
    pass2_iters = await run_pass(
        llm=llm,
        system_prompt=block2_system,
        user_messages=user_messages,
        tools=_PASS2_TOOLS,
        thinking_budget=THINKING_BUDGET_BLOCK_2,
    )

    return group_proposals(pass1_iters + pass2_iters)
