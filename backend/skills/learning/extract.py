import json
import logging
from pathlib import Path

from llm_client import LLMClient
from utils.prompts import get_prompt
from .schemas import ExtractionResult

logger = logging.getLogger(__name__)
_PROMPTS_DIR = Path(__file__).parent / "prompts"
_MAX_CANDIDATES = 10


async def extract_rule_candidates(
    client: LLMClient,
    last_generated: str,
    edited: str,
) -> ExtractionResult:
    system_prompt = get_prompt("rule_extraction.txt", _PROMPTS_DIR)
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
