import json
import logging
from pathlib import Path

from llm_client import LLMClient
from utils.prompts import get_prompt
from .schemas import RebuildResult

logger = logging.getLogger(__name__)
_PROMPTS_DIR = Path(__file__).parent / "prompts"


async def rebuild_rule_candidate(
    client: LLMClient,
    section: str,
    original_rule_text: str,
    original_reasoning: str,
    anchor: str,
    clarification: str,
) -> RebuildResult:
    system_prompt = get_prompt("rule_rebuild", _PROMPTS_DIR)
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
