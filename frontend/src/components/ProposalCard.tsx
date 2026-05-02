import { useState } from "react";

export interface Proposal {
  id: string;
  tool: string;
  args: Record<string, string>;
  source_quote: string;
}

interface Props {
  proposal: Proposal;
  selected: boolean;
  onToggle: () => void;
  onArgsChange: (args: Record<string, string>) => void;
}

const TOOL_LABELS: Record<string, string> = {
  add_behandlungsdiagnose: "Behandlungsdiagnose",
  add_verlaufsdiagnose: "Verlaufsdiagnose",
  add_vorbekannte_diagnose: "Vorbekannte Diagnose",
  add_prozedur: "Prozedur",
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

function getInputType(key: string, value: string): "date" | "textarea" | "text" {
  if (key.endsWith("datum") || ["start", "ende", "beginn"].includes(key)) return "date";
  if (["text", "indikation", "bezeichnung"].includes(key) && value.length > 60)
    return "textarea";
  return "text";
}

function getMainText(args: Record<string, string>): string {
  return (
    args.text ??
    args.bezeichnung ??
    args.wert ??
    Object.values(args)[0] ??
    ""
  );
}

export default function ProposalCard({ proposal, selected, onToggle, onArgsChange }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [showQuote, setShowQuote] = useState(false);
  const [localArgs, setLocalArgs] = useState<Record<string, string>>(proposal.args);

  const label = TOOL_LABELS[proposal.tool] ?? proposal.tool;
  const mainText = getMainText(localArgs);
  const shortSummary = mainText.length > 60 ? mainText.slice(0, 60) + "…" : mainText;

  function handleArgChange(key: string, value: string) {
    const next = { ...localArgs, [key]: value };
    setLocalArgs(next);
    onArgsChange(next);
  }

  return (
    <div className={`rounded-lg border text-sm transition-colors ${
      selected ? "border-blue-200 bg-blue-50" : "border-gray-200 bg-gray-50 opacity-60"
    }`}>
      {/* Header row */}
      <div className="flex items-start gap-2 px-3 py-2">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          className="mt-0.5 shrink-0 accent-blue-600"
        />
        <div className="flex-1 min-w-0">
          <span className="font-medium text-gray-800">{label}</span>
          {shortSummary && (
            <span className="ml-2 text-gray-500 truncate">{shortSummary}</span>
          )}
        </div>
        <div className="flex gap-1 shrink-0">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="rounded px-2 py-0.5 text-xs text-blue-600 hover:bg-blue-100"
          >
            {expanded ? "Schließen" : "Bearbeiten"}
          </button>
          {proposal.source_quote && (
            <button
              onClick={() => setShowQuote((v) => !v)}
              className="rounded px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-200"
            >
              {showQuote ? "▲ Quelle" : "▼ Quelle"}
            </button>
          )}
        </div>
      </div>

      {/* Edit mode */}
      {expanded && (
        <div className="border-t border-blue-100 px-3 py-2 space-y-2">
          {Object.entries(localArgs).map(([key, value]) => {
            const inputType = getInputType(key, value);
            return (
              <div key={key}>
                <label className="block text-xs font-medium text-gray-600 mb-0.5">{key}</label>
                {inputType === "textarea" ? (
                  <textarea
                    value={value}
                    onChange={(e) => handleArgChange(key, e.target.value)}
                    rows={3}
                    className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400 resize-none"
                  />
                ) : (
                  <input
                    type={inputType}
                    value={value}
                    onChange={(e) => handleArgChange(key, e.target.value)}
                    className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400"
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Source quote */}
      {showQuote && proposal.source_quote && (
        <div className="border-t border-gray-100 px-3 py-2">
          <p className="text-xs text-gray-400 mb-0.5">Quelle:</p>
          <p className="text-xs italic text-gray-500">{proposal.source_quote}</p>
        </div>
      )}
    </div>
  );
}
