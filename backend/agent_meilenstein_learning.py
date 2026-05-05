"""LLM-Agenten für den Meilenstein-Lernpfad (B2).

extract_rule_candidates: vergleicht Original vs. bearbeitet, liefert Regelkandidaten.
detect_conflict:         prüft einen Kandidaten gegen bestehende Regeln auf Widerspruch.
"""
import json
import logging
from pathlib import Path

from pydantic import BaseModel

from learning_storage import Rule
from llm_client import LLMClient

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT_CACHE: str | None = None
_CONFLICT_PROMPT_CACHE: str | None = None

_MAX_CANDIDATES = 10
_MAX_EXISTING_RULES = 20


def _get_extraction_prompt() -> str:
    global _EXTRACTION_PROMPT_CACHE
    if _EXTRACTION_PROMPT_CACHE is None:
        path = Path(__file__).parent / "prompts" / "learning_rule_extraction.txt"
        _EXTRACTION_PROMPT_CACHE = path.read_text(encoding="utf-8")
    return _EXTRACTION_PROMPT_CACHE


def _get_conflict_prompt() -> str:
    global _CONFLICT_PROMPT_CACHE
    if _CONFLICT_PROMPT_CACHE is None:
        path = Path(__file__).parent / "prompts" / "learning_conflict_detection.txt"
        _CONFLICT_PROMPT_CACHE = path.read_text(encoding="utf-8")
    return _CONFLICT_PROMPT_CACHE


class RuleCandidate(BaseModel):
    section: str
    rule_text: str


class ExtractionResult(BaseModel):
    candidates: list[RuleCandidate]


class ConflictResult(BaseModel):
    has_conflict: bool
    explanation: str


async def extract_rule_candidates(
    client: LLMClient,
    last_generated: str,
    edited: str,
) -> ExtractionResult:
    """Vergleicht Original- und Bearbeitungsfassung, extrahiert verallgemeinerbare Regelkandidaten."""
    system_prompt = _get_extraction_prompt()
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
    """
    if not existing_rules:
        return ConflictResult(has_conflict=False, explanation="")

    capped = existing_rules[:_MAX_EXISTING_RULES]
    existing_lines = "\n".join(f"- {r.rule_text}" for r in capped)
    user_msg = (
        f"Sektion: {section}\n\n"
        f"Neue Regel: {candidate_rule_text}\n\n"
        f"Bestehende Regeln:\n{existing_lines}"
    )

    try:
        response = await client.chat_completion(
            [
                {"role": "system", "content": _get_conflict_prompt()},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=256,
        )
    except Exception:
        logger.exception("[detect_conflict] LLM-Aufruf fehlgeschlagen")
        return ConflictResult(has_conflict=False, explanation="")

    raw = (response.choices[0].message.content or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[detect_conflict] Kein valides JSON: %s", raw[:200])
        return ConflictResult(has_conflict=False, explanation="")

    try:
        return ConflictResult.model_validate(data)
    except Exception:
        logger.warning("[detect_conflict] Pydantic-Validation fehlgeschlagen: %s", data)
        return ConflictResult(has_conflict=False, explanation="")
