import type { Patient } from "../types";

export interface ResolvedEntry {
  text: string;
  section: string;
}

/**
 * Findet einen Listen-Eintrag im Patient-State per ULID.
 * Gibt null zurück, wenn die ID in keiner der bekannten Listen vorkommt.
 */
export function resolveById(patient: Patient | null | undefined, id: string): ResolvedEntry | null {
  if (!patient) return null;

  const sections: Array<[keyof Patient, string]> = [
    ["behandlungsdiagnosen", "Behandlungsdiagnose"],
    ["verlaufsdiagnosen", "Verlaufsdiagnose"],
    ["vorbekannte_diagnosen", "Vorbekannte Diagnose"],
    ["befunde", "Befund"],
    ["therapien", "Therapie"],
    ["verlaufseintraege", "Verlaufseintrag"],
  ];

  for (const [key, label] of sections) {
    const list = patient[key] as Array<{ id: string; text?: string; bezeichnung?: string }> | undefined;
    if (!Array.isArray(list)) continue;
    const entry = list.find((e) => e.id === id);
    if (entry) {
      return { text: entry.text ?? entry.bezeichnung ?? "(kein Text)", section: label };
    }
  }
  return null;
}
