import { useRef, useState } from "react";
import { FileText, Loader2, Paperclip, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { extractFileText } from "../api/brief";

interface Props {
  disabled?: boolean;
  onGenerate: (extraContext: string, befundeRaw: string) => Promise<void>;
}

export default function BriefOnboarding({ disabled = false, onGenerate }: Props) {
  const [context, setContext] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [befundeRaw, setBefundeRaw] = useState("");
  const [generating, setGenerating] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleAddFiles(incoming: FileList | null) {
    if (!incoming) return;
    const newFiles = Array.from(incoming);
    setExtracting(true);
    try {
      const extracted = await extractFileText(newFiles);
      setContext((prev) => (prev.trim() ? prev + "\n\n" + extracted : extracted));
      setFiles((prev) => [...prev, ...newFiles]);
    } catch {
      setFiles((prev) => [...prev, ...newFiles]);
    } finally {
      setExtracting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleGenerate() {
    setGenerating(true);
    try {
      await onGenerate(context.trim(), befundeRaw.trim());
    } finally {
      setGenerating(false);
    }
  }

  const busy = disabled || extracting || generating;

  return (
    <div className="flex flex-col items-center justify-center h-full px-6 py-8">
      <div className="w-full max-w-xl space-y-5">
        <div className="flex items-center gap-2">
          <FileText className="size-5 text-muted-foreground" />
          <h2 className="text-base font-semibold">Brief generieren</h2>
        </div>

        {/* Slot 1: Context */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">
            Kontext (optional)
          </label>
          <Textarea
            value={context}
            onChange={(e) => setContext(e.target.value)}
            placeholder="Allgemeiner Kontext für die Brief-Generierung — z.B. Verlegungsanlass, besondere Hinweise zur Doku, klinische Besonderheiten des Aufenthalts."
            rows={4}
            className="text-sm resize-none"
            disabled={busy}
          />
          <div className="flex items-center gap-2">
            <input
              ref={fileRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => handleAddFiles(e.target.files)}
            />
            <Button
              variant="ghost"
              size="sm"
              className="text-xs h-7 px-2"
              onClick={() => fileRef.current?.click()}
              disabled={busy}
              type="button"
            >
              {extracting ? (
                <><Loader2 className="size-3.5 animate-spin mr-1" /> Extrahiere…</>
              ) : (
                <><Paperclip className="size-3.5 mr-1" /> Datei hinzufügen</>
              )}
            </Button>
          </div>
          {files.length > 0 && (
            <ul className="space-y-0.5 pl-1">
              {files.map((f, i) => (
                <li key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Paperclip className="size-3 shrink-0" />
                  <span className="flex-1 truncate">{f.name}</span>
                  <button
                    type="button"
                    onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                  >
                    <X className="size-3" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Slot 2: SAP Befunde */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">
            SAP-Befunde (optional)
          </label>
          <Textarea
            value={befundeRaw}
            onChange={(e) => setBefundeRaw(e.target.value)}
            placeholder="SAP-Befunde-Block hier einfügen — wird automatisch formatiert und in die Befunde-Sektion übernommen. Kann auch später über die Befunde-Sektion nachgereicht werden."
            rows={4}
            className="text-sm resize-none font-mono"
            disabled={busy}
          />
        </div>

        {/* Generate button */}
        <div className="flex justify-end">
          <Button
            onClick={handleGenerate}
            disabled={busy}
            size="default"
            className="min-w-36"
          >
            {generating ? (
              <><Loader2 className="size-4 animate-spin mr-2" /> Generiere…</>
            ) : (
              "Brief generieren"
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
