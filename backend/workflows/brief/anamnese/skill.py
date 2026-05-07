from pathlib import Path

import yaml

from llm_client import LLMClient
from models.patient import Patient
from utils.prompts import get_prompt

PROMPT_FILE = "prompt.md"


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


async def run(
    llm: LLMClient,
    patient: Patient,
    rules_block: str = "",
    extra_context: str = "",
) -> str:
    """Generates the Anamnese section of an Arztbrief from a Patient object."""
    prompt = get_prompt(PROMPT_FILE, Path(__file__).parent)
    filled = _inject_rules(
        _inject_extra_context(
            prompt.replace("{patient_yaml}", _to_yaml(patient)),
            extra_context,
        ),
        rules_block,
    )
    resp = await llm.chat_completion(
        [{"role": "user", "content": filled}],
        temperature=0,
        max_tokens=1024,
    )
    return (resp.choices[0].message.content or "").strip()
