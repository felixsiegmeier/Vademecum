"""Meilenstein-Generierung — Einzel-LLM-Call mit Regel-Injection."""
import re
import logging
from datetime import date
from pathlib import Path

import yaml

from storage import learning_storage
from llm_client import LLMClient
from models.patient import Patient
from utils.prompts import get_prompt

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent
_PROMPT_CACHE: str | None = None

_SECTION_ORDER = [
    "Operationen & Prozeduren",
    "Behandlungsdiagnosen",
    "Relevante Nebendiagnosen",
    "Kardiale Funktion",
    "Antikoagulation",
    "Antimikrobielle Therapie",
    "Befunde",
    "Therapieziel / Patientenwille",
]


def _load_prompt() -> str:
    global _PROMPT_CACHE
    if _PROMPT_CACHE is None:
        _PROMPT_CACHE = get_prompt("prompt.md", _PROMPTS_DIR)
    return _PROMPT_CACHE


def _build_system_prompt(rules: list) -> str:
    base = _load_prompt()
    if not rules:
        return base

    sections: dict[str, list[str]] = {}
    for rule in rules:
        sections.setdefault(rule.section, []).append(rule.rule_text)

    lines: list[str] = [
        "<gelernte_regeln>",
        "",
        "Die folgenden Regeln wurden aus früheren manuellen Korrekturen am Meilenstein "
        "abgeleitet. Beachte sie beim Generieren der entsprechenden Sektion. "
        "Eine Regel überschreibt im Konfliktfall die allgemeine Klausel-Logik.",
    ]
    for section in _SECTION_ORDER:
        if section not in sections:
            continue
        lines.append("")
        lines.append(f"## {section}")
        lines.append("")
        for rule_text in sections[section]:
            lines.append(f"- {rule_text}")
    lines.append("")
    lines.append("</gelernte_regeln>")

    return base + "\n\n" + "\n".join(lines)


async def generate(
    patient: Patient,
    llm: LLMClient,
    *,
    current_meilenstein: str = "",
    user_id: str = "default",
) -> str:
    """Generiert Meilenstein aus Patient-YAML. Gibt Markdown-Content zurück."""
    rules = learning_storage.load_rules(user_id=user_id, domain="meilenstein")
    system_prompt = _build_system_prompt(rules)

    patient_yaml = yaml.safe_dump(
        patient.model_dump(exclude_none=True, mode="json"),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=100,
    )
    today_iso = date.today().isoformat()
    user_blocks = [
        f"<patient_yaml>\n{patient_yaml}\n</patient_yaml>",
        f"<generierungsdatum>{today_iso}</generierungsdatum>",
    ]
    if current_meilenstein.strip():
        user_blocks.append(
            f"<aktueller_meilenstein>\n{current_meilenstein}\n</aktueller_meilenstein>"
        )
    user_msg = "\n\n".join(user_blocks)

    response = await llm.chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
        max_tokens=4096,
    )

    raw = (response.choices[0].message.content or "").strip()
    m = re.search(r"```[^\n]*\n(.*?)\n```", raw, re.DOTALL)
    md_content = m.group(1).strip() if m else raw

    learning_storage.save_last_output(patient.stammdaten.id, md_content, domain="meilenstein")
    return md_content
