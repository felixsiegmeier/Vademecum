import json
import logging
from pathlib import Path

from llm_client import LLMClient
from utils.prompts import get_prompt
from .schemas import ConflictResult

logger = logging.getLogger(__name__)
_PROMPTS_DIR = Path(__file__).parent / "prompts"
_MAX_EXISTING_RULES = 20


async def detect_conflict(
    client: LLMClient,
    candidate_rule_text: str,
    section: str,
    existing_rules: list,
) -> ConflictResult:
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
                {"role": "system", "content": get_prompt("conflict_detection", _PROMPTS_DIR)},
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
