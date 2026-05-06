import { useState } from "react";
import { ChevronDown, ChevronRight, Loader2, GraduationCap } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import RuleCandidateCard from "./RuleCandidateCard";
import { rebuildLearnRule, saveLearnRules } from "../api/brief";
import type {
  ConflictResolution,
  LearnFromEditsResponse,
  LearnRuleCandidate,
} from "../types";

interface ConvertedCandidate {
  section: string;
  rule_text: string;
  reasoning: string;
  anchor: string;
  conflict: null;
  fromTrivial: true;
}

type CandidateItem = LearnRuleCandidate | ConvertedCandidate;

interface CardState {
  accepted: boolean;
  ruleText: string;
  conflictResolution: ConflictResolution | null;
  discarded: boolean;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  response: LearnFromEditsResponse;
  domain: string;
  section?: string;
  sections?: readonly string[];
  onRulesSaved: () => void;
}

export default function RuleReviewModal({
  open,
  onOpenChange,
  response,
  domain,
  section,
  sections,
  onRulesSaved,
}: Props) {
  const [candidates, setCandidates] = useState<CandidateItem[]>(() => response.rule_candidates);
  const [cardStates, setCardStates] = useState<CardState[]>(() =>
    response.rule_candidates.map((c) => ({
      accepted: true,
      ruleText: c.rule_text,
      conflictResolution: null,
      discarded: false,
    }))
  );
  const [trivialExpanded, setTrivialExpanded] = useState(false);
  const [saving, setSaving] = useState(false);

  const [trivialSections, setTrivialSections] = useState<string[]>(
    response.trivial_changes.map(() => "")
  );
  const [trivialRuleTexts, setTrivialRuleTexts] = useState<string[]>(
    response.trivial_changes.map(() => "")
  );

  function updateCardState(idx: number, patch: Partial<CardState>) {
    setCardStates((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  }

  function handleDiscard(idx: number) {
    updateCardState(idx, { discarded: true, accepted: false });
  }

  function handleConvertTrivial(trivialIdx: number) {
    const sectionVal = trivialSections[trivialIdx];
    const ruleText = trivialRuleTexts[trivialIdx];
    if (!sectionVal || !ruleText.trim()) {
      toast.error("Bitte Sektion und Regeltext ausfüllen.");
      return;
    }
    const trivialChange = response.trivial_changes[trivialIdx];
    const newCandidate: ConvertedCandidate = {
      section: sectionVal,
      rule_text: ruleText.trim(),
      reasoning: "",
      anchor: trivialChange.anchor,
      conflict: null,
      fromTrivial: true,
    };
    setCandidates((prev) => [...prev, newCandidate]);
    setCardStates((prev) => [
      ...prev,
      { accepted: false, ruleText: ruleText.trim(), conflictResolution: null, discarded: false },
    ]);
  }

  async function handleRebuild(idx: number, clarification: string) {
    const candidate = candidates[idx];
    const state = cardStates[idx];
    try {
      const data = await rebuildLearnRule(domain, section, {
        section: candidate.section,
        original_rule_text: state.ruleText,
        original_reasoning: candidate.reasoning,
        anchor: candidate.anchor,
        clarification,
      });
      updateCardState(idx, { ruleText: data.rule_text });
      setCandidates((prev) =>
        prev.map((c, i) =>
          i === idx ? { ...c, reasoning: data.reasoning, rule_text: data.rule_text } : c
        )
      );
    } catch {
      toast.error("Re-Build fehlgeschlagen.");
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      const rulesToAdd: { section: string; rule_text: string }[] = [];
      const ruleIdsToDelete: string[] = [];

      cardStates.forEach((state, idx) => {
        if (!state.accepted || state.discarded) return;
        const candidate = candidates[idx];
        if (state.conflictResolution === "discard_new") return;

        rulesToAdd.push({ section: candidate.section, rule_text: state.ruleText });

        if (
          state.conflictResolution === "replace" &&
          candidate.conflict &&
          candidate.conflict.conflicting_rule_id
        ) {
          ruleIdsToDelete.push(candidate.conflict.conflicting_rule_id);
        }
      });

      if (rulesToAdd.length === 0) {
        toast.info("Keine Regeln zum Speichern ausgewählt.");
        return;
      }

      const data = await saveLearnRules(domain, section, rulesToAdd, ruleIdsToDelete);
      toast.success(`${data.saved_count} Regel${data.saved_count !== 1 ? "n" : ""} gespeichert.`);
      onRulesSaved();
      onOpenChange(false);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const visibleCards = candidates.map((c, i) => ({ c, state: cardStates[i], idx: i }))
    .filter(({ state }) => !state.discarded);

  const acceptedCount = cardStates.filter((s) => s.accepted && !s.discarded).length;
  const ruleCount = response.rule_candidates.length;
  const trivialCount = response.trivial_changes.length;

  return (
    <Dialog open={open} onOpenChange={(o) => !saving && onOpenChange(o)}>
      <DialogContent className="max-w-3xl flex flex-col max-h-[85vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GraduationCap className="size-4" />
            Vorgeschlagene Regeln
          </DialogTitle>
          <p className="text-xs text-muted-foreground mt-0.5">
            {ruleCount} Regel{ruleCount !== 1 ? "n" : ""}
            {trivialCount > 0 && `, ${trivialCount} triviale Änderung${trivialCount !== 1 ? "en" : ""}`}
          </p>
        </DialogHeader>

        <ScrollArea className="flex-1 overflow-y-auto pr-1">
          <div className="space-y-3 pb-2">
            {visibleCards.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-6">
                Alle Regelvorschläge verworfen.
              </p>
            )}
            {visibleCards.map(({ c, state, idx }) => (
              <RuleCandidateCard
                key={idx}
                candidate={c}
                accepted={state.accepted}
                onToggleAccept={(v) => updateCardState(idx, { accepted: v })}
                onRuleTextChange={(t) => updateCardState(idx, { ruleText: t })}
                onDiscard={() => handleDiscard(idx)}
                conflictResolution={state.conflictResolution}
                onConflictResolve={(res) => updateCardState(idx, { conflictResolution: res })}
                onRebuild={(clarification) => handleRebuild(idx, clarification)}
              />
            ))}

            {trivialCount > 0 && (
              <div className="border rounded-md">
                <button
                  className="w-full flex items-center justify-between px-3 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                  onClick={() => setTrivialExpanded((v) => !v)}
                >
                  <span>{trivialCount} triviale Änderung{trivialCount !== 1 ? "en" : ""}</span>
                  {trivialExpanded
                    ? <ChevronDown className="size-3.5" />
                    : <ChevronRight className="size-3.5" />
                  }
                </button>
                {trivialExpanded && (
                  <div className="border-t px-3 pb-3 space-y-3">
                    {response.trivial_changes.map((tc, tidx) => (
                      <div key={tidx} className="pt-3 space-y-2">
                        <p className="text-xs text-foreground">{tc.description}</p>
                        {tc.anchor && (
                          <p className="text-xs text-muted-foreground border-l-2 border-muted pl-2 font-mono">
                            „{tc.anchor}"
                          </p>
                        )}
                        <div className="flex gap-2 items-end">
                          <div className="flex-1 space-y-1">
                            {sections ? (
                              <Select
                                value={trivialSections[tidx]}
                                onValueChange={(v) =>
                                  setTrivialSections((prev) => prev.map((s, i) => i === tidx ? v : s))
                                }
                              >
                                <SelectTrigger className="h-7 text-xs">
                                  <SelectValue placeholder="Sektion wählen…" />
                                </SelectTrigger>
                                <SelectContent>
                                  {sections.map((s) => (
                                    <SelectItem key={s} value={s} className="text-xs">{s}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            ) : (
                              <Input
                                value={trivialSections[tidx]}
                                onChange={(e) =>
                                  setTrivialSections((prev) => prev.map((s, i) => i === tidx ? e.target.value : s))
                                }
                                className="h-7 text-xs"
                                placeholder="Sektion…"
                              />
                            )}
                            <Textarea
                              value={trivialRuleTexts[tidx]}
                              onChange={(e) =>
                                setTrivialRuleTexts((prev) => prev.map((t, i) => i === tidx ? e.target.value : t))
                              }
                              rows={1}
                              className="resize-none text-xs"
                              placeholder="Regeltext formulieren…"
                            />
                          </div>
                          <Button
                            size="xs"
                            variant="outline"
                            className="text-xs shrink-0"
                            onClick={() => handleConvertTrivial(tidx)}
                          >
                            Zur Regel
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </ScrollArea>

        <DialogFooter className="border-t pt-3">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Abbrechen
          </Button>
          <Button
            onClick={handleSave}
            disabled={saving || acceptedCount === 0}
          >
            {saving
              ? <><Loader2 className="size-3.5 animate-spin" /> Speichere…</>
              : `${acceptedCount > 0 ? `${acceptedCount} Regel${acceptedCount !== 1 ? "n" : ""}` : "Auswählen"} übernehmen`
            }
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
