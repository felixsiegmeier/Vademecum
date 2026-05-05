import { useEffect, useRef, useState, useCallback } from "react";
import { Copy, Check, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface MeilensteinData {
  content: string;
  generated_at: string | null;
  is_stale: boolean;
}

interface Props {
  patientId: string;
}

function formatGeneratedAt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function MeilensteinPanel({ patientId }: Props) {
  const [data, setData] = useState<MeilensteinData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [empty, setEmpty] = useState(false);

  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [confirmRegen, setConfirmRegen] = useState(false);

  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveStatusTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [copied, setCopied] = useState(false);

  const loadMeilenstein = useCallback(() => {
    setLoading(true);
    setError(null);
    setEmpty(false);
    fetch(`/api/patients/${patientId}/meilenstein`)
      .then((res) => {
        if (res.status === 404) { setEmpty(true); setData(null); return null; }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((d) => { if (d) setData(d); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [patientId]);

  useEffect(() => {
    loadMeilenstein();
  }, [loadMeilenstein]);

  function handleContentChange(value: string) {
    setData((prev) => prev ? { ...prev, content: value } : null);
    setSaveStatus("saving");

    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      try {
        await fetch(`/api/patients/${patientId}/meilenstein`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: value }),
        });
        setSaveStatus("saved");
        if (saveStatusTimer.current) clearTimeout(saveStatusTimer.current);
        saveStatusTimer.current = setTimeout(() => setSaveStatus("idle"), 2000);
      } catch {
        setSaveStatus("idle");
      }
    }, 1500);
  }

  async function doGenerate() {
    setGenerating(true);
    setGenError(null);
    setConfirmRegen(false);
    try {
      const currentContent = data?.content?.trim() || null;
      const res = await fetch(
        `/api/patients/${patientId}/meilenstein/generate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ current_meilenstein: currentContent }),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const d = await res.json();
      setData(d);
      setEmpty(false);
    } catch (e) {
      const msg = (e as Error).message;
      setGenError(msg);
      toast.error(msg, {
        action: { label: "Erneut versuchen", onClick: doGenerate },
      });
    } finally {
      setGenerating(false);
    }
  }

  async function handleCopy() {
    if (!data?.content) return;
    try {
      await navigator.clipboard.writeText(data.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-full text-sm text-muted-foreground">Lade Meilenstein…</div>;
  }

  if (error) {
    return <div className="flex items-center justify-center h-full text-sm text-destructive">Fehler: {error}</div>;
  }

  if (empty) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <p className="text-sm text-muted-foreground">Noch kein Meilenstein generiert</p>
        {genError && (
          <p className="text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">{genError}</p>
        )}
        <Button onClick={doGenerate} disabled={generating}>
          {generating ? (<><Loader2 className="size-4 animate-spin" /> Generiere…</>) : "Meilenstein generieren"}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {data?.is_stale && (
        <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 flex items-center justify-between gap-4">
          <span className="text-sm text-amber-900">
            Patientendaten haben sich seit der Generierung geändert. Neu generieren?
          </span>
          <Button
            size="sm"
            variant="default"
            onClick={() => setConfirmRegen(true)}
            disabled={generating}
            className="bg-amber-600 hover:bg-amber-700 text-white shrink-0"
          >
            Aktualisieren
          </Button>
        </div>
      )}

      {/* Toolbar */}
      <div className="bg-card border-b px-4 py-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            letzte Generierung: {formatGeneratedAt(data?.generated_at ?? null)}
          </span>
          {saveStatus === "saving" && (
            <span className="text-xs text-muted-foreground">Speichert…</span>
          )}
          {saveStatus === "saved" && (
            <span className="text-xs text-emerald-600">Gespeichert</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleCopy}>
            {copied ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
            {copied ? "Kopiert" : "Kopieren"}
          </Button>
          <Button
            size="sm"
            onClick={() => setConfirmRegen(true)}
            disabled={generating}
          >
            {generating ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
            {generating ? "Aktualisiere…" : "Aktualisieren"}
          </Button>
        </div>
      </div>

      {/* Editor */}
      <div className="flex-1 overflow-hidden p-4">
        <Textarea
          value={data?.content ?? ""}
          onChange={(e) => handleContentChange(e.target.value)}
          className="w-full h-full resize-none font-mono"
          spellCheck={false}
        />
      </div>

      {/* Confirm-Dialog */}
      <Dialog open={confirmRegen} onOpenChange={(o) => !o && !generating && setConfirmRegen(false)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Neu generieren?</DialogTitle>
            <DialogDescription>
              Manuelle Änderungen am Meilenstein werden überschrieben. Fortfahren?
            </DialogDescription>
          </DialogHeader>
          {genError && (
            <p className="text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">{genError}</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmRegen(false)} disabled={generating}>
              Abbrechen
            </Button>
            <Button onClick={doGenerate} disabled={generating}>
              {generating ? (<><Loader2 className="size-4 animate-spin" /> Aktualisiere…</>) : "Aktualisieren"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
