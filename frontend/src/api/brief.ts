import type { Brief, BriefSectionKey } from "../types";

const base = (patientId: string) => `/api/brief/${patientId}`;

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

export async function formatSapBefunde(patientId: string, rawText: string): Promise<string> {
  const res = await fetch(`${base(patientId)}/format-befunde`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text: rawText }),
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
