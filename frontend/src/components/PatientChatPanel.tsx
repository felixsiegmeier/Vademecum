import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type {
  ApplyResponse,
  ApplyResult,
  ArgsRecord,
  ChatResponse,
  Patient,
  Proposal,
  StreamEvent,
} from "../types";
import { STAMMDATEN_FELD_LABELS } from "../types";
import { takePendingFile } from "../pendingFileStore";
import { parseNdjson } from "../utils/ndjson";
import { formatSectionCounts } from "../utils/streamSection";
import ProposalCard from "./ProposalCard";
import { toast } from "sonner";

// ── Anzeige-Typen für die Chat-History ───────────────────────────────────────

interface ChatTextEntry {
  kind: "chat-text";
  role: "user" | "assistant";
  content: string;
}

interface ProposalsEntry {
  kind: "proposals";
  id: string;
  source: "upload" | "chat";
  fileName?: string;
  proposals: Proposal[];
  selectedIndices: Set<number>;
  editedArgs: Map<number, ArgsRecord>;
  failedIndices: Set<number>;
  failedSummaries: Map<number, string>;
  appliedIndices: Set<number>;  // erfolgreich angewendete Indizes
  fullyApplied: boolean;        // alle Cards entweder applied oder abgewählt → Bar weg
  discarded: boolean;           // User hat Vorschläge verworfen → Bar weg
  streaming: boolean;           // true während NDJSON-Stream aktiv
  streamStatus: { phase: "block1" | "block2"; iter: number; max_iter: number; items_in_phase: number } | null;
}

interface AutoSkipEntry {
  kind: "auto-skip";
  id: string;
  fileName?: string;
}

type HistoryEntry = ChatTextEntry | ProposalsEntry | AutoSkipEntry;

// Chat-History pro Patient — bleibt beim Tab-Wechsel erhalten
const historyStore = new Map<string, HistoryEntry[]>();

// ── Hilfsfunktionen ──────────────────────────────────────────────────────────

const ACCEPTED_MIME = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "text/plain",
  "text/markdown",
  "text/csv",
  "application/csv",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];

function makeProposalsEntry(
  source: "upload" | "chat",
  proposals: Proposal[],
  fileName?: string,
  streaming = false,
): ProposalsEntry {
  return {
    kind: "proposals",
    id: `prop-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    source,
    fileName,
    proposals,
    selectedIndices: new Set(proposals.map((_, i) => i)),
    editedArgs: new Map(),
    failedIndices: new Set(),
    failedSummaries: new Map(),
    appliedIndices: new Set(),
    fullyApplied: false,
    discarded: false,
    streaming,
    streamStatus: null,
  };
}

/** Mergt edited args in das passende Tool-Call-Slot eines Proposals (call oder add_call). */
function mergeEditedArgs(p: Proposal, edited: ArgsRecord | undefined): Proposal {
  if (!edited) return p;
  if (p.type === "update" && p.add_call) {
    return { ...p, add_call: { ...p.add_call, args: { ...p.add_call.args, ...edited } } };
  }
  if ((p.type === "add" || p.type === "update_singleton") && p.call) {
    return { ...p, call: { ...p.call, args: { ...p.call.args, ...edited } } };
  }
  return p;
}

interface Props {
  patientId: string;
  patient: Patient | null;
  refreshPatient: () => Promise<void>;
  onPatientChanged: () => void;
}

export function PatientChatPanel({ patientId, patient, refreshPatient, onPatientChanged }: Props) {
  const [history, setHistory] = useState<HistoryEntry[]>(() => historyStore.get(patientId) ?? []);
  const [input, setInput] = useState("");
  const [uploading, setUploading] = useState(false);   // F5: globaler Upload-Guard
  const [chatBusy, setChatBusy] = useState(false);
  const [chatBusyLong, setChatBusyLong] = useState(false); // true wenn Input > CUTOFF (2-Pass)
  const [applying, setApplying] = useState(false);
  const [mismatchModal, setMismatchModal] = useState<
    Array<{ feld: string; current: string; proposed: string }>
  | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setHistory(historyStore.get(patientId) ?? []);
  }, [patientId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, chatBusy, uploading]);

  function persist(next: HistoryEntry[]) {
    historyStore.set(patientId, next);
    setHistory(next);
  }

  function showToast(kind: "success" | "error" | "warning" | "info", text: string) {
    toast[kind](text);
  }

  // Safe for async streaming loops — uses functional setState so closure is never stale
  function updateEntryById(entryId: string, fn: (e: ProposalsEntry) => ProposalsEntry) {
    setHistory((prev) => {
      const next = prev.map((e) =>
        e.kind === "proposals" && e.id === entryId ? fn(e) : e,
      );
      historyStore.set(patientId, next);
      return next;
    });
  }

  // Letzten noch nicht vollständig angewendeten proposals-Block finden — dieser steuert die Bar
  const activeProposalsIdx = useMemo(() => {
    for (let i = history.length - 1; i >= 0; i--) {
      const e = history[i];
      if (e.kind === "proposals" && !e.fullyApplied && !e.discarded) return i;
    }
    return -1;
  }, [history]);

  const activeProposals = activeProposalsIdx >= 0 ? (history[activeProposalsIdx] as ProposalsEntry) : null;

  // ── Chat-Send (Text) ──────────────────────────────────────────────────────

  async function handleSubmit() {
    if (!input.trim() || chatBusy || uploading) return;
    const text = input;
    const isLong = text.length > 2000; // CHAT_2PASS_CUTOFF — gespiegelt aus Backend
    const userEntry: ChatTextEntry = { kind: "chat-text", role: "user", content: text };
    const optimistic = [...history, userEntry];
    persist(optimistic);
    setInput("");
    setChatBusy(true);
    setChatBusyLong(isLong);
    try {
      const res = await fetch(`/api/patients/${patientId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: [{ role: "user", content: text }] }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const detail = body?.detail ?? `HTTP ${res.status}`;
        throw new Error(typeof detail === "string" ? detail : `HTTP ${res.status}`);
      }
      const data = (await res.json()) as ChatResponse;
      if (data.reply) {
        // Single-Pass Text-Antwort des LLM
        const replyEntry: ChatTextEntry = {
          kind: "chat-text",
          role: "assistant",
          content: data.reply,
        };
        persist([...optimistic, replyEntry]);
      } else if (data.proposals.length > 0) {
        // Tool-Calls → Proposals (Single-Pass oder 2-Pass)
        const propEntry = makeProposalsEntry("chat", data.proposals);
        persist([...optimistic, propEntry]);
      } else {
        // Keine Proposals, kein Reply — Fallback-Meldung
        const msgEntry: ChatTextEntry = {
          kind: "chat-text",
          role: "assistant",
          content: data.message ?? "Keine Änderungen am Patienten vorgeschlagen.",
        };
        persist([...optimistic, msgEntry]);
      }
    } catch (e) {
      const err: ChatTextEntry = {
        kind: "chat-text",
        role: "assistant",
        content: `Fehler: ${(e as Error).message}`,
      };
      persist([...optimistic, err]);
      showToast("error", "Verbindung zum Backend verloren");
    } finally {
      setChatBusy(false);
      setChatBusyLong(false);
      textareaRef.current?.focus();
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  // ── Auto-Upload bei Navigation vom NewPatientDialog ──────────────────────
  // PatientChatPanel wird bei Patientenwechsel nicht neu gemountet (gleiche Route).
  // Um stale-history-Probleme zu vermeiden, wird historyStore direkt gelesen.

  useEffect(() => {
    const file = takePendingFile();
    if (!file) return;
    handleFileSelected(file, historyStore.get(patientId) ?? []); // eslint-disable-line react-hooks/exhaustive-deps
  }, [patientId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Datei-Upload (NDJSON-Streaming) ──────────────────────────────────────

  async function handleFileSelected(file: File, baseHistory?: HistoryEntry[]) {
    if (uploading) return;  // Concurrent-Schutz
    if (!ACCEPTED_MIME.includes(file.type)) {
      const err: ChatTextEntry = {
        kind: "chat-text",
        role: "assistant",
        content: `Nicht unterstützter Dateityp: ${file.type || file.name}. Bitte PDF, JPG oder PNG wählen.`,
      };
      persist([...(baseHistory ?? history), err]);
      return;
    }

    const userEntry: ChatTextEntry = {
      kind: "chat-text",
      role: "user",
      content: `[Datei: ${file.name}]`,
    };
    const optimistic = [...(baseHistory ?? history), userEntry];

    // Streaming entry added immediately so the live bar appears before first LLM token
    const streamEntry = makeProposalsEntry("upload", [], file.name, true);
    persist([...optimistic, streamEntry]);
    const entryId = streamEntry.id;

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("patient_id", patientId);
      const res = await fetch("/api/uploads", { method: "POST", body: formData });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      if (!res.body) throw new Error("Keine Stream-Antwort vom Server");

      for await (const event of parseNdjson<StreamEvent>(res.body)) {
        if (event.type === "heartbeat") continue;

        if (event.type === "status") {
          updateEntryById(entryId, (e) => ({ ...e, streamStatus: event }));
        } else if (event.type === "proposals") {
          updateEntryById(entryId, (e) => {
            const newProposals = [...e.proposals, ...event.items];
            const newSelected = new Set(e.selectedIndices);
            event.items.forEach((_, i) => newSelected.add(e.proposals.length + i));
            return { ...e, proposals: newProposals, selectedIndices: newSelected };
          });
        } else if (event.type === "error") {
          showToast("error", "Verbindung abgebrochen — bitte erneut hochladen");
          updateEntryById(entryId, (e) => ({ ...e, streaming: false, discarded: true }));
          return;
        } else if (event.type === "done") {
          if (event.auto_skipped) {
            // Replace streaming entry with auto-skip entry in the same position
            const skip: AutoSkipEntry = {
              kind: "auto-skip",
              id: `skip-${Date.now()}`,
              fileName: file.name,
            };
            setHistory((prev) => {
              const next = prev.map((e) =>
                e.kind === "proposals" && e.id === entryId ? skip : e,
              );
              historyStore.set(patientId, next);
              return next;
            });
          } else {
            updateEntryById(entryId, (e) => ({ ...e, streaming: false, streamStatus: null }));
          }
        }
      }
    } catch (e) {
      showToast("error", "Verbindung zum Backend verloren");
      updateEntryById(entryId, (e) => ({ ...e, streaming: false, discarded: true }));
    } finally {
      setUploading(false);
    }
  }

  // ── Per-Proposal-Card-Interaktion ─────────────────────────────────────────

  function updateProposalsEntry(entryId: string, fn: (e: ProposalsEntry) => ProposalsEntry) {
    const next = history.map((e) =>
      e.kind === "proposals" && e.id === entryId ? fn(e) : e,
    );
    persist(next);
  }

  function toggleProposal(entryId: string, idx: number) {
    updateProposalsEntry(entryId, (e) => {
      const sel = new Set(e.selectedIndices);
      if (sel.has(idx)) sel.delete(idx);
      else sel.add(idx);
      return { ...e, selectedIndices: sel };
    });
  }

  function setProposalArgs(entryId: string, idx: number, args: ArgsRecord) {
    updateProposalsEntry(entryId, (e) => {
      const map = new Map(e.editedArgs);
      map.set(idx, args);
      return { ...e, editedArgs: map };
    });
  }

  function handleDiscard() {
    if (!activeProposals || applying) return;
    updateProposalsEntry(activeProposals.id, (e) => ({ ...e, discarded: true }));
  }

  async function handleForceApply() {
    setMismatchModal(null);
    await handleApply(true);
  }

  // ── Apply-Flow ────────────────────────────────────────────────────────────

  async function handleApply(force = false) {
    if (!activeProposals || applying) return;
    const entry = activeProposals;
    const indicesToApply: number[] = [];
    const proposalsToApply: Proposal[] = [];
    entry.proposals.forEach((p, i) => {
      if (!entry.selectedIndices.has(i)) return;
      if (entry.appliedIndices.has(i)) return;  // schon erfolgreich angewendet
      indicesToApply.push(i);
      proposalsToApply.push(mergeEditedArgs(p, entry.editedArgs.get(i)));
    });
    if (proposalsToApply.length === 0) return;

    setApplying(true);
    try {
      const res = await fetch(`/api/patients/${patientId}/apply-proposals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposals: proposalsToApply, force }),
      });
      if (res.status === 409) {
        const body = await res.json().catch(() => ({}));
        if (body.mismatch_warning) {
          setMismatchModal(body.conflicting_fields ?? []);
          return;
        }
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const data = (await res.json()) as ApplyResponse;
      const results: ApplyResult[] = data.results;

      const failedIndices = new Set(entry.failedIndices);
      const failedSummaries = new Map(entry.failedSummaries);
      const appliedIndices = new Set(entry.appliedIndices);
      let okCount = 0;
      let failCount = 0;
      results.forEach((r, k) => {
        const proposalIdx = indicesToApply[k];
        if (r.ok) {
          okCount++;
          appliedIndices.add(proposalIdx);
          failedIndices.delete(proposalIdx);
          failedSummaries.delete(proposalIdx);
        } else {
          failCount++;
          failedIndices.add(proposalIdx);
          failedSummaries.set(proposalIdx, r.summary || "Fehler");
        }
      });

      // Auto-deselect failed indices so bar disappears by default after partial failure
      const newSelectedIndices = new Set(entry.selectedIndices);
      failedIndices.forEach((i) => newSelectedIndices.delete(i));

      // fullyApplied only when no failures and all selected entries are applied
      const fullyApplied = failedIndices.size === 0 && entry.proposals.every((_, i) => {
        if (!newSelectedIndices.has(i)) return true;
        return appliedIndices.has(i);
      });

      updateProposalsEntry(entry.id, (e) => ({
        ...e,
        selectedIndices: newSelectedIndices,
        failedIndices,
        failedSummaries,
        appliedIndices,
        fullyApplied,
      }));

      await refreshPatient();
      onPatientChanged();

      if (failCount === 0) {
        showToast("success", `${okCount} ${okCount === 1 ? "Vorschlag" : "Vorschläge"} angewendet.`);
      } else {
        showToast("warning", `${okCount} angewendet, ${failCount} fehlgeschlagen — bitte prüfen.`);
      }
    } catch (e) {
      showToast("error", `Verbindung zum Backend verloren: ${(e as Error).message}`);
    } finally {
      setApplying(false);
    }
  }

  // ── Render-Helfer ─────────────────────────────────────────────────────────

  function renderEntry(entry: HistoryEntry, idx: number) {
    if (entry.kind === "chat-text") {
      const isUser = entry.role === "user";
      return (
        <div key={idx} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
          <div
            className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${
              isUser
                ? "bg-blue-600 text-white whitespace-pre-wrap"
                : "bg-white border border-gray-200 text-gray-800"
            }`}
          >
            {isUser ? (
              entry.content
            ) : (
              // Assistant replies from LLM may contain Markdown — render it properly
              <ReactMarkdown
                components={{
                  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                  ul: ({ children }) => <ul className="list-disc list-inside space-y-1 mb-2">{children}</ul>,
                  ol: ({ children }) => <ol className="list-decimal list-inside space-y-1 mb-2">{children}</ol>,
                  li: ({ children }) => <li>{children}</li>,
                  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                  em: ({ children }) => <em className="italic">{children}</em>,
                  code: ({ children }) => (
                    <code className="bg-gray-100 rounded px-1 font-mono text-xs">{children}</code>
                  ),
                }}
              >
                {entry.content}
              </ReactMarkdown>
            )}
          </div>
        </div>
      );
    }

    if (entry.kind === "auto-skip") {
      return (
        <div key={idx} className="flex justify-start">
          <div className="max-w-[80%] rounded-xl bg-gray-50 border border-gray-200 px-3 py-2 text-sm text-gray-500">
            {entry.fileName ? (
              <>📎 <span className="font-medium">{entry.fileName}</span> — </>
            ) : null}
            PDF identisch zum letzten Upload — keine Änderungen gefunden.
          </div>
        </div>
      );
    }

    // proposals block
    const isStreaming = entry.streaming;
    const headerCount = isStreaming && entry.proposals.length > 0
      ? formatSectionCounts(entry.proposals)
      : `${entry.proposals.length} ${entry.proposals.length === 1 ? "Vorschlag" : "Vorschläge"}`;
    const liveText = entry.streamStatus
      ? `Block ${entry.streamStatus.phase === "block1" ? 1 : 2} — Iteration ${entry.streamStatus.iter}/${entry.streamStatus.max_iter}, ${entry.streamStatus.items_in_phase} Items bisher`
      : "Verbinde…";

    return (
      <div key={idx} className="flex justify-start">
        <div className={`rounded-xl border border-gray-200 bg-white text-sm overflow-hidden w-full max-w-[90%] ${entry.discarded ? "opacity-50 pointer-events-none" : ""}`}>
          {/* Header */}
          <div className="px-3 py-2 border-b border-gray-100 bg-gray-50 flex items-center justify-between gap-2">
            <p className="font-medium text-gray-800 truncate">
              {entry.source === "upload" ? "📎 " : "💬 "}
              {entry.fileName ?? (entry.source === "chat" ? "Chat-Vorschläge" : "Upload")}
            </p>
            <span className="text-xs text-gray-500 shrink-0">
              {headerCount}
              {!isStreaming && entry.appliedIndices.size > 0 && ` · ${entry.appliedIndices.size} angewendet`}
            </span>
          </div>

          {/* Sticky live bar while streaming */}
          {isStreaming && (
            <div className="px-3 py-1.5 border-b border-amber-100 bg-amber-50 flex items-center gap-2 text-xs text-amber-800">
              <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
              <span>{liveText}</span>
            </div>
          )}

          {/* Proposal cards — flow in progressively */}
          <div className="px-3 py-2 space-y-2 max-h-[28rem] overflow-y-auto">
            {entry.proposals.map((p, i) => {
              const applied = entry.appliedIndices.has(i);
              return (
                <div key={i} className={applied ? "opacity-50 pointer-events-none" : ""}>
                  <ProposalCard
                    proposal={p}
                    patient={patient}
                    selected={entry.selectedIndices.has(i) && !applied}
                    onToggle={() => toggleProposal(entry.id, i)}
                    onArgsChange={(args) => setProposalArgs(entry.id, i, args)}
                    failedSummary={entry.failedSummaries.get(i) ?? null}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // ── Sticky-Apply-Bar (F6) ────────────────────────────────────────────────

  const totalActive = activeProposals?.proposals.length ?? 0;
  const selectedActiveCount = activeProposals
    ? Array.from(activeProposals.selectedIndices).filter(
        (i) => !activeProposals.appliedIndices.has(i),
      ).length
    : 0;

  return (
    <div className="flex flex-col h-full relative">
      <div className="flex-1 overflow-y-auto p-4 space-y-3 pb-2">
        {history.length === 0 && (
          <p className="text-center text-sm text-gray-400 mt-8">
            Visite, Befunde oder Fragen eingeben…
          </p>
        )}
        {history.map((e, i) => renderEntry(e, i))}
        {chatBusy && (
          <div className="flex justify-start">
            <div className={`rounded-xl border px-3 py-2 text-sm ${chatBusyLong ? "bg-amber-50 border-amber-200 text-amber-800" : "bg-white border-gray-200 text-gray-400"}`}>
              {chatBusyLong ? "Verarbeitung läuft, kann 30–60 Sekunden dauern…" : "Denkt nach…"}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Sticky-Apply-Bar */}
      {activeProposals && (
        <div className="border-t border-blue-100 bg-blue-50/80 backdrop-blur px-4 py-2 flex items-center justify-between gap-2">
          <button
            onClick={handleDiscard}
            disabled={applying || activeProposals.streaming}
            className="rounded-lg bg-gray-100 px-4 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Verwerfen
          </button>
          <div className="flex items-center gap-2">
            {activeProposals.streaming ? (
              <span className="flex items-center gap-1.5 text-sm text-amber-700">
                <Loader2 className="w-4 h-4 animate-spin" />
                Analysiert…
              </span>
            ) : (
              <span className="text-sm text-blue-900">
                <span className="font-medium">{selectedActiveCount}</span> von {totalActive} anwenden
              </span>
            )}
            <button
              onClick={() => handleApply()}
              disabled={applying || selectedActiveCount === 0 || activeProposals.streaming}
              className="rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {applying ? "Wird übernommen…" : "Anwenden"}
            </button>
          </div>
        </div>
      )}

      {/* Eingabezeile */}
      <div className="border-t bg-white px-4 py-3 flex gap-2 items-end">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.txt,.md,.csv,.xlsx,.docx"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFileSelected(file);
            e.target.value = "";
          }}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading || chatBusy}
          title={uploading ? "Upload läuft…" : "Dokument hochladen"}
          className="shrink-0 rounded-lg border border-gray-300 px-3 py-2 text-gray-500 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          📎
        </button>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={chatBusy || uploading}
          placeholder="Visite, Befunde, Fragen… (Enter = Senden, Shift+Enter = Zeilenumbruch)"
          rows={2}
          className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        />
        <button
          onClick={handleSubmit}
          disabled={chatBusy || uploading || !input.trim()}
          className="shrink-0 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Senden
        </button>
      </div>

      {/* Mismatch-Modal */}
      {mismatchModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4 p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-2">
              Identitätsfelder geändert
            </h2>
            <p className="text-sm text-gray-600 mb-4">
              Dieses Dokument schlägt Änderungen an Patienten-Identitätsfeldern vor.
              Möglicherweise gehört es zu einem anderen Patienten.
            </p>
            <table className="w-full text-xs mb-6 border-collapse">
              <thead>
                <tr className="text-gray-500 border-b border-gray-200">
                  <th className="text-left py-1 pr-3 font-medium">Feld</th>
                  <th className="text-left py-1 pr-3 font-medium">Aktuell</th>
                  <th className="text-left py-1 font-medium">Vorschlag</th>
                </tr>
              </thead>
              <tbody>
                {mismatchModal.map((c) => (
                  <tr key={c.feld} className="border-b border-gray-100">
                    <td className="py-1.5 pr-3 text-gray-700 font-medium">
                      {STAMMDATEN_FELD_LABELS[c.feld] ?? c.feld}
                    </td>
                    <td className="py-1.5 pr-3 text-gray-500">{c.current}</td>
                    <td className="py-1.5 text-gray-900 font-medium">{c.proposed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setMismatchModal(null)}
                disabled={applying}
                className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg disabled:opacity-50"
              >
                Abbrechen
              </button>
              <button
                onClick={handleForceApply}
                disabled={applying}
                className="px-4 py-2 text-sm font-medium text-white bg-orange-600 hover:bg-orange-700 rounded-lg disabled:opacity-50"
              >
                {applying ? "Wird angewendet…" : "Trotzdem anwenden"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
