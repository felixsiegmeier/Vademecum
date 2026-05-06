import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Brief, BriefSectionKey, LearnFromEditsResponse } from "../types";
import {
  generateBrief,
  getBrief,
  formatSapBefunde,
  regenerateSection,
  polishSection,
  saveSectionEdit,
  learnFromEdits,
  deleteBrief,
} from "../api/brief";
import BriefOnboarding from "./BriefOnboarding";
import BriefSection from "./BriefSection";
import BefundeSection from "./BefundeSection";
import BriefVisibilityPanel from "./BriefVisibilityPanel";
import RuleReviewModal from "./RuleReviewModal";

interface Props {
  patientId: string;
}

const GENERATABLE: BriefSectionKey[] = ["diagnosen", "anamnese", "therapie", "verlauf"];
const LEARNABLE: BriefSectionKey[] = ["diagnosen", "anamnese", "therapie", "verlauf"];

const SECTION_LABELS: Record<BriefSectionKey, string> = {
  diagnosen: "Diagnosen",
  anamnese: "Anamnese",
  therapie: "Therapie",
  befunde: "Befunde",
  verlauf: "Verlauf",
};

export default function BriefPanel({ patientId }: Props) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [generating, setGenerating] = useState<Partial<Record<BriefSectionKey, boolean>>>({});
  const [formatting, setFormatting] = useState(false);

  // Track content at last generate per section to detect edits
  const [lastGenerated, setLastGenerated] = useState<Partial<Record<BriefSectionKey, string>>>({});

  // Learn flow
  const [learning, setLearning] = useState<Partial<Record<BriefSectionKey, boolean>>>({});
  const [learnResponse, setLearnResponse] = useState<LearnFromEditsResponse | null>(null);
  const [learnSection, setLearnSection] = useState<BriefSectionKey | null>(null);
  const [showLearnModal, setShowLearnModal] = useState(false);

  // Visibility panel
  const [showVisibility, setShowVisibility] = useState(false);

  // Reset dialog
  const [showResetDialog, setShowResetDialog] = useState(false);
  const [resetting, setResetting] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    getBrief(patientId)
      .then((b) => {
        setBrief(b);
        const initial: Partial<Record<BriefSectionKey, string>> = {};
        for (const k of GENERATABLE) {
          if (b[k]) initial[k] = b[k];
        }
        setLastGenerated(initial);
      })
      .catch((e: Error) => setLoadError(e.message))
      .finally(() => setLoading(false));
  }, [patientId]);

  useEffect(() => { load(); }, [load]);

  const isEmpty = !brief || GENERATABLE.every((k) => !brief[k]);

  function markGenerated(updated: Partial<Brief>) {
    setLastGenerated((prev) => {
      const next = { ...prev };
      for (const k of GENERATABLE) {
        if (updated[k] !== undefined) next[k] = updated[k] as string;
      }
      return next;
    });
  }

  async function handleEmptyStateGenerate(extraContext: string, befundeRaw: string) {
    const [briefResult, befundeFormatted] = await Promise.all([
      generateBrief(patientId, extraContext).catch((e: Error) => {
        toast.error(e.message);
        return null;
      }),
      befundeRaw
        ? formatSapBefunde(patientId, befundeRaw).catch(() => null)
        : Promise.resolve(null),
    ]);

    if (!briefResult) return;

    const merged: Brief = befundeFormatted
      ? { ...briefResult, befunde: befundeFormatted }
      : briefResult;

    setBrief(merged);
    markGenerated(merged);
  }

  async function handleRegenerate(section: BriefSectionKey, extraContext?: string) {
    setGenerating((prev) => ({ ...prev, [section]: true }));
    try {
      const result = await regenerateSection(patientId, section, extraContext);
      setBrief((prev) => prev ? { ...prev, ...result } as Brief : null);
      markGenerated(result);
    } catch (e) {
      toast.error(`${SECTION_LABELS[section]}: ${(e as Error).message}`);
    } finally {
      setGenerating((prev) => ({ ...prev, [section]: false }));
    }
  }

  async function handlePolish(section: BriefSectionKey, extraContext?: string) {
    setGenerating((prev) => ({ ...prev, [section]: true }));
    try {
      const result = await polishSection(patientId, section, extraContext);
      setBrief((prev) => prev ? { ...prev, ...result } as Brief : null);
      markGenerated(result);
    } catch (e) {
      toast.error(`${SECTION_LABELS[section]}: ${(e as Error).message}`);
    } finally {
      setGenerating((prev) => ({ ...prev, [section]: false }));
    }
  }

  async function handleFormat(rawText: string, extraContext?: string) {
    setFormatting(true);
    try {
      const formatted = await formatSapBefunde(patientId, rawText, extraContext);
      setBrief((prev) => prev ? { ...prev, befunde: formatted } : prev);
    } catch (e) {
      toast.error(`Befunde: ${(e as Error).message}`);
    } finally {
      setFormatting(false);
    }
  }

  function handleSave(section: BriefSectionKey) {
    return (value: string) => {
      setBrief((prev) => prev ? { ...prev, [section]: value } : prev);
      saveSectionEdit(patientId, section, value).catch(() => {
        toast.error("Speichern fehlgeschlagen");
      });
    };
  }

  async function handleLearn(section: BriefSectionKey) {
    setLearning((prev) => ({ ...prev, [section]: true }));
    try {
      const editedContent = brief?.[section] ?? "";
      let data: LearnFromEditsResponse;
      try {
        data = await learnFromEdits("brief", section, patientId, editedContent);
      } catch (e) {
        if ((e as Error).message.startsWith("HTTP 404")) {
          toast.info("Bitte zuerst generieren.");
          return;
        }
        throw e;
      }
      const hasContent = data.rule_candidates.length > 0 || data.trivial_changes.length > 0;
      if (!hasContent) {
        toast.info("Keine relevanten Änderungen erkannt.");
        return;
      }
      setLearnResponse(data);
      setLearnSection(section);
      setShowLearnModal(true);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLearning((prev) => ({ ...prev, [section]: false }));
    }
  }

  function canLearn(section: BriefSectionKey): boolean {
    const last = lastGenerated[section];
    const current = brief?.[section];
    return last !== undefined && current !== undefined && current.trim() !== last.trim();
  }

  async function handleReset() {
    setResetting(true);
    try {
      await deleteBrief(patientId);
      setBrief(null);
      setLastGenerated({});
      setShowResetDialog(false);
      toast.success("Brief verworfen.");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setResetting(false);
    }
  }

  const anySectionBusy = Object.values(generating).some(Boolean) || formatting;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin mr-2" /> Lade Brief…
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <p className="text-sm text-destructive">Fehler: {loadError}</p>
        <Button variant="ghost" size="sm" onClick={load}>Nochmal versuchen</Button>
      </div>
    );
  }

  if (isEmpty) {
    return (
      <BriefOnboarding
        disabled={anySectionBusy}
        onGenerate={handleEmptyStateGenerate}
      />
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="shrink-0">
        {/* Thin status bar with reset action */}
        <div className="border-b px-4 py-1.5 flex items-center justify-between text-xs bg-muted/20">
          <span className="text-muted-foreground">Brief vorhanden — Sektionen einzeln neu generieren oder bearbeiten.</span>
          <Button
            variant="ghost"
            size="xs"
            className="text-destructive/60 hover:text-destructive shrink-0"
            onClick={() => setShowResetDialog(true)}
            disabled={anySectionBusy || resetting}
          >
            <Trash2 className="size-3 mr-1" />
            Brief verwerfen
          </Button>
        </div>

        {/* Visibility Sub-Panel toggle */}
        <div className="border-b">
          <button
            onClick={() => setShowVisibility((v) => !v)}
            className="w-full flex items-center gap-1.5 px-4 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors"
          >
            {showVisibility
              ? <ChevronDown className="size-3" />
              : <ChevronRight className="size-3" />
            }
            Prompt & Regeln
          </button>
          {showVisibility && <BriefVisibilityPanel />}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {GENERATABLE.filter((k) => k !== "verlauf").map((section) => (
          <BriefSection
            key={section}
            title={SECTION_LABELS[section]}
            content={brief?.[section] ?? ""}
            generating={generating[section]}
            onRegenerate={(extraContext) => handleRegenerate(section, extraContext)}
            onPolish={(extraContext) => handlePolish(section, extraContext)}
            onLearn={LEARNABLE.includes(section) ? () => handleLearn(section) : undefined}
            canLearn={canLearn(section)}
            onSave={handleSave(section)}
            disabled={anySectionBusy || !!learning[section]}
          />
        ))}

        <BefundeSection
          content={brief?.befunde ?? ""}
          formatting={formatting}
          onFormat={handleFormat}
          onSave={handleSave("befunde")}
          disabled={anySectionBusy}
        />

        <BriefSection
          title={SECTION_LABELS["verlauf"]}
          content={brief?.verlauf ?? ""}
          generating={generating["verlauf"]}
          onRegenerate={(extraContext) => handleRegenerate("verlauf", extraContext)}
          onPolish={(extraContext) => handlePolish("verlauf", extraContext)}
          onLearn={() => handleLearn("verlauf")}
          canLearn={canLearn("verlauf")}
          onSave={handleSave("verlauf")}
          disabled={anySectionBusy || !!learning["verlauf"]}
        />
      </div>

      {/* Reset confirm dialog */}
      <Dialog open={showResetDialog} onOpenChange={(o) => !resetting && setShowResetDialog(o)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Brief verwerfen?</DialogTitle>
            <DialogDescription>
              Den gesamten Brief verwerfen? Diese Aktion kann nicht rückgängig gemacht werden.
              Gelernte Regeln bleiben erhalten.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowResetDialog(false)} disabled={resetting}>
              Abbrechen
            </Button>
            <Button variant="destructive" onClick={handleReset} disabled={resetting}>
              {resetting ? (
                <><Loader2 className="size-4 animate-spin" /> Verwerfe…</>
              ) : (
                "Brief verwerfen"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {learnResponse && learnSection && (
        <RuleReviewModal
          open={showLearnModal}
          onOpenChange={(o) => {
            setShowLearnModal(o);
            if (!o) { setLearnResponse(null); setLearnSection(null); }
          }}
          response={learnResponse}
          domain="brief"
          section={learnSection}
          onRulesSaved={() => {
            if (learnSection) {
              setLastGenerated((prev) => ({ ...prev, [learnSection]: brief?.[learnSection] ?? "" }));
            }
          }}
        />
      )}
    </div>
  );
}
