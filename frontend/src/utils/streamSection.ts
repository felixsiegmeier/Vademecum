import type { Proposal } from "../types";

/**
 * Maps tool names to display section labels.
 * Used to aggregate streaming proposals into human-readable section counts.
 * Backend tool inventory: add_behandlungsdiagnose, add_verlaufsdiagnose,
 * add_vorbekannte_diagnose, add_befund, add_therapie, add_verlaufseintrag,
 * update_*, delete_entry.
 */
const SECTION_BY_TOOL: Record<string, string> = {
  add_behandlungsdiagnose: "Diagnosen",
  add_verlaufsdiagnose: "Diagnosen",
  add_vorbekannte_diagnose: "Diagnosen",
  add_befund: "Befunde",
  add_therapie: "Therapien",
  add_verlaufseintrag: "Verlauf",
};

// Fixed order controls display sequence in the live counter
const SECTION_ORDER = ["Diagnosen", "Therapien", "Befunde", "Verlauf", "Sonstiges"] as const;

/** Returns the display section for a proposal based on its primary tool. */
function proposalSection(p: Proposal): string {
  // For update proposals (delete+add pair) the add_call defines the section
  const tool = p.add_call?.tool ?? p.call?.tool ?? "";
  return SECTION_BY_TOOL[tool] ?? "Sonstiges";
}

/**
 * Returns a concise section-count string, e.g. "2 Diagnosen, 4 Therapien, 1 Befund".
 * Sections with 0 items are omitted. Falls back to "0 Vorschläge" if empty.
 */
export function formatSectionCounts(proposals: Proposal[]): string {
  const counts: Partial<Record<string, number>> = {};
  for (const p of proposals) {
    const section = proposalSection(p);
    counts[section] = (counts[section] ?? 0) + 1;
  }
  const parts = SECTION_ORDER.filter((s) => counts[s]).map((s) => `${counts[s]} ${s}`);
  return parts.length > 0 ? parts.join(", ") : "0 Vorschläge";
}
