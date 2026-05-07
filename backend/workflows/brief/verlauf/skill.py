import logging
import re
import sys
from pathlib import Path
from typing import Optional

import yaml

from llm_client import LLMClient
from models.patient import Patient
from utils.prompts import get_prompt

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent


def _to_yaml(patient: Patient) -> str:
    return yaml.safe_dump(
        patient.model_dump(exclude_none=True, mode="json"),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=100,
    )


def _inject_rules(prompt: str, rules_block: str) -> str:
    if not rules_block:
        return prompt.replace("{gelernte_regeln}\n", "").replace("{gelernte_regeln}", "")
    return prompt.replace("{gelernte_regeln}", rules_block)


def _inject_extra_context(prompt: str, extra_context: str) -> str:
    if not extra_context.strip():
        return prompt.replace("{extra_context}\n", "").replace("{extra_context}", "")
    block = (
        "Zusätzliche Anmerkungen vom Bearbeiter, die nicht Teil der strukturierten Akte sind. "
        "Berücksichtige sie sofern für diese Sektion relevant:\n"
        + extra_context.strip()
        + "\n"
    )
    return prompt.replace("{extra_context}", block)


def _extract_substanz_tiefe(collected: str) -> str:
    m = re.search(r"^SUBSTANZ_TIEFE:\s*(\S+)", collected, re.MULTILINE)
    if not m:
        logger.warning("[generate_verlauf] SUBSTANZ_TIEFE nicht in Sammler-Output — fallback kompakt")
        return "kompakt"
    return m.group(1).strip()


def _load_curate_prompt(substanz_tiefe: str) -> str:
    tiefe = substanz_tiefe.lower().strip()
    if tiefe == "minimal":
        tiefe_normalized = "minimal"
    elif tiefe in {"kompakt", "mittel"}:
        tiefe_normalized = "kompakt"
    elif tiefe in {"ausführlich", "ausfuehrlich"}:
        tiefe_normalized = "ausfuehrlich"
    else:
        logger.warning("[generate_verlauf] unbekannte SUBSTANZ_TIEFE '%s', fallback kompakt", tiefe)
        tiefe_normalized = "kompakt"
    shared = get_prompt("brief_verlauf_curate_shared.txt", _PROMPTS_DIR)
    specific = get_prompt(f"brief_verlauf_curate_{tiefe_normalized}.txt", _PROMPTS_DIR)
    return shared + "\n\n" + specific


async def run(
    llm: LLMClient,
    patient: Patient,
    rules_block: str = "",
    extra_context: str = "",
    *,
    meilenstein: Optional[str] = None,
    befunde_formatted: str = "",
    diagnosen: str = "",
    anamnese: str = "",
    therapie: str = "",
    adressatenprofil: str = "",
) -> str:
    """3-Pass: Substanz-Sammler (collect) → Coverage-Auditor (audit) → Stil-Kurator (curate)."""
    patient_yaml = _to_yaml(patient)
    common_replacements = {
        "{patient_yaml}": patient_yaml,
        "{meilenstein_or_none}": meilenstein or "—",
        "{befunde_or_empty}": befunde_formatted or "—",
        "{diagnosen}": diagnosen or "—",
        "{anamnese}": anamnese or "—",
        "{therapie}": therapie or "—",
    }

    def _fill(template: str, extra: dict | None = None) -> str:
        for key, val in common_replacements.items():
            template = template.replace(key, val)
        if extra:
            for key, val in extra.items():
                template = template.replace(key, val)
        return _inject_extra_context(template, extra_context)

    # Pass 1 — Substanz-Sammler
    collect_prompt = _fill(get_prompt("brief_verlauf_collect.txt", _PROMPTS_DIR))
    resp1 = await llm.chat_completion(
        [{"role": "user", "content": collect_prompt}],
        temperature=0,
        max_tokens=4096,
    )
    collected = (resp1.choices[0].message.content or "").strip()
    print(f"[BR-C1.7-DIAG] verlauf_collect ({len(collected)} chars):\n{collected}\n", file=sys.stderr)

    # Pass 2 — Coverage-/Konsistenz-Auditor
    audit_prompt = _fill(
        get_prompt("brief_verlauf_audit.txt", _PROMPTS_DIR),
        extra={"{collected_substance}": collected},
    )
    resp2 = await llm.chat_completion(
        [{"role": "user", "content": audit_prompt}],
        temperature=0,
        max_tokens=4096,
    )
    audited = (resp2.choices[0].message.content or "").strip()

    # Pass 3 — Stil-Kurator (mit Regel-Injection und Adressaten-Profil)
    substanz_tiefe = _extract_substanz_tiefe(collected)
    curate_prompt = _inject_rules(
        _fill(
            _load_curate_prompt(substanz_tiefe),
            extra={
                "{audited_substance}": audited,
                "{ADRESSATENPROFIL}": adressatenprofil,
            },
        ),
        rules_block,
    )
    resp3 = await llm.chat_completion(
        [{"role": "user", "content": curate_prompt}],
        temperature=0,
        max_tokens=4096,
    )
    result = (resp3.choices[0].message.content or "").strip()
    print(f"[BR-C1.7-DIAG] verlauf_curate ({len(result)} chars):\n{result}\n", file=sys.stderr)
    return result
