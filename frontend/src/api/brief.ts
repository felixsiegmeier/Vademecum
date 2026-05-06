import type { Brief, BriefSectionKey, LearnFromEditsResponse, StoredRule } from "../types";

const base = (patientId: string) => `/api/brief/${patientId}`;
const learnBase = (domain: string, section?: string) =>
  section ? `/api/learn/${domain}/${section}` : `/api/learn/${domain}`;

export async function getBrief(patientId: string): Promise<Brief> {
  const res = await fetch(base(patientId));
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function generateBrief(patientId: string, extraContext = ""): Promise<Brief> {
  const res = await fetch(`${base(patientId)}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ extra_context: extraContext }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function regenerateSection(
  patientId: string,
  section: BriefSectionKey,
  extraContext = ""
): Promise<Partial<Brief>> {
  const res = await fetch(`${base(patientId)}/generate-section/${section}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ extra_context: extraContext }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function formatSapBefunde(
  patientId: string,
  rawText: string,
  extraContext = ""
): Promise<string> {
  const res = await fetch(`${base(patientId)}/format-befunde`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text: rawText, extra_context: extraContext }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  const data: { befunde: string } = await res.json();
  return data.befunde;
}

export async function saveSectionEdit(
  patientId: string,
  section: BriefSectionKey,
  content: string
): Promise<void> {
  await fetch(`${base(patientId)}/section/${section}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
}

export async function extractFileText(files: File[]): Promise<string> {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const res = await fetch("/api/extract-text", { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  const data: { combined_text: string } = await res.json();
  return data.combined_text;
}

export async function polishSection(
  patientId: string,
  section: BriefSectionKey,
  extraContext = ""
): Promise<Partial<Brief>> {
  const res = await fetch(`${base(patientId)}/polish-section/${section}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ extra_context: extraContext }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function deleteBrief(patientId: string): Promise<void> {
  const res = await fetch(base(patientId), { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
}

// ─── Lernlog API ─────────────────────────────────────────────────────────────

export async function learnFromEdits(
  domain: string,
  section: string | undefined,
  patientId: string,
  editedContent: string,
): Promise<LearnFromEditsResponse> {
  const res = await fetch(`${learnBase(domain, section)}/from-edits`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patient_id: patientId, edited_content: editedContent }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function getLearnRules(domain: string, section?: string): Promise<StoredRule[]> {
  const res = await fetch(`${learnBase(domain, section)}/rules`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data: { rules: StoredRule[] } = await res.json();
  return data.rules;
}

export async function deleteLearnRule(
  domain: string,
  section: string | undefined,
  id: string,
): Promise<void> {
  const res = await fetch(`${learnBase(domain, section)}/rules/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);
}

export async function saveLearnRules(
  domain: string,
  section: string | undefined,
  rulesToAdd: { section: string; rule_text: string }[],
  ruleIdsToDelete: string[],
): Promise<{ saved_count: number; deleted_count: number; total_rules: number }> {
  const res = await fetch(`${learnBase(domain, section)}/save-rules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rules_to_add: rulesToAdd, rule_ids_to_delete: ruleIdsToDelete }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function rebuildLearnRule(
  domain: string,
  section: string | undefined,
  payload: {
    section: string;
    original_rule_text: string;
    original_reasoning: string;
    anchor: string;
    clarification: string;
  },
): Promise<{ section: string; rule_text: string; reasoning: string; anchor: string }> {
  const res = await fetch(`${learnBase(domain, section)}/rebuild-rule`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function getSystemPrompt(domain: string, section?: string): Promise<string> {
  const res = await fetch(`${learnBase(domain, section)}/system-prompt`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data: { content: string } = await res.json();
  return data.content;
}
