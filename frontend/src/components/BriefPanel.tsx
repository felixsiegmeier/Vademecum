import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import type { Brief, BriefSectionKey } from "../types";
import {
  generateBrief,
  getBrief,
  formatSapBefunde,
  regenerateSection,
  saveSectionEdit,
} from "../api/brief";
import PendingContextZone from "./PendingContextZone";
import BriefSection from "./BriefSection";
import BefundeSection from "./BefundeSection";

interface Props {
  patientId: string;
}

const GENERATABLE: BriefSectionKey[] = ["diagnosen", "anamnese", "therapie", "verlauf"];
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

  const [globalGenerating, setGlobalGenerating] = useState(false);
  const [generating, setGenerating] = useState<Partial<Record<BriefSectionKey, boolean>>>({});
  const [formatting, setFormatting] = useState(false);

  const [pendingContext, setPendingContext] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    getBrief(patientId)
      .then(setBrief)
      .catch((e: Error) => setLoadError(e.message))
      .finally(() => setLoading(false));
  }, [patientId]);

  useEffect(() => { load(); }, [load]);

  const isEmpty = !brief || GENERATABLE.every((k) => !brief[k]);

  async function handleGenerate() {
    setGlobalGenerating(true);
    try {
      const updated = await generateBrief(patientId, pendingContext);
      setBrief(updated);
      setPendingContext("");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setGlobalGenerating(false);
    }
  }

  async function handleRegenerate(section: BriefSectionKey) {
    setGenerating((prev) => ({ ...prev, [section]: true }));
    try {
      const result = await regenerateSection(patientId, section, pendingContext);
      setBrief((prev) => prev ? { ...prev, ...result } as Brief : null);
      setPendingContext("");
    } catch (e) {
      toast.error(`${SECTION_LABELS[section]}: ${(e as Error).message}`);
    } finally {
      setGenerating((prev) => ({ ...prev, [section]: false }));
    }
  }

  async function handleFormat(rawText: string) {
    setFormatting(true);
    try {
      const formatted = await formatSapBefunde(patientId, rawText);
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

  const busy = globalGenerating || Object.values(generating).some(Boolean) || formatting;

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
      <div className="flex flex-col h-full overflow-hidden">
        <PendingContextZone
          onSubmit={setPendingContext}
          disabled={busy}
        />
        <div className="flex flex-col items-center justify-center flex-1 gap-4">
          {pendingContext && (
            <p className="text-xs text-muted-foreground max-w-sm text-center bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
              Zusatz-Kontext gesetzt — wird bei Generierung verwendet.
            </p>
          )}
          <Button onClick={handleGenerate} disabled={globalGenerating}>
            {globalGenerating ? (
              <><Loader2 className="size-4 animate-spin" /> Generiere…</>
            ) : (
              "Brief generieren"
            )}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="shrink-0">
        <PendingContextZone onSubmit={setPendingContext} disabled={busy} />
        {pendingContext && (
          <div className="px-4 py-1.5 text-xs text-amber-900 bg-amber-50 border-b border-amber-200 flex items-center gap-2">
            <span className="flex-1">Zusatz-Kontext gesetzt — wird bei nächster Generierung verwendet.</span>
            <button
              className="underline text-amber-700 hover:text-amber-900"
              onClick={() => setPendingContext("")}
            >
              Verwerfen
            </button>
          </div>
        )}
        <div className="flex items-center justify-between px-4 py-2 border-b">
          <span className="text-xs text-muted-foreground">Alle 4 Sektionen neu generieren</span>
          <Button size="sm" onClick={handleGenerate} disabled={busy}>
            {globalGenerating ? (
              <><Loader2 className="size-3.5 animate-spin" /> Generiere…</>
            ) : (
              "Neu generieren"
            )}
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {GENERATABLE.filter((k) => k !== "verlauf").map((section) => (
          <BriefSection
            key={section}
            title={SECTION_LABELS[section]}
            content={brief?.[section] ?? ""}
            generating={generating[section]}
            onRegenerate={() => handleRegenerate(section)}
            onSave={handleSave(section)}
            disabled={busy}
          />
        ))}

        <BefundeSection
          content={brief?.befunde ?? ""}
          formatting={formatting}
          onFormat={handleFormat}
          onSave={handleSave("befunde")}
          disabled={busy}
        />

        <BriefSection
          title={SECTION_LABELS["verlauf"]}
          content={brief?.verlauf ?? ""}
          generating={generating["verlauf"]}
          onRegenerate={() => handleRegenerate("verlauf")}
          onSave={handleSave("verlauf")}
          disabled={busy}
        />
      </div>
    </div>
  );
}
