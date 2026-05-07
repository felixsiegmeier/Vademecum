from .conflict import detect_conflict
from .extract import extract_rule_candidates
from .rebuild import rebuild_rule_candidate
from .schemas import ConflictResult, ExtractionResult, RebuildResult, RuleCandidate, TrivialChange

__all__ = [
    "from_edits",
    "rebuild",
    "ConflictResult",
    "ExtractionResult",
    "RebuildResult",
    "RuleCandidate",
    "TrivialChange",
]


async def from_edits(
    client,
    last_generated: str,
    edited: str,
    existing_rules: list,
) -> tuple[list[dict], list[dict]]:
    """Orchestrates extract + conflict-detect loop; returns (result_candidates, trivial_changes) as dicts."""
    extraction = await extract_rule_candidates(client, last_generated, edited)

    result_candidates: list[dict] = []
    for candidate in extraction.candidates:
        section_rules = [r for r in existing_rules if r.section == candidate.section]
        conflict = await detect_conflict(client, candidate.rule_text, candidate.section, section_rules)
        result_candidates.append({
            "section": candidate.section,
            "rule_text": candidate.rule_text,
            "reasoning": candidate.reasoning,
            "anchor": candidate.anchor,
            "conflict": {
                "conflicting_rule_id": conflict.conflicting_rule_id,
                "explanation": conflict.explanation,
            } if conflict.has_conflict else None,
        })

    trivial_changes = [
        {"section": tc.section, "rule_text": tc.rule_text, "reasoning": tc.reasoning, "anchor": tc.anchor}
        for tc in extraction.trivial_changes
    ]

    return result_candidates, trivial_changes


async def rebuild(
    client,
    section: str,
    original_rule_text: str,
    original_reasoning: str,
    anchor: str,
    clarification: str,
) -> RebuildResult:
    """Refine a rule candidate based on a clarification."""
    return await rebuild_rule_candidate(
        client=client,
        section=section,
        original_rule_text=original_rule_text,
        original_reasoning=original_reasoning,
        anchor=anchor,
        clarification=clarification,
    )
