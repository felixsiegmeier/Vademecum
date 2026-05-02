import { useRef, useState } from "react";
import Toast, { type ToastMessage } from "./Toast";
import { setPendingFile } from "../pendingFileStore";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (patientId: string) => void;
}

type Geschlecht = "m" | "w" | "d" | "";
type Aufnahmequelle = "elektiv" | "notfall" | "extern" | "";

interface FormState {
  name: string;
  geburtsdatum: string;
  geschlecht: Geschlecht;
  bettplatz: string;
  aufnahmedatum: string;
  aufnahme_quelle: Aufnahmequelle;
  verlegungsziel: string;
}

interface StammdatenExtract {
  name: string | null;
  geburtsdatum: string | null;
  geschlecht: "m" | "w" | "d" | null;
  bettplatz: string | null;
  aufnahmedatum: string | null;
  aufnahme_quelle: "elektiv" | "notfall" | "extern" | null;
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

const EMPTY_FORM: FormState = {
  name: "",
  geburtsdatum: "",
  geschlecht: "",
  bettplatz: "",
  aufnahmedatum: today(),
  aufnahme_quelle: "",
  verlegungsziel: "",
};

export default function NewPatientDialog({ open, onClose, onCreated }: Props) {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});

  const [pendingFile, setPendingFileState] = useState<File | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastMessage | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!open) return null;

  function setField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => ({ ...e, [key]: undefined }));
  }

  function validate(): boolean {
    const next: Partial<Record<keyof FormState, string>> = {};
    if (!form.name.trim()) next.name = "Pflichtfeld";
    if (!form.geburtsdatum) next.geburtsdatum = "Pflichtfeld";
    if (!form.geschlecht) next.geschlecht = "Pflichtfeld";
    if (!form.bettplatz.trim()) next.bettplatz = "Pflichtfeld";
    if (!form.aufnahmedatum) next.aufnahmedatum = "Pflichtfeld";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleFileSelected(file: File) {
    setIsExtracting(true);
    setUploadError(null);
    setPendingFileState(null);

    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/extract-stammdaten", { method: "POST", body: fd });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `Upload fehlgeschlagen: ${res.status}`);
      }
      const data: StammdatenExtract = await res.json();

      const allNull = Object.values(data).every((v) => v === null);
      if (allNull) {
        setToast({
          id: Date.now(),
          kind: "info",
          text: "Keine Stammdaten im Dokument erkannt — bitte manuell eingeben.",
        });
        // File verworfen — kein Auto-Forward in die Proposals-Pipeline
        return;
      }

      // Felder mit extrahierten Werten befüllen; bestehende manuelle Eingaben nicht überschreiben
      setForm((prev) => ({
        ...prev,
        name: data.name ?? prev.name,
        geburtsdatum: data.geburtsdatum ?? prev.geburtsdatum,
        geschlecht: (data.geschlecht as Geschlecht) ?? prev.geschlecht,
        bettplatz: data.bettplatz ?? prev.bettplatz,
        aufnahmedatum: data.aufnahmedatum ?? prev.aufnahmedatum,
        aufnahme_quelle: (data.aufnahme_quelle as Aufnahmequelle) ?? prev.aufnahme_quelle,
      }));
      setPendingFileState(file);
    } catch (err) {
      setUploadError((err as Error).message);
    } finally {
      setIsExtracting(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const patientRes = await fetch("/api/patients", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stammdaten: {
            name: form.name.trim(),
            geburtsdatum: form.geburtsdatum,
            geschlecht: form.geschlecht,
            bettplatz: form.bettplatz.trim(),
            aufnahmedatum: form.aufnahmedatum,
            aufnahme_quelle: form.aufnahme_quelle || null,
            verlegungsziel: form.verlegungsziel.trim() || null,
          },
        }),
      });
      if (!patientRes.ok) {
        const body = await patientRes.json().catch(() => ({}));
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : Array.isArray(body.detail)
            ? body.detail.map((d: { msg: string }) => d.msg).join(", ")
            : `HTTP ${patientRes.status}`
        );
      }
      const patient = await patientRes.json();
      const patientId = patient.patient_id;

      // Datei im Modul-Store ablegen — PatientChatPanel konsumiert sie beim Mount
      if (pendingFile) {
        setPendingFile(pendingFile);
      }

      handleReset();
      onCreated(patientId);
      onClose();
    } catch (err) {
      setSubmitError((err as Error).message);
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleReset() {
    setForm(EMPTY_FORM);
    setErrors({});
    setPendingFileState(null);
    setUploadError(null);
    setSubmitError(null);
  }

  function handleClose() {
    if (isExtracting || isSubmitting) return;
    handleReset();
    onClose();
  }

  return (
    <>
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        onClick={(e) => e.target === e.currentTarget && handleClose()}
      >
        <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 overflow-hidden max-h-[90vh] flex flex-col">
          {/* Header */}
          <div className="px-6 py-4 border-b border-gray-200 shrink-0">
            <h2 className="text-base font-semibold text-gray-900">Neuer Patient</h2>
          </div>

          <form onSubmit={handleSubmit} noValidate className="flex flex-col overflow-hidden">
            <div className="px-6 py-4 space-y-4 overflow-y-auto">
              {/* Upload-Bereich */}
              <div>
                <p className="text-sm text-gray-500 mb-2">
                  Optional: Dokument hochladen, um Felder automatisch zu befüllen.
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFileSelected(file);
                    e.target.value = "";
                  }}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isExtracting || isSubmitting}
                  className="w-full rounded-lg border-2 border-dashed border-gray-300 px-4 py-4 text-sm text-gray-500 hover:border-blue-400 hover:text-blue-500 transition-colors disabled:opacity-50"
                >
                  {isExtracting ? (
                    <span className="text-blue-500">Stammdaten werden gelesen…</span>
                  ) : pendingFile ? (
                    <span className="text-gray-800 font-medium">📎 {pendingFile.name}</span>
                  ) : (
                    "PDF, JPG oder PNG auswählen…"
                  )}
                </button>
                {uploadError && (
                  <p className="mt-1 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
                    {uploadError}
                  </p>
                )}
              </div>

              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setField("name", e.target.value)}
                  placeholder="Nachname, Vorname"
                  disabled={isSubmitting}
                  className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 ${
                    errors.name ? "border-red-400" : "border-gray-300"
                  }`}
                />
                {errors.name && <p className="mt-1 text-xs text-red-600">{errors.name}</p>}
              </div>

              {/* Geburtsdatum + Geschlecht */}
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Geburtsdatum <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="date"
                    value={form.geburtsdatum}
                    onChange={(e) => setField("geburtsdatum", e.target.value)}
                    disabled={isSubmitting}
                    className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 ${
                      errors.geburtsdatum ? "border-red-400" : "border-gray-300"
                    }`}
                  />
                  {errors.geburtsdatum && (
                    <p className="mt-1 text-xs text-red-600">{errors.geburtsdatum}</p>
                  )}
                </div>
                <div className="w-28">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Geschlecht <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={form.geschlecht}
                    onChange={(e) => setField("geschlecht", e.target.value as Geschlecht)}
                    disabled={isSubmitting}
                    className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 ${
                      errors.geschlecht ? "border-red-400" : "border-gray-300"
                    }`}
                  >
                    <option value="">—</option>
                    <option value="m">m</option>
                    <option value="w">w</option>
                    <option value="d">d</option>
                  </select>
                  {errors.geschlecht && (
                    <p className="mt-1 text-xs text-red-600">{errors.geschlecht}</p>
                  )}
                </div>
              </div>

              {/* Bettplatz */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Bettplatz <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={form.bettplatz}
                  onChange={(e) => setField("bettplatz", e.target.value)}
                  placeholder="ITS-1 / Bett 3"
                  disabled={isSubmitting}
                  className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 ${
                    errors.bettplatz ? "border-red-400" : "border-gray-300"
                  }`}
                />
                {errors.bettplatz && (
                  <p className="mt-1 text-xs text-red-600">{errors.bettplatz}</p>
                )}
              </div>

              {/* Aufnahmedatum + Aufnahmequelle */}
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Aufnahmedatum <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="date"
                    value={form.aufnahmedatum}
                    onChange={(e) => setField("aufnahmedatum", e.target.value)}
                    disabled={isSubmitting}
                    className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 ${
                      errors.aufnahmedatum ? "border-red-400" : "border-gray-300"
                    }`}
                  />
                  {errors.aufnahmedatum && (
                    <p className="mt-1 text-xs text-red-600">{errors.aufnahmedatum}</p>
                  )}
                </div>
                <div className="w-36">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Aufnahmequelle
                  </label>
                  <select
                    value={form.aufnahme_quelle}
                    onChange={(e) => setField("aufnahme_quelle", e.target.value as Aufnahmequelle)}
                    disabled={isSubmitting}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                  >
                    <option value="">—</option>
                    <option value="elektiv">elektiv</option>
                    <option value="notfall">notfall</option>
                    <option value="extern">extern</option>
                  </select>
                </div>
              </div>

              {/* Verlegungsziel */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Verlegungsziel
                </label>
                <input
                  type="text"
                  value={form.verlegungsziel}
                  onChange={(e) => setField("verlegungsziel", e.target.value)}
                  placeholder="IMC, Normalstation, …"
                  disabled={isSubmitting}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                />
              </div>

              {submitError && (
                <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
                  {submitError}
                </p>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-gray-200 flex justify-end gap-2 shrink-0">
              <button
                type="button"
                onClick={handleClose}
                disabled={isExtracting || isSubmitting}
                className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg disabled:opacity-50"
              >
                Abbrechen
              </button>
              <button
                type="submit"
                disabled={isSubmitting || isExtracting}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50"
              >
                {isSubmitting ? "Anlegen…" : "Anlegen"}
              </button>
            </div>
          </form>
        </div>
      </div>

      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </>
  );
}
