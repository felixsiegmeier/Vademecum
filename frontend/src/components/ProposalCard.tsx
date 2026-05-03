import { useState } from "react";
import {
  type ArgsRecord,
  type ArgValue,
  type Patient,
  type Proposal,
  type ToolCall,
  STAMMDATEN_FELD_LABELS,
  THERAPIE_KATEGORIEN,
  TOOL_LABELS,
} from "../types";
import { resolveById } from "../utils/resolveById";

interface Props {
  proposal: Proposal;
  patient: Patient | null;
  selected: boolean;
  onToggle: () => void;
  /** Args werden zurückgegeben — bei "update" via add_call, bei add/update_singleton via call. delete editiert nichts. */
  onArgsChange: (args: ArgsRecord) => void;
  /** Optional: Apply ist fehlgeschlagen — Inline-Fehler anzeigen. */
  failedSummary?: string | null;
}

const READONLY_KEYS = new Set(["source_quote", "id"]);
const DATE_KEY_HINTS = ["datum", "beginn", "ende", "geburtsdatum", "aufnahmedatum"];

function isDateKey(key: string): boolean {
  return DATE_KEY_HINTS.includes(key) || key.endsWith("datum");
}

function shorten(text: string, max = 60): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "…";
}

function getMainTextFromAdd(args: ArgsRecord, tool: string): string {
  if (tool === "add_therapie") return String(args.bezeichnung ?? "");
  return String(args.text ?? args.bezeichnung ?? "");
}

function getSingletonMainText(call: ToolCall): string {
  const { tool, args } = call;
  switch (tool) {
    case "update_anamnese":
    case "update_therapieziel":
      return String(args.text ?? "");
    case "update_status":
      return `aktiv: ${args.aktiv ? "ja" : "nein"}`;
    case "update_bettplatz":
      return String(args.bettplatz ?? "");
    case "update_verlegungsziel":
      return String(args.verlegungsziel ?? "");
    case "update_stammdaten": {
      const feld = String(args.feld ?? "");
      const wert = String(args.wert ?? "");
      const label = STAMMDATEN_FELD_LABELS[feld] ?? feld;
      return `${label}: ${wert}`;
    }
    default:
      return "";
  }
}

interface ArgFieldProps {
  argKey: string;
  value: ArgValue;
  onChange: (key: string, value: ArgValue) => void;
  readOnly?: boolean;
  isStammdatenFeld?: boolean;
}

function ArgField({ argKey, value, onChange, readOnly, isStammdatenFeld }: ArgFieldProps) {
  const ro = readOnly || READONLY_KEYS.has(argKey) || isStammdatenFeld;
  const label = (
    <label className="block text-xs font-medium text-gray-600 mb-0.5">{argKey}</label>
  );

  // Boolean (update_status.aktiv)
  if (typeof value === "boolean") {
    return (
      <div>
        {label}
        <label className="inline-flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={value}
            disabled={ro}
            onChange={(e) => onChange(argKey, e.target.checked)}
            className="accent-blue-600"
          />
          <span className="text-gray-700">{value ? "aktiv" : "inaktiv"}</span>
        </label>
      </div>
    );
  }

  // Therapie-Kategorie als Select
  if (argKey === "kategorie") {
    return (
      <div>
        {label}
        <select
          value={String(value ?? "")}
          disabled={ro}
          onChange={(e) => onChange(argKey, e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1 text-xs bg-white focus:outline-none focus:ring-1 focus:ring-blue-400 disabled:bg-gray-100 disabled:text-gray-500"
        >
          {Object.entries(THERAPIE_KATEGORIEN).map(([key, meta]) => (
            <option key={key} value={key}>
              {meta.label}
            </option>
          ))}
        </select>
      </div>
    );
  }

  const stringValue = String(value ?? "");

  // Source-Quote oder andere read-only Felder grau anzeigen
  if (ro) {
    return (
      <div>
        {label}
        <div className="w-full rounded border border-gray-200 bg-gray-100 px-2 py-1 text-xs text-gray-500 whitespace-pre-wrap break-words min-h-[1.5rem]">
          {stringValue || <span className="italic text-gray-400">(leer)</span>}
        </div>
      </div>
    );
  }

  if (isDateKey(argKey)) {
    return (
      <div>
        {label}
        <input
          type="date"
          value={stringValue}
          onChange={(e) => onChange(argKey, e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
      </div>
    );
  }

  if (stringValue.length > 60) {
    return (
      <div>
        {label}
        <textarea
          value={stringValue}
          rows={3}
          onChange={(e) => onChange(argKey, e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400 resize-none"
        />
      </div>
    );
  }

  return (
    <div>
      {label}
      <input
        type="text"
        value={stringValue}
        onChange={(e) => onChange(argKey, e.target.value)}
        className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400"
      />
    </div>
  );
}

function colorForType(type: Proposal["type"], selected: boolean): string {
  if (!selected) return "border-gray-200 bg-gray-50 opacity-50";
  switch (type) {
    case "delete":
      return "border-red-200 bg-red-50";
    case "update":
      return "border-amber-200 bg-amber-50";
    default:
      return "border-blue-200 bg-blue-50";
  }
}

export default function ProposalCard({
  proposal,
  patient,
  selected,
  onToggle,
  onArgsChange,
  failedSummary,
}: Props) {
  // Welche Args sind editierbar? add/update_singleton: call.args; update: add_call.args; delete: nichts.
  const editableSourceArgs: ArgsRecord | null =
    proposal.type === "update" ? (proposal.add_call?.args ?? null) :
    proposal.type === "delete" ? null :
    (proposal.call?.args ?? null);

  const [expanded, setExpanded] = useState(false);
  const [showQuote, setShowQuote] = useState(false);
  const [localArgs, setLocalArgs] = useState<ArgsRecord>(editableSourceArgs ?? {});

  function handleArgChange(key: string, value: ArgValue) {
    const next = { ...localArgs, [key]: value };
    setLocalArgs(next);
    onArgsChange(next);
  }

  // ── Header + mainText pro Discriminator bauen ──
  let header: React.ReactNode = null;
  let mainContent: React.ReactNode = null;
  let kategorieBadge: React.ReactNode = null;
  let sourceQuote = "";

  if (proposal.type === "add" && proposal.call) {
    const { tool, args } = proposal.call;
    header = TOOL_LABELS[tool] ?? tool;
    sourceQuote = String(args.source_quote ?? "");
    if (tool === "add_therapie") {
      const kat = String(args.kategorie ?? "");
      const meta = THERAPIE_KATEGORIEN[kat];
      if (meta) {
        kategorieBadge = (
          <span className={`ml-2 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${meta.color}`}>
            {meta.label}
          </span>
        );
      }
    }
    mainContent = <span className="text-gray-600">{shorten(getMainTextFromAdd(localArgs, tool))}</span>;
  } else if (proposal.type === "update_singleton" && proposal.call) {
    const { tool, args } = proposal.call;
    sourceQuote = String(args.source_quote ?? "");
    if (tool === "update_stammdaten") {
      header = TOOL_LABELS[tool];
      const feld = String(args.feld ?? "");
      const wert = String(args.wert ?? "");
      const label = STAMMDATEN_FELD_LABELS[feld] ?? feld;
      mainContent = <span className="text-gray-600">{shorten(`${label}: ${wert}`)}</span>;
    } else {
      header = TOOL_LABELS[tool] ?? tool;
      // Use localArgs so live edits reflect in the header text
      const previewCall: ToolCall = { tool, args: { ...args, ...localArgs } };
      mainContent = <span className="text-gray-600">{shorten(getSingletonMainText(previewCall))}</span>;
    }
  } else if (proposal.type === "update" && proposal.add_call && proposal.delete_call) {
    const addTool = proposal.add_call.tool;
    header = TOOL_LABELS[addTool] ?? addTool;
    sourceQuote = String(proposal.add_call.args.source_quote ?? "");
    if (addTool === "add_therapie") {
      const kat = String((localArgs.kategorie ?? proposal.add_call.args.kategorie) ?? "");
      const meta = THERAPIE_KATEGORIEN[kat];
      if (meta) {
        kategorieBadge = (
          <span className={`ml-2 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${meta.color}`}>
            {meta.label}
          </span>
        );
      }
    }
    const oldId = String(proposal.delete_call.args.id ?? "");
    const resolved = resolveById(patient, oldId);
    const newText = getMainTextFromAdd(localArgs, addTool);
    if (resolved) {
      mainContent = (
        <span className="text-gray-600">
          <span className="line-through text-gray-400">{shorten(resolved.text)}</span>
          <span className="mx-1.5 text-gray-400">→</span>
          <span className="font-medium text-gray-800">{shorten(newText)}</span>
        </span>
      );
    } else {
      mainContent = (
        <span className="text-gray-600">
          <span className="italic text-gray-400 line-through">
            Eintrag …{oldId.slice(-6)} (nicht im Stand auffindbar)
          </span>
          <span className="mx-1.5 text-gray-400">→</span>
          <span className="font-medium text-gray-800">{shorten(newText)}</span>
        </span>
      );
    }
  } else if (proposal.type === "delete" && proposal.call) {
    const args = proposal.call.args;
    sourceQuote = String(args.source_quote ?? "");
    const oldId = String(args.id ?? "");
    const resolved = resolveById(patient, oldId);
    header = resolved
      ? `${TOOL_LABELS["delete_entry"]} — ${resolved.section}`
      : TOOL_LABELS["delete_entry"];
    mainContent = resolved ? (
      <span className="line-through text-gray-500">{shorten(resolved.text)}</span>
    ) : (
      <span className="italic text-gray-400">
        Eintrag …{oldId.slice(-6)} <span>(nicht im Stand auffindbar)</span>
      </span>
    );
  }

  const colorClass = colorForType(proposal.type, selected);
  const isUpdate = proposal.type === "update";

  // Diff-View-Daten für Update-Gruppen
  const diffOldText = isUpdate && proposal.delete_call
    ? resolveById(patient, String(proposal.delete_call.args.id ?? ""))?.text ?? null
    : null;
  const diffOldId = isUpdate && proposal.delete_call
    ? String(proposal.delete_call.args.id ?? "")
    : "";

  return (
    <div className={`rounded-lg border text-sm transition-colors ${colorClass}`}>
      {/* Header row */}
      <div className="flex items-start gap-2 px-3 py-2">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          className="mt-0.5 shrink-0 accent-blue-600"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline">
            <span className="font-medium text-gray-800">{header}</span>
            {kategorieBadge}
          </div>
          {mainContent && <div className="mt-0.5 truncate">{mainContent}</div>}
        </div>
        <div className="flex gap-1 shrink-0">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="rounded px-2 py-0.5 text-xs text-blue-600 hover:bg-blue-100"
          >
            {expanded ? "Schließen" : isUpdate ? "Details" : proposal.type === "delete" ? "Details" : "Bearbeiten"}
          </button>
          {sourceQuote && (
            <button
              onClick={() => setShowQuote((v) => !v)}
              className="rounded px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-200"
            >
              {showQuote ? "▲ Quelle" : "▼ Quelle"}
            </button>
          )}
        </div>
      </div>

      {/* Edit / details mode */}
      {expanded && (
        <div className="border-t border-black/5 px-3 py-2 space-y-2">

          {/* delete: ID + source_quote read-only */}
          {proposal.type === "delete" && proposal.call && (
            <>
              <ArgField
                argKey="id"
                value={String(proposal.call.args.id ?? "")}
                onChange={() => {}}
                readOnly
              />
              <ArgField
                argKey="source_quote"
                value={String(proposal.call.args.source_quote ?? "")}
                onChange={() => {}}
                readOnly
              />
            </>
          )}

          {/* add / update_singleton: generischer Arg-Loop */}
          {(proposal.type === "add" || proposal.type === "update_singleton") && editableSourceArgs &&
            Object.entries(localArgs).map(([key, value]) => {
              const isStammFeld =
                proposal.type === "update_singleton" &&
                proposal.call?.tool === "update_stammdaten" &&
                key === "feld";
              return (
                <ArgField
                  key={key}
                  argKey={key}
                  value={value}
                  onChange={handleArgChange}
                  isStammdatenFeld={isStammFeld}
                />
              );
            })}

          {/* update: Diff-View (Alter Eintrag → Neuer Eintrag) + restliche Felder */}
          {isUpdate && proposal.add_call && (
            <>
              {/* Bisheriger Eintrag */}
              <div>
                <p className="text-xs font-medium text-red-600/80 mb-0.5">Bisheriger Eintrag</p>
                {diffOldText !== null ? (
                  <div className="w-full rounded border border-red-200 bg-red-50 px-2 py-1.5 text-xs text-gray-500 whitespace-pre-wrap break-words">
                    <s>{diffOldText}</s>
                  </div>
                ) : (
                  <div className="text-xs italic text-gray-400">
                    Eintrag …{diffOldId.slice(-6)} nicht im aktuellen Stand auffindbar.
                  </div>
                )}
              </div>

              {/* Neuer Eintrag (Merge, bearbeitbar) */}
              <div>
                <p className="text-xs font-medium text-blue-600 mb-0.5">Neuer Eintrag (Merge)</p>
                <textarea
                  value={String(localArgs.text ?? proposal.add_call.args.text ?? "")}
                  rows={4}
                  onChange={(e) => handleArgChange("text", e.target.value)}
                  className="w-full rounded border border-blue-200 bg-blue-50 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400 resize-none"
                />
              </div>

              {/* Restliche Felder (datum, source_quote) — ohne text */}
              {Object.entries(localArgs)
                .filter(([key]) => key !== "text")
                .map(([key, value]) => (
                  <ArgField key={key} argKey={key} value={value} onChange={handleArgChange} />
                ))}

              {/* zu löschende ID */}
              <ArgField
                argKey="(zu löschende ID)"
                value={diffOldId}
                onChange={() => {}}
                readOnly
              />
            </>
          )}
        </div>
      )}

      {/* Source quote */}
      {showQuote && sourceQuote && (
        <div className="border-t border-black/5 px-3 py-2">
          <p className="text-xs text-gray-400 mb-0.5">Quelle:</p>
          <p className="text-xs italic text-gray-500 whitespace-pre-wrap">{sourceQuote}</p>
        </div>
      )}

      {/* Apply-Fehler inline */}
      {failedSummary && (
        <div className="border-t border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          ⚠ {failedSummary}
        </div>
      )}
    </div>
  );
}
