import { useState } from "react";
import { ChevronDown, ChevronRight, X, Loader2, WrapText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { ConflictResolution, LearnRuleCandidate } from "../types";

interface Props {
  candidate: LearnRuleCandidate;
  accepted: boolean;
  onToggleAccept: (accepted: boolean) => void;
  onRuleTextChange: (text: string) => void;
  onDiscard: () => void;
  conflictResolution: ConflictResolution | null;
  onConflictResolve: (res: ConflictResolution) => void;
  onRebuild?: (clarification: string) => Promise<void>;
}

const SECTION_COLORS: Record<string, string> = {
  "Operationen & Prozeduren":   "bg-red-100 text-red-800 border-red-200",
  "Behandlungsdiagnosen":        "bg-blue-100 text-blue-800 border-blue-200",
  "Relevante Nebendiagnosen":    "bg-slate-100 text-slate-700 border-slate-200",
  "Kardiale Funktion":           "bg-purple-100 text-purple-800 border-purple-200",
  "Antikoagulation":             "bg-orange-100 text-orange-800 border-orange-200",
  "Antimikrobielle Therapie":    "bg-violet-100 text-violet-800 border-violet-200",
  "Befunde":                     "bg-teal-100 text-teal-800 border-teal-200",
  "Therapieziel / Patientenwille": "bg-emerald-100 text-emerald-800 border-emerald-200",
};

export default function RuleCandidateCard({
  candidate,
  accepted,
  onToggleAccept,
  onRuleTextChange,
  onDiscard,
  conflictResolution,
  onConflictResolve,
  onRebuild,
}: Props) {
  const [ruleText, setRuleText] = useState(candidate.rule_text);
  const [showClarification, setShowClarification] = useState(false);
  const [clarification, setClarification] = useState("");
  const [rebuilding, setRebuilding] = useState(false);

  const hasConflict = !!candidate.conflict;
  const conflictResolved = !hasConflict || conflictResolution !== null;
  const canAccept = conflictResolved && conflictResolution !== "discard_new";

  const cardStyle = accepted
    ? "border-blue-200 bg-blue-50/40"
    : "border-border bg-muted/20 opacity-70";

  async function handleRebuild() {
    if (!clarification.trim()) return;
    setRebuilding(true);
    try {
      await onRebuild!(clarification.trim());
      setClarification("");
      setShowClarification(false);
    } finally {
      setRebuilding(false);
    }
  }

  function handleRuleTextChange(val: string) {
    setRuleText(val);
    onRuleTextChange(val);
  }

  return (
    <div className={cn("rounded-md border text-sm transition-colors", cardStyle)}>
      {/* Header */}
      <div className="flex items-start gap-2 px-3 py-2.5">
        <Checkbox
          checked={accepted}
          disabled={!canAccept}
          onCheckedChange={(v) => onToggleAccept(v === true)}
          className="mt-0.5 shrink-0"
        />
        <div className="flex-1 min-w-0">
          <Badge
            variant="outline"
            className={cn("text-xs mb-1.5", SECTION_COLORS[candidate.section] ?? "bg-gray-100 text-gray-700 border-gray-200")}
          >
            {candidate.section}
          </Badge>
        </div>
        <Button
          variant="ghost"
          size="xs"
          onClick={onDiscard}
          className="text-muted-foreground hover:text-destructive shrink-0"
          title="Verwerfen"
        >
          <X className="size-3.5" />
        </Button>
      </div>

      {/* Konflikt-Box */}
      {hasConflict && (
        <div className="mx-3 mb-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2">
          <p className="text-xs font-medium text-amber-900 mb-1">Konflikt mit bestehender Regel</p>
          <p className="text-xs text-amber-800 mb-2">{candidate.conflict!.explanation}</p>
          <div className="flex gap-1.5 flex-wrap">
            <Button
              size="xs"
              variant={conflictResolution === "replace" ? "default" : "outline"}
              className="text-xs"
              onClick={() => onConflictResolve("replace")}
            >
              Alte ersetzen
            </Button>
            <Button
              size="xs"
              variant={conflictResolution === "keep_both" ? "default" : "outline"}
              className="text-xs"
              onClick={() => onConflictResolve("keep_both")}
            >
              Beide behalten
            </Button>
            <Button
              size="xs"
              variant={conflictResolution === "discard_new" ? "destructive" : "outline"}
              className="text-xs"
              onClick={() => onConflictResolve("discard_new")}
            >
              Neue verwerfen
            </Button>
          </div>
        </div>
      )}

      {/* rule_text (editierbar) */}
      <div className="px-3 pb-2">
        <Textarea
          value={ruleText}
          onChange={(e) => handleRuleTextChange(e.target.value)}
          rows={2}
          className="resize-none text-sm font-medium"
          placeholder="Regeltext…"
        />
      </div>

      {/* reasoning (read-only) */}
      {candidate.reasoning && (
        <div className="px-3 pb-2">
          <p className="text-xs text-muted-foreground italic border-l-2 border-muted pl-2">
            {candidate.reasoning}
          </p>
        </div>
      )}

      {/* anchor (read-only Zitat) */}
      {candidate.anchor && (
        <div className="px-3 pb-2">
          <p className="text-xs text-muted-foreground border-l-2 border-primary/30 pl-2 font-mono">
            „{candidate.anchor}"
          </p>
        </div>
      )}

      {/* Klarstellung toggle + rebuild */}
      {onRebuild && (
        <div className="px-3 pb-2.5 border-t pt-2">
          <Button
            variant="ghost"
            size="xs"
            className="text-xs text-muted-foreground"
            onClick={() => setShowClarification((v) => !v)}
          >
            {showClarification
              ? <><ChevronDown className="size-3" /> Klarstellung ausblenden</>
              : <><ChevronRight className="size-3" /> Klarstellung hinzufügen</>
            }
          </Button>
          {showClarification && (
            <div className="mt-2 space-y-2">
              <Textarea
                value={clarification}
                onChange={(e) => setClarification(e.target.value)}
                rows={2}
                className="resize-none text-xs"
                placeholder="Was soll die Regel genauer erfassen?"
              />
              <Button
                size="xs"
                variant="outline"
                onClick={handleRebuild}
                disabled={rebuilding || !clarification.trim()}
              >
                {rebuilding
                  ? <><Loader2 className="size-3 animate-spin" /> Verfeinere…</>
                  : <><WrapText className="size-3" /> Re-Build mit Klarstellung</>
                }
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
