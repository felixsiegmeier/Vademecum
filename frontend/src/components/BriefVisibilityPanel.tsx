import { useEffect, useState } from "react";
import { Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { getLearnRules, deleteLearnRule, getSystemPrompt } from "../api/brief";
import type { StoredRule } from "../types";

const BRIEF_SECTIONS = ["diagnosen", "anamnese", "therapie", "verlauf"] as const;
type BriefSection = typeof BRIEF_SECTIONS[number];

const SECTION_LABELS: Record<BriefSection, string> = {
  diagnosen: "Diagnosen",
  anamnese: "Anamnese",
  therapie: "Therapie",
  verlauf: "Verlauf",
};

interface SectionState {
  rules: StoredRule[] | null;
  rulesLoading: boolean;
  promptContent: string | null;
  promptLoading: boolean;
  deletingIds: Set<string>;
  activeTab: "rules" | "prompt";
}

function makeSectionState(): SectionState {
  return {
    rules: null,
    rulesLoading: false,
    promptContent: null,
    promptLoading: false,
    deletingIds: new Set(),
    activeTab: "rules",
  };
}

export default function BriefVisibilityPanel() {
  const [activeSection, setActiveSection] = useState<BriefSection>("diagnosen");
  const [sectionStates, setSectionStates] = useState<Record<BriefSection, SectionState>>(
    () => ({
      diagnosen: makeSectionState(),
      anamnese: makeSectionState(),
      therapie: makeSectionState(),
      verlauf: makeSectionState(),
    })
  );

  function patchSection(section: BriefSection, patch: Partial<SectionState>) {
    setSectionStates((prev) => ({
      ...prev,
      [section]: { ...prev[section], ...patch },
    }));
  }

  function patchSectionDeletingIds(section: BriefSection, updater: (prev: Set<string>) => Set<string>) {
    setSectionStates((prev) => ({
      ...prev,
      [section]: { ...prev[section], deletingIds: updater(prev[section].deletingIds) },
    }));
  }

  const state = sectionStates[activeSection];

  useEffect(() => {
    const s = sectionStates[activeSection];
    if (s.activeTab === "rules" && s.rules === null && !s.rulesLoading) {
      loadRules(activeSection);
    }
    if (s.activeTab === "prompt" && s.promptContent === null && !s.promptLoading) {
      loadPrompt(activeSection);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSection, state.activeTab]);

  function loadRules(section: BriefSection) {
    patchSection(section, { rulesLoading: true });
    getLearnRules("brief", section)
      .then((rules) => patchSection(section, { rules }))
      .catch(() => patchSection(section, { rules: [] }))
      .finally(() => patchSection(section, { rulesLoading: false }));
  }

  function loadPrompt(section: BriefSection) {
    patchSection(section, { promptLoading: true });
    getSystemPrompt("brief", section)
      .then((content) => patchSection(section, { promptContent: content }))
      .catch(() => patchSection(section, { promptContent: "Fehler beim Laden." }))
      .finally(() => patchSection(section, { promptLoading: false }));
  }

  async function deleteRule(section: BriefSection, id: string) {
    patchSectionDeletingIds(section, (prev) => new Set(prev).add(id));
    try {
      await deleteLearnRule("brief", section, id);
      setSectionStates((prev) => ({
        ...prev,
        [section]: {
          ...prev[section],
          rules: prev[section].rules?.filter((r) => r.id !== id) ?? null,
        },
      }));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      patchSectionDeletingIds(section, (prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }

  return (
    <div>
      {/* Section tabs */}
      <div className="border-t px-4 pt-2">
        <div className="flex gap-1">
          {BRIEF_SECTIONS.map((s) => (
            <button
              key={s}
              onClick={() => setActiveSection(s)}
              className={`px-3 py-1 text-xs rounded-t-sm transition-colors ${
                activeSection === s
                  ? "bg-background border border-b-background -mb-px font-medium"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {SECTION_LABELS[s]}
            </button>
          ))}
        </div>
      </div>

      {/* Inner tabs: Regeln / Prompt */}
      <Tabs
        value={state.activeTab}
        onValueChange={(v) => patchSection(activeSection, { activeTab: v as "rules" | "prompt" })}
      >
        <div className="border-t px-4 pt-1 pb-1">
          <TabsList className="h-7">
            <TabsTrigger value="rules" className="text-xs h-6 px-3">
              Gelernte Regeln
            </TabsTrigger>
            <TabsTrigger value="prompt" className="text-xs h-6 px-3">
              Base-Prompt
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="rules" className="mt-0">
          <ScrollArea className="h-48 px-4">
            {state.rulesLoading && (
              <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" /> Lade Regeln…
              </div>
            )}
            {!state.rulesLoading && (state.rules === null || state.rules.length === 0) && (
              <p className="py-4 text-sm text-muted-foreground">Noch keine gespeicherten Regeln.</p>
            )}
            {(state.rules ?? []).length > 0 && (
              <div className="mb-3 pt-2">
                <div className="space-y-1">
                  {(state.rules ?? []).map((rule) => (
                    <div
                      key={rule.id}
                      className="flex items-start gap-2 rounded-sm px-2 py-1.5 hover:bg-muted/40 group"
                    >
                      <span className="flex-1 text-xs">{rule.rule_text}</span>
                      <Button
                        variant="ghost"
                        size="xs"
                        onClick={() => deleteRule(activeSection, rule.id)}
                        disabled={state.deletingIds.has(rule.id)}
                        className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive shrink-0 transition-opacity"
                      >
                        {state.deletingIds.has(rule.id)
                          ? <Loader2 className="size-3 animate-spin" />
                          : <Trash2 className="size-3" />
                        }
                      </Button>
                    </div>
                  ))}
                </div>
                <Separator className="mt-2" />
              </div>
            )}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="prompt" className="mt-0">
          <ScrollArea className="h-48 px-4">
            {state.promptLoading && (
              <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" /> Lade Prompt…
              </div>
            )}
            {!state.promptLoading && state.promptContent !== null && (
              <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono py-2">
                {state.promptContent}
              </pre>
            )}
          </ScrollArea>
        </TabsContent>
      </Tabs>
    </div>
  );
}
