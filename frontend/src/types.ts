// frontend/src/types.ts

/** Args-Werte: meistens string, gelegentlich boolean (update_status.aktiv), gelegentlich null. */
export type ArgValue = string | boolean | null;
export type ArgsRecord = Record<string, ArgValue>;

export interface ToolCall {
  tool: string;
  args: ArgsRecord;
}

/**
 * Backend agent_extraction_core.Proposal:
 *   "add"              → call gesetzt
 *   "delete"           → call gesetzt (delete_entry, standalone)
 *   "update_singleton" → call gesetzt (update_*-Tool für Singleton-Felder)
 *   "update"           → call=null, delete_call+add_call beide gesetzt
 */
export type ProposalType = "add" | "delete" | "update" | "update_singleton";

export interface Proposal {
  type: ProposalType;
  call: ToolCall | null;
  delete_call: ToolCall | null;
  add_call: ToolCall | null;
}

/**
 * Streaming events from POST /api/uploads (NDJSON, one object per line).
 * Transport: application/x-ndjson over chunked HTTP (not SSE — POST upload).
 */
export type StreamEvent =
  | { type: "status"; phase: "block1" | "block2"; iter: number; max_iter: number; items_in_phase: number }
  | { type: "proposals"; phase: "block1" | "block2"; items: Proposal[] }
  | { type: "heartbeat" }
  | { type: "done"; total_proposals: number; auto_skipped: boolean }
  | { type: "error"; message: string; retryable: boolean };

/** @deprecated Upload endpoint now streams NDJSON — kept for reference only. */
export interface UploadResponse {
  patient_id: string;
  proposals: Proposal[];
  auto_skipped: boolean;
}

/** Response von POST /api/patients/{id}/chat */
export interface ChatResponse {
  proposals: Proposal[];
  auto_skipped: boolean;
  message?: string;
  reply?: string | null;
}

/** Response von POST /api/patients/{id}/apply-proposals */
export interface ApplyResult {
  type: ProposalType;
  ok: boolean;
  id?: string;
  summary: string;
}

export interface ApplyResponse {
  results: ApplyResult[];
}

// ─── UI-Helpers ─────────────────────────────────────────────────────

export const TOOL_LABELS: Record<string, string> = {
  add_behandlungsdiagnose: "Behandlungsdiagnose",
  add_verlaufsdiagnose: "Verlaufsdiagnose",
  add_vorbekannte_diagnose: "Vorbekannte Diagnose",
  add_befund: "Befund",
  add_therapie: "Therapie",
  add_verlaufseintrag: "Verlaufseintrag",
  update_anamnese: "Anamnese",
  update_therapieziel: "Therapieziel",
  update_status: "Status",
  update_bettplatz: "Bettplatz",
  update_verlegungsziel: "Verlegungsziel",
  update_stammdaten: "Stammdaten",
  delete_entry: "Eintrag löschen",
};

/** update_stammdaten nutzt generisches feld/wert-Pattern. Backend-Enum: name|geburtsdatum|geschlecht|aufnahmedatum|aufnahme_quelle. */
export const STAMMDATEN_FELD_LABELS: Record<string, string> = {
  name: "Name",
  geburtsdatum: "Geburtsdatum",
  geschlecht: "Geschlecht",
  aufnahmedatum: "Aufnahmedatum",
  aufnahme_quelle: "Aufnahme-Quelle",
};

export const THERAPIE_KATEGORIEN: Record<string, { label: string; color: string }> = {
  operativ:       { label: "Operativ",       color: "bg-red-100 text-red-700" },
  MCS:            { label: "MCS",            color: "bg-purple-100 text-purple-700" },
  RRT:            { label: "RRT",            color: "bg-teal-100 text-teal-700" },
  respiratorisch: { label: "Respiratorisch", color: "bg-blue-100 text-blue-700" },
  interventionell:{ label: "Interventionell",color: "bg-orange-100 text-orange-700" },
  antimikrobiell: { label: "Antimikrobiell", color: "bg-violet-100 text-violet-700" },
  medikamentös:   { label: "Medikamentös",   color: "bg-slate-100 text-slate-700" },
  bedside:        { label: "Bedside",        color: "bg-amber-100 text-amber-700" },
  sonstiges:      { label: "Sonstiges",      color: "bg-gray-100 text-gray-700" },
};

// ─── Lernlog / Rule-Review ───────────────────────────────────────────────────

export interface LearnConflict {
  conflicting_rule_id: string;
  explanation: string;
}

export interface LearnRuleCandidate {
  section: string;
  rule_text: string;
  reasoning: string;
  anchor: string;
  conflict: LearnConflict | null;
}

export interface LearnTrivialChange {
  description: string;
  anchor: string;
}

export interface LearnFromEditsResponse {
  rule_candidates: LearnRuleCandidate[];
  trivial_changes: LearnTrivialChange[];
}

export interface StoredRule {
  id: string;
  section: string;
  rule_text: string;
  created_at: string;
  patient_schema_version_at_creation: string;
}

export type ConflictResolution = "replace" | "keep_both" | "discard_new";

export const MEILENSTEIN_SECTIONS = [
  "Operationen & Prozeduren",
  "Behandlungsdiagnosen",
  "Relevante Nebendiagnosen",
  "Kardiale Funktion",
  "Antikoagulation",
  "Antimikrobielle Therapie",
  "Befunde",
  "Therapieziel / Patientenwille",
] as const;

/** Zentrales Patient-Schema, gespiegelt aus backend/models/patient.py. */
export interface PatientStammdaten {
  id: string;
  name: string;
  geburtsdatum?: string | null;
  geschlecht?: string | null;
  bettplatz?: string | null;
  aufnahmedatum: string;
  aufnahme_quelle?: string | null;
  verlegungsziel?: string | null;
  aktiv: boolean;
}

export interface DiagnoseEntry {
  id: string;
  text: string;
  datum?: string | null;
  source_quote: string;
}

export interface BefundEntry {
  id: string;
  text: string;
  datum: string;
  source_quote: string;
}

export interface TherapieEntry {
  id: string;
  bezeichnung: string;
  kategorie: string;
  beginn: string;
  ende?: string | null;
  indikation: string;
  source_quote: string;
}

export interface VerlaufsEintragEntry {
  id: string;
  datum: string;
  text: string;
  source_quote: string;
}

export interface Patient {
  stammdaten: PatientStammdaten;
  anamnese?: string | null;
  therapieziel?: string | null;
  behandlungsdiagnosen: DiagnoseEntry[];
  verlaufsdiagnosen: DiagnoseEntry[];
  vorbekannte_diagnosen: DiagnoseEntry[];
  befunde: BefundEntry[];
  therapien: TherapieEntry[];
  verlaufseintraege: VerlaufsEintragEntry[];
}
