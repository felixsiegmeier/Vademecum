import { useEffect, useRef, useState, useCallback } from "react";

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
  const [empty, setEmpty] = useState(false);  // 404 → noch kein Meilenstein vorhanden

  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [confirmRegen, setConfirmRegen] = useState(false);  // Regen-Modal anzeigen?

  // Autosave: Debounce-Timer — erst 1,5s nach letzter Eingabe wird gespeichert
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
    // Lokalen State sofort aktualisieren (optimistic), Backend mit Debounce
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
      const res = await fetch(
        `/api/patients/${patientId}/meilenstein/generate`,
        { method: "POST" }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const d = await res.json();
      setData(d);
      setEmpty(false);
    } catch (e) {
      setGenError((e as Error).message);
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
    return <div className="flex items-center justify-center h-full text-sm text-gray-400">Lade Meilenstein…</div>;
  }

  if (error) {
    return <div className="flex items-center justify-center h-full text-sm text-red-600">Fehler: {error}</div>;
  }

  // Noch kein Meilenstein generiert → nur Generate-Button zeigen
  if (empty) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <p className="text-sm text-gray-500">Noch kein Meilenstein generiert</p>
        {genError && (
          <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{genError}</p>
        )}
        <button
          onClick={doGenerate}
          disabled={generating}
          className="px-5 py-2.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {generating ? "Generiere…" : "Meilenstein generieren"}
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Stale-Banner: erscheint wenn YAML sich seit der Generierung geändert hat */}
      {data?.is_stale && (
        <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 flex items-center justify-between gap-4">
          <span className="text-sm text-amber-800">
            Patientendaten haben sich seit der Generierung geändert. Neu generieren?
          </span>
          <button
            onClick={() => setConfirmRegen(true)}
            disabled={generating}
            className="shrink-0 px-3 py-1 text-xs font-medium text-white bg-amber-600 hover:bg-amber-700 rounded-lg disabled:opacity-50"
          >
            Neu generieren
          </button>
        </div>
      )}

      {/* Toolbar */}
      <div className="bg-white border-b px-4 py-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">
            letzte Generierung: {formatGeneratedAt(data?.generated_at ?? null)}
          </span>
          {saveStatus === "saving" && (
            <span className="text-xs text-gray-400">Speichert…</span>
          )}
          {saveStatus === "saved" && (
            <span className="text-xs text-green-600">Gespeichert</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCopy}
            className="px-3 py-1.5 text-xs font-medium text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            {copied ? "Kopiert ✓" : "Kopieren"}
          </button>
          <button
            onClick={() => setConfirmRegen(true)}
            disabled={generating}
            className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50"
          >
            {generating ? "Generiere…" : "Neu generieren"}
          </button>
        </div>
      </div>

      {/* Editierbares Textarea (Arzt kann Meilenstein manuell korrigieren) */}
      <div className="flex-1 overflow-hidden p-4">
        <textarea
          value={data?.content ?? ""}
          onChange={(e) => handleContentChange(e.target.value)}
          className="w-full h-full resize-none font-mono text-sm text-gray-800 bg-white border border-gray-200 rounded-lg p-4 focus:outline-none focus:ring-2 focus:ring-blue-500"
          spellCheck={false}
        />
      </div>

      {/* Bestätigungs-Modal vor Neu-Generierung (manuelle Änderungen werden überschrieben) */}
      {confirmRegen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4 p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-2">Neu generieren?</h2>
            <p className="text-sm text-gray-600 mb-6">
              Manuelle Änderungen am Meilenstein werden überschrieben. Fortfahren?
            </p>
            {genError && (
              <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-4">{genError}</p>
            )}
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setConfirmRegen(false)}
                disabled={generating}
                className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg disabled:opacity-50"
              >
                Abbrechen
              </button>
              <button
                onClick={doGenerate}
                disabled={generating}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50"
              >
                {generating ? "Generiere…" : "Neu generieren"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
