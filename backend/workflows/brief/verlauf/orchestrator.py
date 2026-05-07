"""3-Pass Verlauf-Orchestrator: collect → audit → curate.

Importiert die nummerierten Subdirs via importlib, da Python-Identifier
keine mit Ziffer beginnenden Namen erlauben.
"""

import importlib
import logging
from typing import Optional

from llm_client import LLMClient
from models.patient import Patient

logger = logging.getLogger(__name__)

_collect = importlib.import_module("workflows.brief.verlauf.01_collect.skill")
_audit = importlib.import_module("workflows.brief.verlauf.02_audit.skill")
_curate = importlib.import_module("workflows.brief.verlauf.03_curate.skill")


async def run(
    llm: LLMClient,
    patient: Patient,
    rules_block: str = "",
    extra_context: str = "",
    *,
    meilenstein: Optional[str] = None,
    befunde_formatted: str = "",
    diagnosen: str = "",
    anamnese: str = "",
    therapie: str = "",
    adressatenprofil: str = "",
    curate_variant_override: Optional[str] = None,
) -> str:
    """3-Pass: Substanz-Sammler (collect) → Coverage-Auditor (audit) → Stil-Kurator (curate)."""
    collect_output = await _collect.run(
        llm, patient,
        meilenstein=meilenstein,
        befunde_formatted=befunde_formatted,
        diagnosen=diagnosen,
        anamnese=anamnese,
        therapie=therapie,
        extra_context=extra_context,
    )
    logger.debug("[BR-C1.7-DIAG] verlauf_collect (%d chars):\n%s\n", len(collect_output.substance), collect_output.substance)

    audited = await _audit.run(
        llm, patient, collect_output.substance,
        meilenstein=meilenstein,
        befunde_formatted=befunde_formatted,
        diagnosen=diagnosen,
        anamnese=anamnese,
        therapie=therapie,
        extra_context=extra_context,
    )

    curate_variant = curate_variant_override or collect_output.curate_variant
    result = await _curate.run(
        llm, patient, audited, curate_variant,
        rules_block=rules_block,
        extra_context=extra_context,
        meilenstein=meilenstein,
        befunde_formatted=befunde_formatted,
        diagnosen=diagnosen,
        anamnese=anamnese,
        therapie=therapie,
        adressatenprofil=adressatenprofil,
    )
    logger.debug("[BR-C1.7-DIAG] verlauf_curate (%d chars):\n%s\n", len(result), result)
    return result
