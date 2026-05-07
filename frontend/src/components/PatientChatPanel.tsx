import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Paperclip, MessageSquare, Send, AlertTriangle, CheckCircle2, X, ChevronDown, ChevronRight } from "lucide-react";
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
import { getChatHistory, saveChatHistory } from "../api/chat";
import { takePendingFile } from "../pendingFileStore";
import { parseNdjson } from "../utils/ndjson";
import { formatSectionCounts } from "../utils/streamSection";
import ProposalCard from "./ProposalCard";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

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
  phaseLabel: string | null;    // z.B. "Block 1 — Themenextraktion"
  phaseStartedAt: number | null; // Date.now() beim phase_start-Event
  collapsed: boolean;           // true nach Auto-Collapse (alle entschieden)
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
    phaseLabel: null,
    phaseStartedAt: null,
    collapsed: false,
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
  const [pendingFile, setPendingFile] = useState<File | null>(null);
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
    setPendingFile(null);
    const cached = historyStore.get(patientId);
    if (cached) {
      setHistory(cached);
      return;
    }
    // Fresh session: load text history from server
    getChatHistory(patientId).then((messages) => {
      const entries: ChatTextEntry[] = messages.map((m) => ({
        kind: "chat-text",
        role: m.role,
        content: m.content,
      }));
      historyStore.set(patientId, entries);
      setHistory(entries);
    });
  }, [patientId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Tick every second while uploading to drive the elapsed-seconds counter in the live bar
  const [tickMs, setTickMs] = useState(Date.now());
  useEffect(() => {
    if (!uploading) return;
    const id = setInterval(() => setTickMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, [uploading]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, chatBusy, uploading]);

  function persist(next: HistoryEntry[]) {
    historyStore.set(patientId, next);
    setHistory(next);
  }

  function persistChatToServer(entries: HistoryEntry[]) {
    const messages = entries
      .filter((e): e is ChatTextEntry => e.kind === "chat-text")
      .map((e) => ({ role: e.role, content: e.content }));
    saveChatHistory(patientId, messages); // fire-and-forget
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

  // Auto-collapse decided (fullyApplied or discarded) proposals entries after 500ms
  useEffect(() => {
    const decided = history.filter(
      (e): e is ProposalsEntry =>
        e.kind === "proposals" && (e.fullyApplied || e.discarded) && !e.collapsed && !e.streaming,
    );
    if (decided.length === 0) return;
    const id = setTimeout(() => {
      decided.forEach((e) => updateEntryById(e.id, (entry) => ({ ...entry, collapsed: true })));
    }, 500);
    return () => clearTimeout(id);
  }, [history]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Chat-Send (Text) ──────────────────────────────────────────────────────

  async function handleSubmit() {
    if (chatBusy || uploading) return;

    if (pendingFile) {
      const ctx = input.trim() || undefined;
      const file = pendingFile;
      setPendingFile(null);
      setInput("");
      await handleFileSelected(file, undefined, ctx);
      return;
    }

    if (!input.trim()) return;
    const text = input;
    const isLong = text.length > 2000; // CHAT_2PASS_CUTOFF — gespiegelt aus Backend
    const userEntry: ChatTextEntry = { kind: "chat-text", role: "user", content: text };
    const optimistic = [...history, userEntry];
    persist(optimistic);
    setInput("");
    setChatBusy(true);
    setChatBusyLong(isLong);
    try {
      const chatMessages = optimistic
        .filter((e): e is ChatTextEntry => e.kind === "chat-text")
        .map((e) => ({ role: e.role, content: e.content }));
      const res = await fetch(`/api/patients/${patientId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: chatMessages }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const detail = body?.detail ?? `HTTP ${res.status}`;
        throw new Error(typeof detail === "string" ? detail : `HTTP ${res.status}`);
      }
      const data = (await res.json()) as ChatResponse;
      if (data.reply) {
        const replyEntry: ChatTextEntry = {
          kind: "chat-text",
          role: "assistant",
          content: data.reply,
        };
        const next = [...optimistic, replyEntry];
        persist(next);
        persistChatToServer(next);
      } else if (data.proposals.length > 0) {
        const propEntry = makeProposalsEntry("chat", data.proposals);
        persist([...optimistic, propEntry]);
        persistChatToServer(optimistic); // save user message; proposals are ephemeral
      } else {
        const msgEntry: ChatTextEntry = {
          kind: "chat-text",
          role: "assistant",
          content: data.message ?? "Keine Änderungen am Patienten vorgeschlagen.",
        };
        const next = [...optimistic, msgEntry];
        persist(next);
        persistChatToServer(next);
      }
    } catch (e) {
      const err: ChatTextEntry = {
        kind: "chat-text",
        role: "assistant",
        content: `Fehler: ${(e as Error).message}`,
      };
      const next = [...optimistic, err];
      persist(next);
      persistChatToServer(next);
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

  async function handleFileSelected(file: File, baseHistory?: HistoryEntry[], extraContext?: string) {
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
      content: extraContext ? `[Datei: ${file.name}]\n${extraContext}` : `[Datei: ${file.name}]`,
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
      if (extraContext) formData.append("extra_context", extraContext);
      const res = await fetch("/api/uploads", { method: "POST", body: formData });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      if (!res.body) throw new Error("Keine Stream-Antwort vom Server");

      for await (const event of parseNdjson<StreamEvent>(res.body)) {
        if (event.type === "heartbeat") continue;

        if (event.type === "stream_opened") {
          // Connection confirmed — "Verbinde…" transitions to phase label on next phase_start
        } else if (event.type === "phase_start") {
          const label = event.phase === "block1" ? "Block 1 — Themenextraktion" : "Block 2 — Verlauf";
          updateEntryById(entryId, (e) => ({
            ...e,
            phaseLabel: label,
            phaseStartedAt: Date.now(),
            streamStatus: null,
          }));
        } else if (event.type === "phase_done") {
          // phase_done: keep phaseLabel visible until next phase_start or done clears it
        } else if (event.type === "status") {
          updateEntryById(entryId, (e) => ({ ...e, streamStatus: event }));
        } else if (event.type === "proposals") {
          updateEntryById(entryId, (e) => {
            const newProposals = [...e.proposals, ...event.items];
            const newSelected = new Set(e.selectedIndices);
            event.items.forEach((_, i) => newSelected.add(e.proposals.length + i));
            return { ...e, proposals: newProposals, selectedIndices: newSelected };
          });
        } else if (event.type === "error") {
          const msg = event.reason === "llm_timeout"
            ? "LLM-Timeout — bitte Dokument erneut hochladen"
            : "Verbindung abgebrochen — bitte erneut hochladen";
          showToast("error", msg);
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
        <div key={idx} className={cn("flex", isUser ? "justify-end" : "justify-start")}>
          <div
            className={cn(
              "max-w-[85%] rounded-md px-3 py-2 text-sm",
              isUser
                ? "bg-primary text-primary-foreground whitespace-pre-wrap"
                : "bg-muted/60 text-foreground border",
            )}
          >
            {isUser ? (
              entry.content
            ) : (
              <div className="prose prose-sm max-w-none prose-p:my-2 prose-p:first:mt-0 prose-p:last:mb-0 prose-ul:my-2 prose-ol:my-2 prose-li:my-0">
                <ReactMarkdown
                  components={{
                    code: ({ children }) => (
                      <code className="bg-background border rounded px-1 font-mono text-xs">{children}</code>
                    ),
                  }}
                >
                  {entry.content}
                </ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      );
    }

    if (entry.kind === "auto-skip") {
      return (
        <div key={idx} className="flex justify-start">
          <div className="max-w-[85%] rounded-md bg-muted/40 border px-3 py-2 text-sm text-muted-foreground flex items-center gap-2">
            <CheckCircle2 className="size-4 text-emerald-600 shrink-0" />
            <span>
              {entry.fileName ? (
                <><span className="font-medium text-foreground">{entry.fileName}</span> — </>
              ) : null}
              identisch zum letzten Upload, keine Änderungen.
            </span>
          </div>
        </div>
      );
    }

    // proposals block
    const isStreaming = entry.streaming;
    const headerCount = isStreaming && entry.proposals.length > 0
      ? formatSectionCounts(entry.proposals)
      : `${entry.proposals.length} ${entry.proposals.length === 1 ? "Vorschlag" : "Vorschläge"}`;
    const elapsedS = entry.phaseStartedAt ? Math.floor((tickMs - entry.phaseStartedAt) / 1000) : 0;
    const liveText = entry.phaseLabel
      ? `${entry.phaseLabel} (${elapsedS}s)…`
      : entry.streamStatus
      ? `Block ${entry.streamStatus.phase === "block1" ? 1 : 2} — Iter ${entry.streamStatus.iter}/${entry.streamStatus.max_iter}, ${entry.streamStatus.items_in_phase} Items`
      : "Verbinde…";

    const isDecided = entry.fullyApplied || entry.discarded;
    const canCollapse = isDecided && !isStreaming;

    // Collapsed: single header row only
    if (entry.collapsed) {
      return (
        <div key={idx} className="flex justify-start">
          <button
            className="rounded-md border bg-card text-sm w-full max-w-[92%] shadow-sm px-3 py-2 flex items-center gap-2 text-left hover:bg-muted/20 transition-colors opacity-60"
            onClick={() => updateEntryById(entry.id, (e) => ({ ...e, collapsed: false }))}
          >
            <ChevronRight className="size-3.5 text-muted-foreground shrink-0" />
            {entry.source === "upload"
              ? <Paperclip className="size-3.5 text-muted-foreground shrink-0" />
              : <MessageSquare className="size-3.5 text-muted-foreground shrink-0" />}
            <span className="flex-1 truncate font-medium text-foreground">
              {entry.fileName ?? (entry.source === "chat" ? "Chat-Vorschläge" : "Upload")}
            </span>
            <span className="text-xs text-muted-foreground shrink-0">
              {headerCount}
              {entry.appliedIndices.size > 0 && ` · ${entry.appliedIndices.size} angewendet`}
            </span>
          </button>
        </div>
      );
    }

    return (
      <div key={idx} className="flex justify-start">
        <div className={cn(
          "rounded-md border bg-card text-sm overflow-hidden w-full max-w-[92%] shadow-sm",
          entry.discarded && "opacity-50 pointer-events-none",
        )}>
          {/* Header — clickable to collapse when decided */}
          <div
            className={cn(
              "px-3 py-2 border-b bg-muted/40 flex items-center justify-between gap-2",
              canCollapse && "cursor-pointer hover:bg-muted/60 transition-colors",
            )}
            onClick={canCollapse ? () => updateEntryById(entry.id, (e) => ({ ...e, collapsed: true })) : undefined}
          >
            <p className="font-medium text-foreground truncate flex items-center gap-1.5">
              {canCollapse && <ChevronDown className="size-3.5 text-muted-foreground shrink-0" />}
              {entry.source === "upload"
                ? <Paperclip className="size-3.5 text-muted-foreground shrink-0" />
                : <MessageSquare className="size-3.5 text-muted-foreground shrink-0" />}
              <span className="truncate">
                {entry.fileName ?? (entry.source === "chat" ? "Chat-Vorschläge" : "Upload")}
              </span>
            </p>
            <span className="text-xs text-muted-foreground shrink-0">
              {headerCount}
              {!isStreaming && entry.appliedIndices.size > 0 && ` · ${entry.appliedIndices.size} angewendet`}
            </span>
          </div>

          {/* Sticky live bar while streaming */}
          {isStreaming && (
            <div className="px-3 py-1.5 border-b border-amber-200 bg-amber-50 flex items-center gap-2 text-xs text-amber-900">
              <Loader2 className="size-3.5 animate-spin shrink-0" />
              <span>{liveText}</span>
            </div>
          )}

          {/* Proposal cards — flow in progressively; read-only when decided */}
          <div className={cn("px-3 py-2 space-y-2 max-h-[28rem] overflow-y-auto", isDecided && "pointer-events-none")}>
            {entry.proposals.map((p, i) => {
              const applied = entry.appliedIndices.has(i);
              return (
                <div key={i} className={cn(applied && "opacity-50")}>
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
    <div className="flex flex-col h-full relative bg-background">
      <div className="flex-1 overflow-y-auto p-4 space-y-3 pb-2">
        {history.length === 0 && (
          <p className="text-center text-sm text-muted-foreground mt-8">
            Visite, Befunde oder Fragen eingeben…
          </p>
        )}
        {history.map((e, i) => renderEntry(e, i))}
        {chatBusy && (
          <div className="flex justify-start">
            <div className={cn(
              "rounded-md border px-3 py-2 text-sm flex items-center gap-2",
              chatBusyLong
                ? "bg-amber-50 border-amber-200 text-amber-900"
                : "bg-muted/40 text-muted-foreground",
            )}>
              <Loader2 className="size-3.5 animate-spin" />
              {chatBusyLong ? "Verarbeitung läuft, kann 30–60 Sekunden dauern…" : "Denkt nach…"}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Sticky-Apply-Bar */}
      {activeProposals && (
        <div className="border-t bg-primary/5 px-4 py-2 flex items-center justify-between gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleDiscard}
            disabled={applying || activeProposals.streaming}
          >
            Verwerfen
          </Button>
          <div className="flex items-center gap-2">
            {activeProposals.streaming ? (
              <span className="flex items-center gap-1.5 text-sm text-amber-700">
                <Loader2 className="size-4 animate-spin" />
                Analysiert…
              </span>
            ) : (
              <span className="text-sm text-foreground">
                <Badge variant="secondary" className="mr-1">{selectedActiveCount}</Badge>
                von {totalActive} anwenden
              </span>
            )}
            <Button
              size="sm"
              onClick={() => handleApply()}
              disabled={applying || selectedActiveCount === 0 || activeProposals.streaming}
            >
              {applying ? "Wird übernommen…" : "Anwenden"}
            </Button>
          </div>
        </div>
      )}

      {/* Eingabezeile */}
      <div className="border-t bg-card">
        {/* Pending file card */}
        {pendingFile && (
          <div className="flex items-center gap-2 px-4 pt-2">
            <div className="flex-1 flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-1.5 text-sm min-w-0">
              <Paperclip className="size-3.5 text-muted-foreground shrink-0" />
              <span className="truncate text-foreground">{pendingFile.name}</span>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setPendingFile(null)}
              title="Datei entfernen"
              className="shrink-0 size-7"
            >
              <X className="size-3.5" />
            </Button>
          </div>
        )}
        <div className="px-4 py-3 flex gap-2 items-end">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.txt,.md,.csv,.xlsx,.docx"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) setPendingFile(file);
            e.target.value = "";
          }}
        />
        <Button
          variant="outline"
          size="icon"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading || chatBusy}
          title={uploading ? "Upload läuft…" : "Dokument hochladen"}
          className="shrink-0"
        >
          <Paperclip className="size-4" />
        </Button>
        <Textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={chatBusy || uploading}
          placeholder="Visite, Befunde, Fragen… (Enter = Senden, Shift+Enter = Zeilenumbruch)"
          rows={2}
          className="flex-1 resize-none min-h-[2.5rem]"
        />
        <Button
          onClick={handleSubmit}
          disabled={chatBusy || uploading || (!input.trim() && !pendingFile)}
          className="shrink-0"
        >
          <Send className="size-4" />
          Senden
        </Button>
        </div>
      </div>

      {/* Mismatch-Modal */}
      <Dialog open={!!mismatchModal} onOpenChange={(open) => !open && setMismatchModal(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="size-4 text-amber-500" />
              Identitätsfelder geändert
            </DialogTitle>
            <DialogDescription>
              Dieses Dokument schlägt Änderungen an Patienten-Identitätsfeldern vor.
              Möglicherweise gehört es zu einem anderen Patienten.
            </DialogDescription>
          </DialogHeader>
          {mismatchModal && (
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="text-muted-foreground border-b">
                  <th className="text-left py-1 pr-3 font-medium">Feld</th>
                  <th className="text-left py-1 pr-3 font-medium">Aktuell</th>
                  <th className="text-left py-1 font-medium">Vorschlag</th>
                </tr>
              </thead>
              <tbody>
                {mismatchModal.map((c) => (
                  <tr key={c.feld} className="border-b">
                    <td className="py-1.5 pr-3 font-medium">
                      {STAMMDATEN_FELD_LABELS[c.feld] ?? c.feld}
                    </td>
                    <td className="py-1.5 pr-3 text-muted-foreground">{c.current}</td>
                    <td className="py-1.5 font-medium">{c.proposed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setMismatchModal(null)}
              disabled={applying}
            >
              Abbrechen
            </Button>
            <Button
              variant="destructive"
              onClick={handleForceApply}
              disabled={applying}
            >
              {applying ? "Wird angewendet…" : "Trotzdem anwenden"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
