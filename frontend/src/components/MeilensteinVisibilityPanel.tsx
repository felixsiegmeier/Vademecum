import { useEffect, useState } from "react";
import { Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { getLearnRules, deleteLearnRule, getSystemPrompt } from "../api/brief";
import type { StoredRule } from "../types";
import { MEILENSTEIN_SECTIONS } from "../types";

export default function MeilensteinVisibilityPanel() {
  const [activeTab, setActiveTab] = useState<"prompt" | "rules">("rules");

  // Base-Prompt
  const [promptContent, setPromptContent] = useState<string | null>(null);
  const [promptLoading, setPromptLoading] = useState(false);

  // Gelernte Regeln
  const [rules, setRules] = useState<StoredRule[] | null>(null);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (activeTab === "prompt" && promptContent === null && !promptLoading) {
      setPromptLoading(true);
      getSystemPrompt("meilenstein")
        .then((content) => setPromptContent(content))
        .catch(() => setPromptContent("Fehler beim Laden."))
        .finally(() => setPromptLoading(false));
    }
    if (activeTab === "rules" && rules === null && !rulesLoading) {
      loadRules();
    }
  }, [activeTab]);

  function loadRules() {
    setRulesLoading(true);
    getLearnRules("meilenstein")
      .then((rules) => setRules(rules))
      .catch(() => setRules([]))
      .finally(() => setRulesLoading(false));
  }

  async function deleteRule(id: string) {
    setDeletingIds((prev) => new Set(prev).add(id));
    try {
      await deleteLearnRule("meilenstein", undefined, id);
      setRules((prev) => prev?.filter((r) => r.id !== id) ?? null);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }

  // Regeln nach Sektion gruppieren (Reihenfolge aus MEILENSTEIN_SECTIONS)
  const rulesBySection = MEILENSTEIN_SECTIONS.map((section) => ({
    section,
    rules: (rules ?? []).filter((r) => r.section === section),
  })).filter(({ rules }) => rules.length > 0);

  return (
    <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "prompt" | "rules")}>
      <div className="border-t px-4 pt-2 pb-1">
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
          {rulesLoading && (
            <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" /> Lade Regeln…
            </div>
          )}
          {!rulesLoading && (rules === null || rulesBySection.length === 0) && (
            <p className="py-4 text-sm text-muted-foreground">Noch keine gespeicherten Regeln.</p>
          )}
          {rulesBySection.map(({ section, rules: sectionRules }) => (
            <div key={section} className="mb-3">
              <p className="text-xs font-medium text-muted-foreground mb-1">{section}</p>
              <div className="space-y-1">
                {sectionRules.map((rule) => (
                  <div
                    key={rule.id}
                    className="flex items-start gap-2 rounded-sm px-2 py-1.5 hover:bg-muted/40 group"
                  >
                    <span className="flex-1 text-xs">{rule.rule_text}</span>
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={() => deleteRule(rule.id)}
                      disabled={deletingIds.has(rule.id)}
                      className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive shrink-0 transition-opacity"
                    >
                      {deletingIds.has(rule.id)
                        ? <Loader2 className="size-3 animate-spin" />
                        : <Trash2 className="size-3" />
                      }
                    </Button>
                  </div>
                ))}
              </div>
              <Separator className="mt-2" />
            </div>
          ))}
        </ScrollArea>
      </TabsContent>

      <TabsContent value="prompt" className="mt-0">
        <ScrollArea className="h-48 px-4">
          {promptLoading && (
            <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" /> Lade Prompt…
            </div>
          )}
          {!promptLoading && promptContent !== null && (
            <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono py-2">
              {promptContent}
            </pre>
          )}
        </ScrollArea>
      </TabsContent>
    </Tabs>
  );
}
