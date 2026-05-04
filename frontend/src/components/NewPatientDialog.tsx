import { useRef, useState } from "react";
import { Upload, Loader2, Paperclip } from "lucide-react";
import { toast } from "sonner";
import { setPendingFile } from "../pendingFileStore";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

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

  const fileInputRef = useRef<HTMLInputElement>(null);

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
        toast.info("Keine Stammdaten im Dokument erkannt — bitte manuell eingeben.");
        return;
      }

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

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      if (isExtracting || isSubmitting) return;
      handleReset();
      onClose();
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md max-h-[90vh] flex flex-col gap-0 p-0 overflow-hidden">
        <DialogHeader className="px-6 py-4 border-b shrink-0">
          <DialogTitle>Neuer Patient</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} noValidate className="flex flex-col overflow-hidden flex-1">
          <div className="px-6 py-4 space-y-4 overflow-y-auto">
            {/* Upload-Bereich */}
            <div>
              <p className="text-sm text-muted-foreground mb-2">
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
                className={cn(
                  "w-full rounded-md border-2 border-dashed border-input px-4 py-4 text-sm transition-colors disabled:opacity-50",
                  "hover:border-primary hover:bg-muted/40",
                  pendingFile && "border-primary/40 bg-primary/5",
                )}
              >
                {isExtracting ? (
                  <span className="flex items-center justify-center gap-2 text-primary">
                    <Loader2 className="size-4 animate-spin" />
                    Stammdaten werden gelesen…
                  </span>
                ) : pendingFile ? (
                  <span className="flex items-center justify-center gap-2 text-foreground font-medium">
                    <Paperclip className="size-4" />
                    {pendingFile.name}
                  </span>
                ) : (
                  <span className="flex items-center justify-center gap-2 text-muted-foreground">
                    <Upload className="size-4" />
                    PDF, JPG oder PNG auswählen…
                  </span>
                )}
              </button>
              {uploadError && (
                <p className="mt-2 text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">
                  {uploadError}
                </p>
              )}
            </div>

            {/* Name */}
            <div className="space-y-1">
              <Label htmlFor="np-name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="np-name"
                type="text"
                value={form.name}
                onChange={(e) => setField("name", e.target.value)}
                placeholder="Nachname, Vorname"
                disabled={isSubmitting}
                aria-invalid={!!errors.name}
              />
              {errors.name && <p className="text-xs text-destructive">{errors.name}</p>}
            </div>

            {/* Geburtsdatum + Geschlecht */}
            <div className="flex gap-3">
              <div className="flex-1 space-y-1">
                <Label htmlFor="np-geburtsdatum">
                  Geburtsdatum <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="np-geburtsdatum"
                  type="date"
                  value={form.geburtsdatum}
                  onChange={(e) => setField("geburtsdatum", e.target.value)}
                  disabled={isSubmitting}
                  aria-invalid={!!errors.geburtsdatum}
                />
                {errors.geburtsdatum && (
                  <p className="text-xs text-destructive">{errors.geburtsdatum}</p>
                )}
              </div>
              <div className="w-32 space-y-1">
                <Label>
                  Geschlecht <span className="text-destructive">*</span>
                </Label>
                <Select
                  value={form.geschlecht}
                  onValueChange={(v) => setField("geschlecht", v as Geschlecht)}
                  disabled={isSubmitting}
                >
                  <SelectTrigger
                    className="w-full"
                    aria-invalid={!!errors.geschlecht}
                  >
                    <SelectValue placeholder="—" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="m">m</SelectItem>
                    <SelectItem value="w">w</SelectItem>
                    <SelectItem value="d">d</SelectItem>
                  </SelectContent>
                </Select>
                {errors.geschlecht && (
                  <p className="text-xs text-destructive">{errors.geschlecht}</p>
                )}
              </div>
            </div>

            {/* Bettplatz */}
            <div className="space-y-1">
              <Label htmlFor="np-bettplatz">
                Bettplatz <span className="text-destructive">*</span>
              </Label>
              <Input
                id="np-bettplatz"
                type="text"
                value={form.bettplatz}
                onChange={(e) => setField("bettplatz", e.target.value)}
                placeholder="ITS-1 / Bett 3"
                disabled={isSubmitting}
                aria-invalid={!!errors.bettplatz}
              />
              {errors.bettplatz && (
                <p className="text-xs text-destructive">{errors.bettplatz}</p>
              )}
            </div>

            {/* Aufnahmedatum + Aufnahmequelle */}
            <div className="flex gap-3">
              <div className="flex-1 space-y-1">
                <Label htmlFor="np-aufnahmedatum">
                  Aufnahmedatum <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="np-aufnahmedatum"
                  type="date"
                  value={form.aufnahmedatum}
                  onChange={(e) => setField("aufnahmedatum", e.target.value)}
                  disabled={isSubmitting}
                  aria-invalid={!!errors.aufnahmedatum}
                />
                {errors.aufnahmedatum && (
                  <p className="text-xs text-destructive">{errors.aufnahmedatum}</p>
                )}
              </div>
              <div className="w-40 space-y-1">
                <Label>Aufnahmequelle</Label>
                <Select
                  value={form.aufnahme_quelle}
                  onValueChange={(v) => setField("aufnahme_quelle", v as Aufnahmequelle)}
                  disabled={isSubmitting}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="—" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="elektiv">elektiv</SelectItem>
                    <SelectItem value="notfall">notfall</SelectItem>
                    <SelectItem value="extern">extern</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Verlegungsziel */}
            <div className="space-y-1">
              <Label htmlFor="np-verlegungsziel">Verlegungsziel</Label>
              <Input
                id="np-verlegungsziel"
                type="text"
                value={form.verlegungsziel}
                onChange={(e) => setField("verlegungsziel", e.target.value)}
                placeholder="IMC, Normalstation, …"
                disabled={isSubmitting}
              />
            </div>

            {submitError && (
              <p className="text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">
                {submitError}
              </p>
            )}
          </div>

          <DialogFooter className="px-6 py-3 border-t bg-muted/30 shrink-0 -mx-0 -mb-0 rounded-b-xl">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isExtracting || isSubmitting}
            >
              Abbrechen
            </Button>
            <Button
              type="submit"
              disabled={isSubmitting || isExtracting}
            >
              {isSubmitting ? (
                <><Loader2 className="size-4 animate-spin" /> Anlegen…</>
              ) : (
                "Anlegen"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
