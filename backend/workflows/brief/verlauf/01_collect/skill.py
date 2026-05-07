from pathlib import Path
from typing import Optional

import yaml

from llm_client import LLMClient
from models.patient import Patient
from utils.prompts import get_prompt
from .schema import CollectOutput

_PROMPTS_DIR = Path(__file__).parent
_CURATE_PROMPTS_DIR = Path(__file__).parent.parent / "03_curate" / "prompts"
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


def _build_available_variants() -> str:
    lines = []
    for p in sorted(_CURATE_PROMPTS_DIR.glob("*.md")):
        if p.stem == "shared":
            continue
        try:
            raw = p.read_text(encoding="utf-8")
            desc = ""
            if raw.startswith("---"):
                _, fm_block, _ = raw.split("---", 2)
                fm = yaml.safe_load(fm_block) or {}
                desc = fm.get("description", "")
            lines.append(f"- {p.stem}: {desc}" if desc else f"- {p.stem}")
        except Exception:
            lines.append(f"- {p.stem}")
    return "\n".join(lines)


async def run(
    llm: LLMClient,
    patient: Patient,
    *,
    meilenstein: Optional[str] = None,
    befunde_formatted: str = "",
    diagnosen: str = "",
    anamnese: str = "",
    therapie: str = "",
    extra_context: str = "",
) -> CollectOutput:
    patient_yaml = _to_yaml(patient)
    available_variants = _build_available_variants()
    prompt = get_prompt(PROMPT_FILE, _PROMPTS_DIR)
    filled = _inject_extra_context(
        prompt
        .replace("{patient_yaml}", patient_yaml)
        .replace("{meilenstein_or_none}", meilenstein or "—")
        .replace("{befunde_or_empty}", befunde_formatted or "—")
        .replace("{diagnosen}", diagnosen or "—")
        .replace("{anamnese}", anamnese or "—")
        .replace("{therapie}", therapie or "—")
        .replace("{available_variants}", available_variants),
        extra_context,
    )
    resp = await llm.chat_completion(
        [{"role": "user", "content": filled}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=4096,
    )
    raw = (resp.choices[0].message.content or "").strip()
    return CollectOutput.model_validate_json(raw)
