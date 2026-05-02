import { useCallback, useEffect, useRef, useState } from "react";

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

// Erstellt ein Record-Objekt mit demselben Wert für alle 6 Felder
function initRecord<T>(val: T): Record<FieldKey, T> {
  return Object.fromEntries(BRIEF_FIELDS.map((f) => [f.key, val])) as Record<FieldKey, T>;
}

export default function BriefPanel({ patientId }: Props) {
  const [briefData, setBriefData] = useState<BriefData | null>(null);
  // is_stale pro Feld: hat sich die Quelldaten seit der Generierung geändert?
  const [isStale, setIsStale] = useState<Record<FieldKey, boolean>>(initRecord(false));
  // localContent: was im Textarea steht (kann vom gespeicherten Wert abweichen, während Autosave läuft)
  const [localContent, setLocalContent] = useState<Record<FieldKey, string>>(initRecord(""));
  // hasLocalEdits: wurde dieses Feld manuell bearbeitet? (für Warnung vor Neu-Generierung)
  const [hasLocalEdits, setHasLocalEdits] = useState<Record<FieldKey, boolean>>(initRecord(false));

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [empty, setEmpty] = useState(false);  // 404 → noch kein Brief

  // globalGenerating: alle Felder auf einmal (erster Aufruf)
  const [globalGenerating, setGlobalGenerating] = useState(false);
  const [globalGenError, setGlobalGenError] = useState<string | null>(null);
  // generatingField: genau ein Feld wird gerade regeneriert
  const [generatingField, setGeneratingField] = useState<FieldKey | null>(null);
  const [fieldGenErrors, setFieldGenErrors] = useState<Record<FieldKey, string>>(initRecord(""));

  // Autosave-Status und Debounce-Timer pro Feld
  const [saveStatus, setSaveStatus] = useState<Record<FieldKey, "idle" | "saving" | "saved">>(
    initRecord("idle")
  );
  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // popoverField: welches Feld hat gerade das Regenerier-Popover offen?
  const [popoverField, setPopoverField] = useState<FieldKey | null>(null);
  const [customPrompt, setCustomPrompt] = useState("");
  const popoverRef = useRef<HTMLDivElement>(null);

  // Refs zu allen Textareas für Auto-Resize
  const textareaRefs = useRef<Partial<Record<FieldKey, HTMLTextAreaElement | null>>>({});
  const [copiedField, setCopiedField] = useState<FieldKey | null>(null);

  // Neue Brief-Daten vom Backend übernehmen und alle lokalen States synchronisieren
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

  // Popover schließen bei Klick außerhalb
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

  // Textarea-Höhe automatisch an Inhalt anpassen (kein festes resize)
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

    // Debounce: 1,5s warten nach letzter Eingabe, dann speichern
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
      // Nur das regenerierte Feld aktualisieren, den Rest unberührt lassen
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

  // ── Render-States ──────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-gray-400">
        Lade Brief…
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-red-600">
        Fehler: {loadError}
      </div>
    );
  }

  // Noch kein Brief generiert → nur Generate-Button zeigen
  if (empty) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <p className="text-sm text-gray-500">Noch kein Brief generiert</p>
        {globalGenError && (
          <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{globalGenError}</p>
        )}
        <button
          onClick={handleGlobalGenerate}
          disabled={globalGenerating}
          className="px-5 py-2.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {globalGenerating ? "Generiere…" : "Brief generieren"}
        </button>
      </div>
    );
  }

  const anyStale = Object.values(isStale).some(Boolean);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Globaler Stale-Banner: mindestens ein Feld ist veraltet */}
      {anyStale && (
        <div className="shrink-0 bg-amber-50 border-b border-amber-200 px-4 py-2">
          <span className="text-sm text-amber-800">
            Patientendaten haben sich seit der Generierung geändert. Felder können einzeln neu
            generiert werden.
          </span>
        </div>
      )}

      {/* Felder */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-8">
        {BRIEF_FIELDS.map(({ key, label }) => {
          const isGeneratingThis = generatingField === key;
          const isPopoverOpen = popoverField === key;
          const genAt = briefData?.meta.generated_at[key] ?? null;
          const stale = isStale[key];
          const fieldErr = fieldGenErrors[key];

          return (
            <div key={key}>
              {/* Feld-Header: Label + Staleness-Indikator + Zeitstempel + Buttons */}
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-sm font-semibold text-gray-800 flex-1">{label}</h3>

                {/* Orangener Punkt = Quelldaten haben sich geändert */}
                {stale && (
                  <span
                    className="w-2 h-2 rounded-full bg-amber-400 shrink-0"
                    title="Daten seit Generierung geändert"
                  />
                )}

                <span className="text-xs text-gray-400 shrink-0">
                  {genAt ? `Generiert: ${formatDate(genAt)}` : "Nicht generiert"}
                </span>

                {/* Kopier-Button */}
                <button
                  onClick={() => handleCopy(key)}
                  title="Kopieren"
                  className="shrink-0 p-1 text-gray-400 hover:text-gray-600 rounded"
                >
                  {copiedField === key ? (
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 text-green-600" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
                      <path d="M8 3a1 1 0 011-1h2a1 1 0 110 2H9a1 1 0 01-1-1z" />
                      <path d="M6 3a2 2 0 00-2 2v11a2 2 0 002 2h8a2 2 0 002-2V5a2 2 0 00-2-2 3 3 0 01-3 3H9a3 3 0 01-3-3z" />
                    </svg>
                  )}
                </button>

                {/* Regenerier-Button + Popover (mit optionalem Custom-Prompt) */}
                <div
                  className="relative shrink-0"
                  ref={isPopoverOpen ? popoverRef : undefined}
                >
                  <button
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
                    className="p-1 text-gray-400 hover:text-gray-600 rounded disabled:opacity-40"
                  >
                    {isGeneratingThis ? (
                      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" d="M12 2a10 10 0 0 1 0 20" />
                      </svg>
                    ) : (
                      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clipRule="evenodd" />
                      </svg>
                    )}
                  </button>

                  {/* Popover: Warnung + optionaler Custom-Prompt + Generieren-Button */}
                  {isPopoverOpen && (
                    <div className="absolute right-0 top-full mt-1 w-80 bg-white border border-gray-200 rounded-xl shadow-lg z-20 p-4">
                      <p className="text-xs font-medium text-gray-700 mb-2">Neu generieren</p>
                      {hasLocalEdits[key] && (
                        <div className="mb-3 text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
                          Manuelle Änderungen an diesem Abschnitt werden überschrieben. Trotzdem generieren?
                        </div>
                      )}
                      {fieldErr && (
                        <div className="mb-3 text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">
                          {fieldErr}
                        </div>
                      )}
                      <textarea
                        value={customPrompt}
                        onChange={(e) => setCustomPrompt(e.target.value)}
                        placeholder="z.B. kürzer, chronologisch, nur Rechtschreibung korrigieren …"
                        rows={2}
                        className="w-full text-xs text-gray-700 border border-gray-200 rounded-lg p-2 mb-3 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                      <div className="flex gap-2 justify-end">
                        <button
                          onClick={() => setPopoverField(null)}
                          className="px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100 rounded-lg"
                        >
                          Abbrechen
                        </button>
                        <button
                          onClick={() => handleFieldRegenerate(key)}
                          className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
                        >
                          Generieren
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Textarea mit Generierungs-Overlay */}
              <div className="relative">
                <textarea
                  ref={(el) => { textareaRefs.current[key] = el; }}
                  value={localContent[key]}
                  onChange={(e) => handleContentChange(key, e.target.value)}
                  disabled={isGeneratingThis}
                  className="w-full min-h-[120px] resize-none text-sm text-gray-800 bg-white border border-gray-200 rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60"
                  style={{ overflow: "hidden" }}
                  spellCheck={false}
                />
                {isGeneratingThis && (
                  <div className="absolute inset-0 flex items-center justify-center bg-white/60 rounded-lg">
                    <span className="text-xs text-gray-500">Generiere…</span>
                  </div>
                )}
              </div>

              {/* Autosave-Status unter dem Textarea */}
              <div className="h-4 mt-1">
                {saveStatus[key] === "saving" && (
                  <span className="text-xs text-gray-400">Speichert…</span>
                )}
                {saveStatus[key] === "saved" && (
                  <span className="text-xs text-green-600">Gespeichert</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
