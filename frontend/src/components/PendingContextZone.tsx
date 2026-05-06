import { useRef, useState } from "react";
import { ChevronDown, ChevronRight, Paperclip, X, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { extractFileText } from "../api/brief";

interface Props {
  onSubmit: (context: string) => void;
  disabled?: boolean;
}

export default function PendingContextZone({ onSubmit, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [extracting, setExtracting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleAddFiles(incoming: FileList | null) {
    if (!incoming) return;
    const newFiles = Array.from(incoming);
    setExtracting(true);
    try {
      const extracted = await extractFileText(newFiles);
      setText((prev) => (prev.trim() ? prev + "\n\n" + extracted : extracted));
      setFiles((prev) => [...prev, ...newFiles]);
    } catch {
      // silently keep files in list so user can still submit manual text
      setFiles((prev) => [...prev, ...newFiles]);
    } finally {
      setExtracting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  function handleSubmit() {
    if (!text.trim()) return;
    onSubmit(text.trim());
    setText("");
    setFiles([]);
    setOpen(false);
  }

  return (
    <div className="border-b bg-muted/30">
      <button
        className="flex w-full items-center gap-1.5 px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        onClick={() => setOpen((o) => !o)}
        type="button"
      >
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        Zusatz-Kontext für nächste Generierung
      </button>

      {open && (
        <div className="px-4 pb-3 space-y-2">
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Freitext oder extrahierter Dateiinhalt — wird einmalig an alle Sub-Agents übergeben, nicht gespeichert."
            rows={4}
            className="text-sm resize-none"
            disabled={disabled || extracting}
          />

          {files.length > 0 && (
            <ul className="space-y-0.5">
              {files.map((f, i) => (
                <li key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Paperclip className="size-3 shrink-0" />
                  <span className="flex-1 truncate">{f.name}</span>
                  <button onClick={() => removeFile(i)} type="button">
                    <X className="size-3" />
                  </button>
                </li>
              ))}
            </ul>
          )}

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
              onClick={() => fileRef.current?.click()}
              disabled={disabled || extracting}
            >
              {extracting ? (
                <><Loader2 className="size-3.5 animate-spin" /> Extrahiere…</>
              ) : (
                <><Paperclip className="size-3.5" /> Datei hinzufügen</>
              )}
            </Button>
            <div className="flex-1" />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => { setText(""); setFiles([]); setOpen(false); }}
              disabled={disabled}
            >
              Verwerfen
            </Button>
            <Button
              size="sm"
              onClick={handleSubmit}
              disabled={disabled || extracting || !text.trim()}
            >
              Übernehmen
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
