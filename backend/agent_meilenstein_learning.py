"""LLM-Agenten für den Meilenstein-Lernpfad (B2/B3).

extract_rule_candidates: vergleicht Original vs. bearbeitet, liefert Regelkandidaten + triviale Änderungen.
detect_conflict:         prüft einen Kandidaten gegen bestehende Regeln auf Widerspruch.
rebuild_rule_candidate:  verfeinert einen Kandidaten anhand einer Klarstellung.
"""
import json
import logging
from pathlib import Path

from learning_storage import Rule
from llm_client import LLMClient
from skills.learning.schemas import (  # noqa: F401
    ConflictResult,
    ExtractionResult,
    RebuildResult,
    RuleCandidate,
    TrivialChange,
)
from utils.prompts import get_prompt

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

_MAX_CANDIDATES = 10
_MAX_EXISTING_RULES = 20



async def extract_rule_candidates(
    client: LLMClient,
    last_generated: str,
    edited: str,
) -> ExtractionResult:
    """Vergleicht Original- und Bearbeitungsfassung, extrahiert verallgemeinerbare Regelkandidaten."""
    system_prompt = get_prompt("learning_rule_extraction.txt", _PROMPTS_DIR)
    user_msg = (
        f"<original>\n{last_generated}\n</original>\n\n"
        f"<bearbeitet>\n{edited}\n</bearbeitet>"
    )
    try:
        response = await client.chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=1024,
        )
    except Exception:
        logger.exception("[extract_rule_candidates] LLM-Aufruf fehlgeschlagen")
        return ExtractionResult(candidates=[])

    raw = (response.choices[0].message.content or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[extract_rule_candidates] Kein valides JSON: %s", raw[:300])
        return ExtractionResult(candidates=[])

    try:
        result = ExtractionResult.model_validate(data)
    except Exception:
        logger.warning("[extract_rule_candidates] Pydantic-Validation fehlgeschlagen: %s", data)
        return ExtractionResult(candidates=[])

    result.candidates = result.candidates[:_MAX_CANDIDATES]
    return result


async def detect_conflict(
    client: LLMClient,
    candidate_rule_text: str,
    section: str,
    existing_rules: list[Rule],
) -> ConflictResult:
    """Prüft ob candidate_rule_text einer bestehenden Regel widerspricht.

    Short-circuit: leere existing_rules → kein Konflikt ohne LLM-Call.
    Gibt conflicting_rule_id der konfligierenden Regel zurück (oder "").
    """
    if not existing_rules:
        return ConflictResult(has_conflict=False, explanation="", conflicting_rule_id="")

    capped = existing_rules[:_MAX_EXISTING_RULES]
    existing_lines = "\n".join(f"[ID: {r.id}] {r.rule_text}" for r in capped)
    user_msg = (
        f"Sektion: {section}\n\n"
        f"Neue Regel: {candidate_rule_text}\n\n"
        f"Bestehende Regeln:\n{existing_lines}"
    )

    try:
        response = await client.chat_completion(
            [
                {"role": "system", "content": get_prompt("learning_conflict_detection.txt", _PROMPTS_DIR)},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=256,
        )
    except Exception:
        logger.exception("[detect_conflict] LLM-Aufruf fehlgeschlagen")
        return ConflictResult(has_conflict=False, explanation="", conflicting_rule_id="")

    raw = (response.choices[0].message.content or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[detect_conflict] Kein valides JSON: %s", raw[:200])
        return ConflictResult(has_conflict=False, explanation="", conflicting_rule_id="")

    try:
        return ConflictResult.model_validate(data)
    except Exception:
        logger.warning("[detect_conflict] Pydantic-Validation fehlgeschlagen: %s", data)
        return ConflictResult(has_conflict=False, explanation="", conflicting_rule_id="")


async def rebuild_rule_candidate(
    client: LLMClient,
    section: str,
    original_rule_text: str,
    original_reasoning: str,
    anchor: str,
    clarification: str,
) -> RebuildResult:
    """Verfeinert einen Regelkandidaten anhand einer Klarstellung des Arztes."""
    system_prompt = get_prompt("learning_rule_rebuild.txt", _PROMPTS_DIR)
    user_msg = (
        f"section: {section}\n"
        f"original_rule_text: {original_rule_text}\n"
        f"original_reasoning: {original_reasoning}\n"
        f"anchor: {anchor}\n"
        f"clarification: {clarification}"
    )
    try:
        response = await client.chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=512,
        )
    except Exception:
        logger.exception("[rebuild_rule_candidate] LLM-Aufruf fehlgeschlagen")
        return RebuildResult(rule_text=original_rule_text, reasoning=original_reasoning)

    raw = (response.choices[0].message.content or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[rebuild_rule_candidate] Kein valides JSON: %s", raw[:300])
        return RebuildResult(rule_text=original_rule_text, reasoning=original_reasoning)

    try:
        return RebuildResult.model_validate(data)
    except Exception:
        logger.warning("[rebuild_rule_candidate] Pydantic-Validation fehlgeschlagen: %s", data)
        return RebuildResult(rule_text=original_rule_text, reasoning=original_reasoning)
