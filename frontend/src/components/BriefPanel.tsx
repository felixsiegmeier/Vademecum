import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy, RefreshCw, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

// Die 6 Brief-Felder — Reihenfolge bestimmt die Darstellung
const BRIEF_FIELDS = [
  { key: "diagnosen", label: "Diagnosen" },
  { key: "anamnese", label: "Anamnese" },
  { key: "operationen_prozeduren", label: "Operationen und Prozeduren" },
  { key: "konservative_therapien", label: "Konservative Therapien" },
  { key: "antimikrobielle_therapie", label: "Antimikrobielle Therapie" },
  { key: "verlauf", label: "Verlauf" },
] as const;

type FieldKey = (typeof BRIEF_FIELDS)[number]["key"];

interface BriefMeta {
  generated_at: Record<FieldKey, string | null>;
  field_hash_at_generation: Record<FieldKey, string | null>;
  input_hash_at_generation: Record<FieldKey, string | null>;
}

interface BriefData {
  diagnosen: string;
  anamnese: string;
  operationen_prozeduren: string;
  konservative_therapien: string;
  antimikrobielle_therapie: string;
  verlauf: string;
  meta: BriefMeta;
}

interface Props {
  patientId: string;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function initRecord<T>(val: T): Record<FieldKey, T> {
  return Object.fromEntries(BRIEF_FIELDS.map((f) => [f.key, val])) as Record<FieldKey, T>;
}

export default function BriefPanel({ patientId }: Props) {
  const [briefData, setBriefData] = useState<BriefData | null>(null);
  const [isStale, setIsStale] = useState<Record<FieldKey, boolean>>(initRecord(false));
  const [localContent, setLocalContent] = useState<Record<FieldKey, string>>(initRecord(""));
  const [hasLocalEdits, setHasLocalEdits] = useState<Record<FieldKey, boolean>>(initRecord(false));

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [empty, setEmpty] = useState(false);

  const [globalGenerating, setGlobalGenerating] = useState(false);
  const [globalGenError, setGlobalGenError] = useState<string | null>(null);
  const [generatingField, setGeneratingField] = useState<FieldKey | null>(null);
  const [fieldGenErrors, setFieldGenErrors] = useState<Record<FieldKey, string>>(initRecord(""));

  const [saveStatus, setSaveStatus] = useState<Record<FieldKey, "idle" | "saving" | "saved">>(
    initRecord("idle")
  );
  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const [popoverField, setPopoverField] = useState<FieldKey | null>(null);
  const [customPrompt, setCustomPrompt] = useState("");
  const popoverRef = useRef<HTMLDivElement>(null);

  const textareaRefs = useRef<Partial<Record<FieldKey, HTMLTextAreaElement | null>>>({});
  const [copiedField, setCopiedField] = useState<FieldKey | null>(null);

  const applyBriefData = (d: BriefData, stale: Record<FieldKey, boolean> = initRecord(false)) => {
    setBriefData(d);
    setIsStale(stale);
    const c = initRecord("");
    BRIEF_FIELDS.forEach((f) => { (c as Record<string, string>)[f.key] = d[f.key]; });
    setLocalContent(c);
    setHasLocalEdits(initRecord(false));
  };

  const loadBrief = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    setEmpty(false);
    fetch(`/api/patients/${patientId}/brief`)
      .then((res) => {
        if (res.status === 404) { setEmpty(true); return null; }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((d) => {
        if (d) applyBriefData(d.data, d.is_stale);
      })
      .catch((e: Error) => setLoadError(e.message))
      .finally(() => setLoading(false));
  }, [patientId]);

  useEffect(() => { loadBrief(); }, [loadBrief]);

  useEffect(() => {
    if (!popoverField) return;
    function handleClick(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setPopoverField(null);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [popoverField]);

  useEffect(() => {
    BRIEF_FIELDS.forEach((f) => {
      const el = textareaRefs.current[f.key];
      if (el) {
        el.style.height = "auto";
        el.style.height = `${el.scrollHeight}px`;
      }
    });
  }, [localContent]);

  function handleContentChange(field: FieldKey, value: string) {
    setLocalContent((prev) => ({ ...prev, [field]: value }));
    setHasLocalEdits((prev) => ({ ...prev, [field]: true }));
    setSaveStatus((prev) => ({ ...prev, [field]: "saving" }));

    if (saveTimers.current[field]) clearTimeout(saveTimers.current[field]);
    saveTimers.current[field] = setTimeout(async () => {
      try {
        await fetch(`/api/patients/${patientId}/brief/${field}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: value }),
        });
        setSaveStatus((prev) => ({ ...prev, [field]: "saved" }));
        setTimeout(
          () => setSaveStatus((prev) => ({ ...prev, [field]: "idle" })),
          2000
        );
      } catch {
        setSaveStatus((prev) => ({ ...prev, [field]: "idle" }));
      }
    }, 1500);
  }

  async function handleGlobalGenerate() {
    setGlobalGenerating(true);
    setGlobalGenError(null);
    try {
      const res = await fetch(
        `/api/patients/${patientId}/brief/generate`,
        { method: "POST" }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
      }
      const d: BriefData = await res.json();
      applyBriefData(d);
      setEmpty(false);
    } catch (e) {
      setGlobalGenError((e as Error).message);
    } finally {
      setGlobalGenerating(false);
    }
  }

  async function handleFieldRegenerate(field: FieldKey) {
    setGeneratingField(field);
    setFieldGenErrors((prev) => ({ ...prev, [field]: "" }));
    setPopoverField(null);
    const prompt = customPrompt;
    setCustomPrompt("");
    try {
      const res = await fetch(
        `/api/patients/${patientId}/brief/generate/${field}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ custom_prompt: prompt || null }),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
      }
      const d: BriefData = await res.json();
      setBriefData(d);
      setLocalContent((prev) => ({ ...prev, [field]: d[field] }));
      setHasLocalEdits((prev) => ({ ...prev, [field]: false }));
      setIsStale((prev) => ({ ...prev, [field]: false }));
    } catch (e) {
      setFieldGenErrors((prev) => ({ ...prev, [field]: (e as Error).message }));
    } finally {
      setGeneratingField(null);
    }
  }

  async function handleCopy(field: FieldKey) {
    try {
      await navigator.clipboard.writeText(localContent[field] ?? "");
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 2000);
    } catch {
      /* ignore */
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        Lade Brief…
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-destructive">
        Fehler: {loadError}
      </div>
    );
  }

  if (empty) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <p className="text-sm text-muted-foreground">Noch kein Brief generiert</p>
        {globalGenError && (
          <p className="text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">{globalGenError}</p>
        )}
        <Button
          onClick={handleGlobalGenerate}
          disabled={globalGenerating}
        >
          {globalGenerating ? (<><Loader2 className="size-4 animate-spin" /> Generiere…</>) : "Brief generieren"}
        </Button>
      </div>
    );
  }

  const anyStale = Object.values(isStale).some(Boolean);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {anyStale && (
        <div className="shrink-0 bg-amber-50 border-b border-amber-200 px-4 py-2">
          <span className="text-sm text-amber-900">
            Patientendaten haben sich seit der Generierung geändert. Felder können einzeln neu
            generiert werden.
          </span>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {BRIEF_FIELDS.map(({ key, label }) => {
          const isGeneratingThis = generatingField === key;
          const isPopoverOpen = popoverField === key;
          const genAt = briefData?.meta.generated_at[key] ?? null;
          const stale = isStale[key];
          const fieldErr = fieldGenErrors[key];

          return (
            <div key={key}>
              <div className="flex items-center gap-2 mb-1.5">
                <h3 className="text-sm font-semibold text-foreground flex-1">{label}</h3>

                {stale && (
                  <span
                    className="size-2 rounded-full bg-amber-500 shrink-0"
                    title="Daten seit Generierung geändert"
                  />
                )}

                <span className="text-xs text-muted-foreground shrink-0">
                  {genAt ? `Generiert: ${formatDate(genAt)}` : "Nicht generiert"}
                </span>

                <Button
                  variant="ghost"
                  size="icon-xs"
                  onClick={() => handleCopy(key)}
                  title="Kopieren"
                >
                  {copiedField === key ? (
                    <Check className="size-3.5 text-emerald-600" />
                  ) : (
                    <Copy className="size-3.5" />
                  )}
                </Button>

                <div
                  className="relative shrink-0"
                  ref={isPopoverOpen ? popoverRef : undefined}
                >
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    onClick={() => {
                      if (isPopoverOpen) {
                        setPopoverField(null);
                      } else {
                        setCustomPrompt("");
                        setPopoverField(key);
                      }
                    }}
                    disabled={isGeneratingThis || globalGenerating}
                    title="Neu generieren"
                  >
                    {isGeneratingThis ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="size-3.5" />
                    )}
                  </Button>

                  {isPopoverOpen && (
                    <div className="absolute right-0 top-full mt-1 w-80 bg-popover text-popover-foreground border rounded-md shadow-md z-20 p-3">
                      <p className="text-xs font-medium mb-2">Neu generieren</p>
                      {hasLocalEdits[key] && (
                        <div className="mb-3 text-xs text-amber-900 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
                          Manuelle Änderungen an diesem Abschnitt werden überschrieben. Trotzdem generieren?
                        </div>
                      )}
                      {fieldErr && (
                        <div className="mb-3 text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2">
                          {fieldErr}
                        </div>
                      )}
                      <Textarea
                        value={customPrompt}
                        onChange={(e) => setCustomPrompt(e.target.value)}
                        placeholder="z.B. kürzer, chronologisch, nur Rechtschreibung korrigieren …"
                        rows={2}
                        className="text-xs resize-none mb-3"
                      />
                      <div className="flex gap-2 justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setPopoverField(null)}
                        >
                          Abbrechen
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => handleFieldRegenerate(key)}
                        >
                          Generieren
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div className="relative">
                <Textarea
                  ref={(el) => { textareaRefs.current[key] = el; }}
                  value={localContent[key]}
                  onChange={(e) => handleContentChange(key, e.target.value)}
                  disabled={isGeneratingThis}
                  className="w-full min-h-[120px] resize-none"
                  style={{ overflow: "hidden" }}
                  spellCheck={false}
                />
                {isGeneratingThis && (
                  <div className="absolute inset-0 flex items-center justify-center bg-background/60 rounded-md">
                    <span className="text-xs text-muted-foreground flex items-center gap-1.5">
                      <Loader2 className="size-3.5 animate-spin" />
                      Generiere…
                    </span>
                  </div>
                )}
              </div>

              <div className={cn("h-4 mt-1", saveStatus[key] === "idle" && "invisible")}>
                {saveStatus[key] === "saving" && (
                  <span className="text-xs text-muted-foreground">Speichert…</span>
                )}
                {saveStatus[key] === "saved" && (
                  <span className="text-xs text-emerald-600">Gespeichert</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
