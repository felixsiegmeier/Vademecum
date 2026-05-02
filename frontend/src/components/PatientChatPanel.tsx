import { useRef, useState, useEffect } from "react";
import UploadResultPanel, { type Proposal, type ToolResult } from "./UploadResultPanel";

// ── API-Typen (was ans Backend geht / was zurückkommt) ────────────────────────

type ToolCall = {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
};

type ApiMessage = {
  role: "user" | "assistant" | "tool";
  content: string | null;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
};

// ── Anzeigetypen (nur im Frontend, nie ans Backend) ──────────────────────────

// Upload-Ergebnis wartet auf Bestätigung des Arztes ("pending"),
// wurde angewendet ("applied") oder verworfen ("discarded")
type UploadResultEntry = {
  kind: "upload-result";
  id: string;
  fileName: string;
  summary: string;
  proposals: Proposal[];
  status: "pending" | "applied" | "discarded";
};

// Zeigt das Ergebnis eines einzelnen angewendeten Tool-Calls an (z.B. "Diagnose ergänzt")
type ToolMarkerEntry = {
  kind: "tool-marker";
  tool: string;
  ok: boolean;
  summary: string;
};

// Die Chat-History enthält sowohl echte API-Nachrichten als auch reine Anzeige-Einträge
type HistoryEntry = ApiMessage | UploadResultEntry | ToolMarkerEntry;

function isApiMessage(e: HistoryEntry): e is ApiMessage {
  return "role" in e;
}

// ── Globaler History-Store ────────────────────────────────────────────────────
// Chat-History wird pro Patient in einer Map gehalten (nicht in React-State),
// damit sie beim Tab-Wechsel erhalten bleibt ohne Backend-Persistenz.
// Zurücksetzen passiert nur durch explizites Löschen (aktuell nicht implementiert).
const historyStore = new Map<string, HistoryEntry[]>();

// ── Hilfsfunktionen ───────────────────────────────────────────────────────────

// Wandelt einen Tool-Call in eine menschenlesbare Zusammenfassung um (für die Chat-Bubbles)
function summarizeToolCall(name: string, argsJson: string): string {
  let args: Record<string, string> = {};
  try {
    args = JSON.parse(argsJson);
  } catch {
    /* ignore */
  }
  switch (name) {
    case "add_behandlungsdiagnose":
      return `Behandlungsdiagnose: ${args.text}`;
    case "add_verlaufsdiagnose":
      return `Verlaufsdiagnose: ${args.text}`;
    case "add_vorbekannte_diagnose":
      return `Vorbekannte Diagnose: ${args.text}`;
    case "add_prozedur":
      return `Prozedur (${args.datum}): ${args.text}`;
    case "add_befund":
      return `Befund (${args.art}, ${args.datum}): ${args.text}`;
    case "add_therapie":
      return `Therapie [${args.kategorie}]: ${args.bezeichnung} ab ${args.beginn}${args.indikation ? ` (${args.indikation})` : ""}`;
    case "add_verlaufseintrag":
      return `Verlaufseintrag (${args.datum})`;
    case "update_anamnese":
      return `Anamnese aktualisiert`;
    case "delete_entry":
      return `Eintrag gelöscht (id=${args.id})`;
    case "update_therapieziel":
      return `Therapieziel: ${args.text}`;
    case "update_status":
      return `Aktivstatus: ${args.aktiv ? "aktiv" : "inaktiv"}`;
    case "update_bettplatz":
      return `Bettplatz: ${args.bettplatz}`;
    case "update_verlegungsziel":
      return `Verlegungsziel: ${args.verlegungsziel}`;
    default:
      return `${name}(${argsJson})`;
  }
}

// Rendert einen einzelnen Chat-Eintrag — unterscheidet zwischen API-Messages und Display-Entries
function renderEntry(
  entry: HistoryEntry,
  index: number,
  patientId: string,
  onUploadComplete: (id: string, results: ToolResult[]) => void,
  onUploadDiscard: (id: string) => void,
) {
  // Tool-Marker: kleines Badge nach Upload-Apply (Erfolg = amber, Fehler = rot)
  if ("kind" in entry && entry.kind === "tool-marker") {
    return (
      <div key={index} className="flex justify-start">
        <div className={`max-w-[80%] rounded-xl border px-3 py-2 text-sm ${
          entry.ok
            ? "bg-amber-50 border-amber-200 text-amber-800"
            : "bg-red-50 border-red-200 text-red-800"
        }`}>
          <div className="flex items-start gap-1.5">
            <span className="mt-0.5 shrink-0">{entry.ok ? "🔧" : "⚠️"}</span>
            <span>{entry.summary}</span>
          </div>
        </div>
      </div>
    );
  }

  // Upload-Ergebnis: interaktive Karte mit Proposals (pending) oder Status-Badge
  if ("kind" in entry && entry.kind === "upload-result") {
    if (entry.status === "pending") {
      return (
        <div key={index} className="flex justify-start">
          <UploadResultPanel
            fileName={entry.fileName}
            summary={entry.summary}
            proposals={entry.proposals}
            patientId={patientId}
            onComplete={(results) => onUploadComplete(entry.id, results)}
            onDiscard={() => onUploadDiscard(entry.id)}
          />
        </div>
      );
    }
    if (entry.status === "applied") {
      return (
        <div key={index} className="flex justify-start">
          <div className="max-w-[80%] rounded-xl bg-green-50 border border-green-200 px-3 py-2 text-sm text-green-700">
            📎 {entry.fileName} — Vorschläge angewendet
          </div>
        </div>
      );
    }
    // discarded
    return (
      <div key={index} className="flex justify-start">
        <div className="max-w-[80%] rounded-xl bg-gray-50 border border-gray-200 px-3 py-2 text-sm text-gray-400">
          📎 {entry.fileName} — Verworfen
        </div>
      </div>
    );
  }

  // Echte API-Nachrichten
  const m = entry as ApiMessage;

  // Tool-Antworten (role: "tool") werden nicht angezeigt — nur für das LLM relevant
  if (m.role === "tool") return null;

  if (m.role === "user") {
    return (
      <div key={index} className="flex justify-end">
        <div className="max-w-[80%] rounded-xl bg-blue-600 px-3 py-2 text-sm text-white">
          {m.content}
        </div>
      </div>
    );
  }

  if (m.role === "assistant") {
    // Tool-Calls des Assistenten: Liste der ausgeführten Aktionen anzeigen
    if (m.tool_calls && m.tool_calls.length > 0) {
      return (
        <div key={index} className="flex justify-start">
          <div className="max-w-[80%] rounded-xl bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-800 space-y-1">
            {m.tool_calls.map((tc) => (
              <div key={tc.id} className="flex items-start gap-1.5">
                <span className="mt-0.5 shrink-0">🔧</span>
                <span>{summarizeToolCall(tc.function.name, tc.function.arguments)}</span>
              </div>
            ))}
          </div>
        </div>
      );
    }
    // Normale Text-Antwort des Assistenten
    if (m.content) {
      return (
        <div key={index} className="flex justify-start">
          <div className="max-w-[80%] rounded-xl bg-white border border-gray-200 px-3 py-2 text-sm text-gray-800">
            {m.content}
          </div>
        </div>
      );
    }
  }

  return null;
}

// ── Komponente ────────────────────────────────────────────────────────────────

const ACCEPTED_MIME = ["application/pdf", "image/jpeg", "image/png"];

export function PatientChatPanel({ patientId }: { patientId: string }) {
  const [history, setHistory] = useState<HistoryEntry[]>(
    () => historyStore.get(patientId) ?? []
  );
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Bei Patient-Wechsel: History aus dem Store laden (erhalten Tab-Wechsel)
  useEffect(() => {
    setHistory(historyStore.get(patientId) ?? []);
  }, [patientId]);

  // Automatisch nach unten scrollen wenn neue Nachrichten kommen
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, busy]);

  async function handleSubmit() {
    if (!input.trim() || busy) return;

    // Optimistic UI: Nutzer-Nachricht sofort anzeigen, bevor Backend antwortet
    const userMsg: ApiMessage = { role: "user", content: input };
    const optimistic = [...history, userMsg];
    setHistory(optimistic);
    historyStore.set(patientId, optimistic);
    setInput("");
    setBusy(true);

    try {
      // Nur ApiMessages ans Backend schicken (keine Display-Only-Einträge)
      const apiMessages = optimistic.filter(isApiMessage);
      const res = await fetch(`/api/patients/${patientId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: apiMessages }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const detail = body?.detail ?? `HTTP ${res.status}`;
        throw new Error(typeof detail === "string" ? detail : `HTTP ${res.status}`);
      }
      const data = await res.json();
      // Backend gibt nur neue Nachrichten zurück (assistant + tool), nicht die ganze History
      const next = [...optimistic, ...(data.messages as ApiMessage[])];
      setHistory(next);
      historyStore.set(patientId, next);
    } catch (e) {
      const errMsg: ApiMessage = {
        role: "assistant",
        content: `Fehler: ${(e as Error).message}`,
      };
      const next = [...optimistic, errMsg];
      setHistory(next);
      historyStore.set(patientId, next);
    } finally {
      setBusy(false);
      textareaRef.current?.focus();
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  async function handleFileSelected(file: File) {
    if (!ACCEPTED_MIME.includes(file.type)) {
      const errMsg: ApiMessage = {
        role: "assistant",
        content: `Nicht unterstützter Dateityp: ${file.type || file.name}. Bitte PDF, JPG oder PNG wählen.`,
      };
      const next = [...history, errMsg];
      setHistory(next);
      historyStore.set(patientId, next);
      return;
    }

    // Datei-Nachricht sofort anzeigen
    const userMsg: ApiMessage = { role: "user", content: `[Datei: ${file.name}]` };
    const withUserMsg = [...history, userMsg];
    setHistory(withUserMsg);
    historyStore.set(patientId, withUserMsg);
    setBusy(true);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("patient_id", patientId);

    try {
      // Backend analysiert Dokument und gibt summary + proposals zurück
      const res = await fetch("/api/uploads", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json();

      // source_quote lebt in args — für ProposalCard auf Top-Level heben
      const proposals: Proposal[] = (
        data.proposals as Array<{ tool: string; args: Record<string, string> }>
      ).map((p, i) => ({
        id: `proposal-${Date.now()}-${i}`,
        tool: p.tool,
        args: p.args,
        source_quote: p.args.source_quote ?? "",
      }));

      // Proposal-Karte in den Chat einbetten (Arzt muss bestätigen)
      const uploadEntry: UploadResultEntry = {
        kind: "upload-result",
        id: `upload-${Date.now()}`,
        fileName: file.name,
        summary: data.summary,
        proposals,
        status: "pending",
      };
      const next = [...withUserMsg, uploadEntry];
      setHistory(next);
      historyStore.set(patientId, next);
    } catch (e) {
      const errMsg: ApiMessage = {
        role: "assistant",
        content: `Upload-Fehler: ${(e as Error).message}`,
      };
      const next = [...withUserMsg, errMsg];
      setHistory(next);
      historyStore.set(patientId, next);
    } finally {
      setBusy(false);
    }
  }

  // Arzt hat "Übernehmen" geklickt: Upload-Karte auf "applied" setzen + Ergebnis-Marker anzeigen
  function handleUploadComplete(entryId: string, results: ToolResult[]) {
    setHistory((prev) => {
      const updated = prev.map((e) =>
        "kind" in e && e.kind === "upload-result" && e.id === entryId
          ? { ...e, status: "applied" as const }
          : e
      );
      const markers: ToolMarkerEntry[] = results.map((r) => ({
        kind: "tool-marker" as const,
        tool: r.tool,
        ok: r.ok,
        summary: r.ok ? (r.summary ?? r.tool) : (r.error ?? "Fehler"),
      }));
      const applied = results.filter((r) => r.ok).length;
      const finalMsg: ApiMessage = {
        role: "assistant",
        content: `${applied} von ${results.length} Einträgen übernommen.`,
      };
      const next = [...updated, ...markers, finalMsg];
      historyStore.set(patientId, next);
      return next;
    });
  }

  // Arzt hat "Verwerfen" geklickt
  function handleUploadDiscard(entryId: string) {
    setHistory((prev) => {
      const updated = prev.map((e) =>
        "kind" in e && e.kind === "upload-result" && e.id === entryId
          ? { ...e, status: "discarded" as const }
          : e
      );
      const discardMsg: ApiMessage = { role: "assistant", content: "Vorschläge verworfen." };
      const next = [...updated, discardMsg];
      historyStore.set(patientId, next);
      return next;
    });
  }

  return (
    <div className="flex flex-col h-full">
      {/* Nachrichtenliste */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {history.length === 0 && (
          <p className="text-center text-sm text-gray-400 mt-8">
            Visite, Befunde oder Fragen eingeben…
          </p>
        )}
        {history.map((entry, i) =>
          renderEntry(entry, i, patientId, handleUploadComplete, handleUploadDiscard)
        )}
        {busy && (
          <div className="flex justify-start">
            <div className="rounded-xl bg-white border border-gray-200 px-3 py-2 text-sm text-gray-400">
              Denkt nach…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Eingabezeile */}
      <div className="border-t bg-white px-4 py-3 flex gap-2 items-end">
        {/* Datei-Upload: verstecktes Input, getriggert durch den 📎-Button */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFileSelected(file);
            e.target.value = "";  // Input zurücksetzen damit dieselbe Datei nochmal gewählt werden kann
          }}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={busy}
          title="Dokument hochladen"
          className="shrink-0 rounded-lg border border-gray-300 px-3 py-2 text-gray-500 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          📎
        </button>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={busy}
          placeholder="Visite, Befunde, Fragen… (Enter = Senden, Shift+Enter = Zeilenumbruch)"
          rows={2}
          className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        />
        <button
          onClick={handleSubmit}
          disabled={busy || !input.trim()}
          className="shrink-0 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Senden
        </button>
      </div>
    </div>
  );
}
