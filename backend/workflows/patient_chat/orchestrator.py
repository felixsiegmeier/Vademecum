import json
import logging
from datetime import date
from pathlib import Path
from string import Template
from typing import Optional

import yaml

from workflows.document_extraction.tool_loop import Proposal, group_proposals
from tools.patient_tools import TOOL_SCHEMAS
from models.patient import Patient
from utils.prompts import get_prompt

logger = logging.getLogger(__name__)

# Inputs länger als dieser Cutoff werden über die 2-Pass-Pipeline geleitet (wie Upload).
# Kürzere Inputs → Single-Pass mit direktem LLM-Routing (Tool-Call oder Text-Antwort).
CHAT_2PASS_CUTOFF = 2000

_PROMPTS_DIR = Path(__file__).parent
_TEMPLATE_CACHE: Template | None = None


def _get_template() -> Template:
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is None:
        # .rstrip("\n") mirrors the original \-escaped triple-quote (no trailing newline)
        _TEMPLATE_CACHE = Template(get_prompt("system_prompt.md", _PROMPTS_DIR).rstrip("\n"))
    return _TEMPLATE_CACHE



def build_system_prompt(patient: Patient, today: date) -> str:
    """Baut den vollständigen System-Prompt für den Patienten-Chat."""
    full_yaml = yaml.safe_dump(
        patient.model_dump(exclude_none=True, mode="json"),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=100,
    )
    geburtsdatum = (
        patient.stammdaten.geburtsdatum.strftime("%d.%m.%Y")
        if patient.stammdaten.geburtsdatum
        else "—"
    )
    return _get_template().substitute(
        today=today.strftime("%d.%m.%Y"),
        name=patient.stammdaten.name,
        geburtsdatum=geburtsdatum,
        bettplatz=patient.stammdaten.bettplatz or "—",
        full_yaml=full_yaml,
    )


async def run_single_pass_chat(
    llm,
    patient: Patient,
    user_text: str,
    today: date,
) -> tuple[list[Proposal], Optional[str]]:
    """Single-Pass Chat: LLM entscheidet selbst ob Tool-Call oder Text-Antwort.

    Returns (proposals, reply):
    - Tool-Calls vom LLM → (proposals, None)
    - Text-Antwort vom LLM → ([], reply_text)
    - Weder noch → ([], None)
    """
    system = build_system_prompt(patient, today)
    response = await llm.chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        tools=TOOL_SCHEMAS,
        tool_choice="auto",
        temperature=0,
        max_tokens=2048,
    )
    msg = response.choices[0].message

    if msg.tool_calls:
        calls: list[dict] = []
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                logger.warning("Malformed JSON args für Tool %s, wird übersprungen", tc.function.name)
                continue
            calls.append({"tool": tc.function.name, "args": args})
        proposals = group_proposals([calls]) if calls else []
        return proposals, None
    else:
        reply = (msg.content or "").strip() or None
        return [], reply
