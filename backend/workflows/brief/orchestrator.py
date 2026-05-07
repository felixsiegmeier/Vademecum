"""Brief-Generator — 4 LLM-Calls + 1 Pre-Pass-Helper.

Öffentliche API:
  generate_diagnosen  — JSON-Mode → Markdown
  generate_anamnese   — plain Text
  generate_therapie   — JSON-Mode → Markdown
  generate_verlauf    — 3-Pass: collect → audit → curate
  polish_section      — Lektor-Korrektur einer einzelnen Sektion
  format_sap_befunde  — Pre-Pass Befunde-Formatierung

Alle generate-Funktionen akzeptieren optional extra_context: str — ephemerer
Nutzer-Kontext der pro Call injiziert wird, nicht persistiert wird.
"""

import logging
from pathlib import Path
from typing import Optional

import yaml

import learning_storage
from llm_client import LLMClient
from models.patient import Patient
from utils.prompts import _PROMPT_CACHE, get_prompt  # _PROMPT_CACHE re-exported for tests
from workflows.brief.anamnese import skill as _anamnese_skill
from workflows.brief.diagnosen import skill as _diagnosen_skill
from workflows.brief.therapie import skill as _therapie_skill
from workflows.brief.verlauf import orchestrator as _verlauf_orchestrator

logger = logging.getLogger(__name__)

_llm_lite: Optional[LLMClient] = None

_PROMPTS_DIR = Path(__file__).parent / "polish"
_ADRESSATEN_DIR = Path(__file__).parent / "verlauf" / "03_curate" / "adressaten"


def _lite() -> LLMClient:
    global _llm_lite
    if _llm_lite is None:
        _llm_lite = LLMClient()
    return _llm_lite


def _get_prompt(name: str) -> str:
    return get_prompt(name, _PROMPTS_DIR)


def _load_adressatenprofil(name: str = "normalstation_intern") -> str:
    for ext in (".md", ".txt"):
        path = _ADRESSATEN_DIR / f"{name}{ext}"
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise ValueError(f"Unbekannter Adressat: '{name}'")


def _to_yaml(patient: Patient) -> str:
    return yaml.safe_dump(
        patient.model_dump(exclude_none=True, mode="json"),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=100,
    )


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


def _build_rules_block(rules: list) -> str:
    if not rules:
        return ""
    lines = [
        "<gelernte_regeln>",
        "",
        "Die folgenden Regeln wurden aus früheren manuellen Korrekturen abgeleitet. "
        "Beachte sie beim Formulieren dieser Sektion.",
    ]
    for rule in rules:
        lines.append(f"- {rule.rule_text}")
    lines.append("")
    lines.append("</gelernte_regeln>")
    return "\n".join(lines)


def _inject_rules(prompt: str, rules_block: str) -> str:
    if not rules_block:
        return prompt.replace("{gelernte_regeln}\n", "").replace("{gelernte_regeln}", "")
    return prompt.replace("{gelernte_regeln}", rules_block)


async def generate_diagnosen(patient: Patient, extra_context: str = "") -> str:
    rules = learning_storage.load_rules(domain="brief", section="diagnosen")
    rules_block = _build_rules_block(rules)
    try:
        result = await _diagnosen_skill.run(_lite(), patient, rules_block, extra_context)
    except Exception:
        logger.exception("[generate_diagnosen] Skill fehlgeschlagen")
        return ""
    learning_storage.save_last_output(patient.stammdaten.id, result, domain="brief", section="diagnosen")
    return result


async def generate_anamnese(patient: Patient, extra_context: str = "") -> str:
    rules = learning_storage.load_rules(domain="brief", section="anamnese")
    rules_block = _build_rules_block(rules)
    try:
        result = await _anamnese_skill.run(_lite(), patient, rules_block, extra_context)
    except Exception:
        logger.exception("[generate_anamnese] Skill fehlgeschlagen")
        return ""
    learning_storage.save_last_output(patient.stammdaten.id, result, domain="brief", section="anamnese")
    return result


async def generate_therapie(patient: Patient, extra_context: str = "") -> str:
    rules = learning_storage.load_rules(domain="brief", section="therapie")
    rules_block = _build_rules_block(rules)
    try:
        result = await _therapie_skill.run(_lite(), patient, rules_block, extra_context)
    except Exception:
        logger.exception("[generate_therapie] Skill fehlgeschlagen")
        return ""
    learning_storage.save_last_output(patient.stammdaten.id, result, domain="brief", section="therapie")
    return result


async def generate_verlauf(
    patient: Patient,
    meilenstein: Optional[str],
    befunde_formatted: str,
    diagnosen: str,
    anamnese: str,
    therapie: str,
    extra_context: str = "",
    adressat: str = "normalstation_intern",
    curate_variant_override: Optional[str] = None,
) -> str:
    """3-Pass: collect → audit → curate."""
    rules = learning_storage.load_rules(domain="brief", section="verlauf")
    rules_block = _build_rules_block(rules)
    adressatenprofil = _load_adressatenprofil(adressat)
    try:
        result = await _verlauf_orchestrator.run(
            _lite(), patient, rules_block, extra_context,
            meilenstein=meilenstein,
            befunde_formatted=befunde_formatted,
            diagnosen=diagnosen,
            anamnese=anamnese,
            therapie=therapie,
            adressatenprofil=adressatenprofil,
            curate_variant_override=curate_variant_override,
        )
    except Exception:
        logger.exception("[generate_verlauf] Skill fehlgeschlagen")
        return ""
    learning_storage.save_last_output(patient.stammdaten.id, result, domain="brief", section="verlauf")
    return result


async def polish_section(
    section: str,
    current_text: str,
    extra_context: str = "",
    patient: Optional[Patient] = None,
) -> str:
    """Lektor-Korrektur einer einzelnen Brief-Sektion (alle 4 Sektionen)."""
    patient_id = patient.stammdaten.id if patient else ""
    prompt_file = "brief_verlauf_polish.txt" if section == "verlauf" else "brief_section_polish.txt"
    rules = learning_storage.load_rules(domain="brief", section=section)
    prompt = _inject_rules(
        _inject_extra_context(
            _get_prompt(prompt_file).replace("{current_text}", current_text),
            extra_context,
        ),
        _build_rules_block(rules),
    )
    max_tokens = 4096 if section == "verlauf" else 2048
    try:
        resp = await _lite().chat_completion(
            [{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=max_tokens,
        )
    except Exception:
        logger.exception("[polish_section/%s] LLM-Aufruf fehlgeschlagen", section)
        return current_text
    result = (resp.choices[0].message.content or "").strip()
    if patient_id:
        learning_storage.save_last_output(patient_id, result, domain="brief", section=section)
    return result


async def format_sap_befunde(raw_text: str, extra_context: str = "") -> str:
    filled = _inject_extra_context(
        _get_prompt("brief_befunde_format.txt").replace("{raw_text}", raw_text),
        extra_context,
    )
    try:
        resp = await _lite().chat_completion(
            [{"role": "user", "content": filled}],
            temperature=0,
            max_tokens=4096,
        )
    except Exception:
        logger.exception("[format_sap_befunde] LLM-Aufruf fehlgeschlagen")
        return raw_text
    return (resp.choices[0].message.content or "").strip()
