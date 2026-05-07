from pathlib import Path
from typing import Optional

import yaml

from llm_client import LLMClient
from models.patient import Patient
from utils.prompts import get_prompt

_PROMPTS_DIR = Path(__file__).parent
PROMPT_FILE = "prompt.md"


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


async def run(
    llm: LLMClient,
    patient: Patient,
    collected_substance: str,
    *,
    meilenstein: Optional[str] = None,
    befunde_formatted: str = "",
    diagnosen: str = "",
    anamnese: str = "",
    therapie: str = "",
    extra_context: str = "",
) -> str:
    patient_yaml = _to_yaml(patient)
    prompt = get_prompt(PROMPT_FILE, _PROMPTS_DIR)
    filled = _inject_extra_context(
        prompt
        .replace("{patient_yaml}", patient_yaml)
        .replace("{meilenstein_or_none}", meilenstein or "—")
        .replace("{befunde_or_empty}", befunde_formatted or "—")
        .replace("{diagnosen}", diagnosen or "—")
        .replace("{anamnese}", anamnese or "—")
        .replace("{therapie}", therapie or "—")
        .replace("{collected_substance}", collected_substance),
        extra_context,
    )
    resp = await llm.chat_completion(
        [{"role": "user", "content": filled}],
        temperature=0,
        max_tokens=4096,
    )
    return (resp.choices[0].message.content or "").strip()
