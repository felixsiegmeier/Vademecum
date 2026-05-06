"""Brief-Generator — 4 LLM-Sub-Agents + 1 Pre-Pass-Helper.

Sub-Agents:
  generate_diagnosen  — JSON-Mode → Markdown (flash-lite)
  generate_anamnese   — plain Text (flash-lite)
  generate_therapie   — JSON-Mode → Markdown (flash-lite)
  generate_verlauf    — 3-Pass: Substanz-Sammler → Coverage-Auditor → Stil-Kurator
  format_sap_befunde  — Pre-Pass Befunde-Formatierung (flash-lite)

Alle 4 LLM-Sub-Agents akzeptieren optional extra_context: str — ephemerer
Nutzer-Kontext der pro Call injiziert wird, nicht persistiert wird.

Modell für alle Passes: LLMClient() Default (keine eigene Flash-Konstante;
vollständig via LLM_BACKEND Env-Variable steuerbar, vorbereitet für Qwen-Migration).
"""

import json
import logging
from pathlib import Path
from typing import Optional

import yaml

import learning_storage
from llm_client import LLMClient
from models.patient import Patient

logger = logging.getLogger(__name__)

# Lazy-initialisierter Client — erst beim ersten LLM-Call erzeugt, damit
# der Import vor load_dotenv() in main.py keine ValueError wirft.
_llm_lite: Optional[LLMClient] = None

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_PROMPT_CACHE: dict[str, str] = {}


def _lite() -> LLMClient:
    global _llm_lite
    if _llm_lite is None:
        _llm_lite = LLMClient()
    return _llm_lite


def _get_prompt(name: str) -> str:
    if name not in _PROMPT_CACHE:
        _PROMPT_CACHE[name] = (_PROMPTS_DIR / name).read_text(encoding="utf-8")
    return _PROMPT_CACHE[name]


def _to_yaml(patient: Patient) -> str:
    return yaml.safe_dump(
        patient.model_dump(exclude_none=True, mode="json"),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=100,
    )


def _inject_extra_context(prompt: str, extra_context: str) -> str:
    """Ersetzt {extra_context}-Platzhalter. Non-empty → Hinweis-Block; leer → entfernt."""
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
    """Ersetzt {gelernte_regeln}-Platzhalter. Non-empty → XML-Block; leer → entfernt."""
    if not rules_block:
        return prompt.replace("{gelernte_regeln}\n", "").replace("{gelernte_regeln}", "")
    return prompt.replace("{gelernte_regeln}", rules_block)


def _render_diagnosen(data: dict) -> str:
    lines: list[str] = []
    behandlung = data.get("behandlung") or []
    if behandlung:
        lines.append("**Behandlungsdiagnosen:**")
        for i, item in enumerate(behandlung):
            lines.append(f"- **{item}**" if i == 0 else f"- {item}")
        lines.append("")
    verlauf = data.get("verlauf") or []
    if verlauf:
        lines.append("**Verlaufsdiagnosen:**")
        for item in verlauf:
            lines.append(f"- {item}")
        lines.append("")
    vorbekannt = data.get("vorbekannt") or []
    if vorbekannt:
        lines.append("**Vorbekannte Diagnosen:**")
        for item in vorbekannt:
            lines.append(f"- {item}")
    return "\n".join(lines).strip()


def _render_therapie(data: dict) -> str:
    lines: list[str] = []
    initial_op = data.get("initial_op") or ""
    if initial_op:
        lines.append("**Initial-OP:**")
        lines.append(initial_op)
        lines.append("")
    antimikrobiell = data.get("antimikrobiell") or []
    if antimikrobiell:
        lines.append("**Antimikrobielle Therapie:**")
        for item in antimikrobiell:
            lines.append(f"- {item}")
        lines.append("")
    weitere = data.get("weitere") or []
    if weitere:
        lines.append("**Weitere Prozeduren:**")
        for item in weitere:
            lines.append(f"- {item}")
    return "\n".join(lines).strip()


async def generate_diagnosen(patient: Patient, extra_context: str = "") -> str:
    rules = learning_storage.load_rules(domain="brief", section="diagnosen")
    filled = _inject_rules(
        _inject_extra_context(
            _get_prompt("brief_diagnosen.txt").replace("{patient_yaml}", _to_yaml(patient)),
            extra_context,
        ),
        _build_rules_block(rules),
    )
    try:
        resp = await _lite().chat_completion(
            [{"role": "user", "content": filled}],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=1024,
        )
    except Exception:
        logger.exception("[generate_diagnosen] LLM-Aufruf fehlgeschlagen")
        return ""
    raw = (resp.choices[0].message.content or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[generate_diagnosen] Kein valides JSON: %s", raw[:300])
        return raw
    result = _render_diagnosen(data)
    learning_storage.save_last_output(patient.stammdaten.id, result, domain="brief", section="diagnosen")
    return result


async def generate_anamnese(patient: Patient, extra_context: str = "") -> str:
    rules = learning_storage.load_rules(domain="brief", section="anamnese")
    filled = _inject_rules(
        _inject_extra_context(
            _get_prompt("brief_anamnese.txt").replace("{patient_yaml}", _to_yaml(patient)),
            extra_context,
        ),
        _build_rules_block(rules),
    )
    try:
        resp = await _lite().chat_completion(
            [{"role": "user", "content": filled}],
            temperature=0,
            max_tokens=1024,
        )
    except Exception:
        logger.exception("[generate_anamnese] LLM-Aufruf fehlgeschlagen")
        return ""
    result = (resp.choices[0].message.content or "").strip()
    learning_storage.save_last_output(patient.stammdaten.id, result, domain="brief", section="anamnese")
    return result


async def generate_therapie(patient: Patient, extra_context: str = "") -> str:
    rules = learning_storage.load_rules(domain="brief", section="therapie")
    filled = _inject_rules(
        _inject_extra_context(
            _get_prompt("brief_therapie.txt").replace("{patient_yaml}", _to_yaml(patient)),
            extra_context,
        ),
        _build_rules_block(rules),
    )
    try:
        resp = await _lite().chat_completion(
            [{"role": "user", "content": filled}],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=1024,
        )
    except Exception:
        logger.exception("[generate_therapie] LLM-Aufruf fehlgeschlagen")
        return ""
    raw = (resp.choices[0].message.content or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[generate_therapie] Kein valides JSON: %s", raw[:300])
        return raw
    result = _render_therapie(data)
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
    collect_prompt = _fill(_get_prompt("brief_verlauf_collect.txt"))
    try:
        resp1 = await _lite().chat_completion(
            [{"role": "user", "content": collect_prompt}],
            temperature=0,
            max_tokens=4096,
        )
    except Exception:
        logger.exception("[generate_verlauf/collect] LLM-Aufruf fehlgeschlagen")
        return ""
    collected = (resp1.choices[0].message.content or "").strip()

    # Pass 2 — Coverage-/Konsistenz-Auditor
    audit_prompt = _fill(
        _get_prompt("brief_verlauf_audit.txt"),
        extra={"{collected_substance}": collected},
    )
    try:
        resp2 = await _lite().chat_completion(
            [{"role": "user", "content": audit_prompt}],
            temperature=0,
            max_tokens=4096,
        )
    except Exception:
        logger.exception("[generate_verlauf/audit] LLM-Aufruf fehlgeschlagen")
        return collected
    audited = (resp2.choices[0].message.content or "").strip()

    # Pass 3 — Stil-Kurator (mit Regel-Injection)
    verlauf_rules = learning_storage.load_rules(domain="brief", section="verlauf")
    curate_prompt = _inject_rules(
        _fill(
            _get_prompt("brief_verlauf_curate.txt"),
            extra={"{audited_substance}": audited},
        ),
        _build_rules_block(verlauf_rules),
    )
    try:
        resp3 = await _lite().chat_completion(
            [{"role": "user", "content": curate_prompt}],
            temperature=0,
            max_tokens=4096,
        )
    except Exception:
        logger.exception("[generate_verlauf/curate] LLM-Aufruf fehlgeschlagen")
        return audited
    result = (resp3.choices[0].message.content or "").strip()
    learning_storage.save_last_output(patient.stammdaten.id, result, domain="brief", section="verlauf")
    return result


async def polish_section(
    section: str,
    current_text: str,
    extra_context: str = "",
    patient: Optional["Patient"] = None,
) -> str:
    """Lektor-Korrektur einer einzelnen Brief-Sektion (alle 4 Sektionen).

    Verlauf: brief_verlauf_polish.txt (Lektor-Klauseln, kein Curate-Pass).
    Andere: brief_section_polish.txt — gleiche Lektor-Klauseln, Struktur-Treue-Hinweis.
    """
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
