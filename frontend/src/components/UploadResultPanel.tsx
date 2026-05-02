import { useState } from "react";
import ProposalCard, { type Proposal } from "./ProposalCard";

export type { Proposal };

export interface ToolResult {
  tool: string;
  ok: boolean;
  summary?: string;
  error?: string;
}

interface Props {
  fileName: string;
  summary: string;
  proposals: Proposal[];
  patientId: string;
  onComplete: (results: ToolResult[]) => void;
  onDiscard: () => void;
}

export default function UploadResultPanel({
  fileName,
  summary,
  proposals,
  patientId,
  onComplete,
  onDiscard,
}: Props) {
  // Alle Proposals sind standardmäßig ausgewählt (selected[id] = undefined → true)
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  // Arzt kann Proposal-Argumente vor dem Übernehmen bearbeiten
  const [editedArgs, setEditedArgs] = useState<Record<string, Record<string, string>>>({});
  const [applying, setApplying] = useState(false);

  // undefined → noch nicht explizit abgewählt → gilt als ausgewählt
  function isSelected(id: string): boolean {
    return selected[id] !== false;
  }

  function toggleSelected(id: string) {
    setSelected((prev) => ({ ...prev, [id]: !isSelected(id) }));
  }

  function handleArgsChange(id: string, args: Record<string, string>) {
    setEditedArgs((prev) => ({ ...prev, [id]: args }));
  }

  const selectedCount = proposals.filter((p) => isSelected(p.id)).length;

  async function handleApply() {
    setApplying(true);
    // Nur ausgewählte Proposals übernehmen; editedArgs hat Vorrang vor den Original-Args
    const calls = proposals
      .filter((p) => isSelected(p.id))
      .map((p) => ({
        tool: p.tool,
        args: editedArgs[p.id] ?? p.args,
      }));

    try {
      const res = await fetch(`/api/patients/${patientId}/apply-tools`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ calls }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      onComplete(data.results as ToolResult[]);
    } catch (e) {
      onComplete([
        { tool: "apply", ok: false, error: (e as Error).message },
      ]);
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white text-sm overflow-hidden w-full max-w-[90%]">
      {/* Header */}
      <div className="px-3 py-2 border-b border-gray-100 bg-gray-50">
        <p className="font-medium text-gray-800 truncate">📎 {fileName}</p>
        {summary && <p className="mt-0.5 text-xs text-gray-500">{summary}</p>}
      </div>

      {/* Proposal list */}
      {proposals.length === 0 ? (
        <p className="px-3 py-4 text-xs text-gray-400 text-center">
          Keine Vorschläge erkannt.
        </p>
      ) : (
        <div className="px-3 py-2 space-y-2 max-h-96 overflow-y-auto">
          {proposals.map((p) => (
            <ProposalCard
              key={p.id}
              proposal={p}
              selected={isSelected(p.id)}
              onToggle={() => toggleSelected(p.id)}
              onArgsChange={(args) => handleArgsChange(p.id, args)}
            />
          ))}
        </div>
      )}

      {/* Footer */}
      <div className="px-3 py-2 border-t border-gray-100 flex items-center justify-between gap-2">
        <span className="text-xs text-gray-500">
          {selectedCount} von {proposals.length} Vorschlägen übernehmen
        </span>
        <div className="flex gap-2">
          <button
            onClick={onDiscard}
            disabled={applying}
            className="px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100 rounded-lg disabled:opacity-40"
          >
            Verwerfen
          </button>
          <button
            onClick={handleApply}
            disabled={applying || selectedCount === 0}
            className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {applying ? "Wird übernommen…" : "Übernehmen"}
          </button>
        </div>
      </div>
    </div>
  );
}
