import { useEffect, useRef, useState } from "react";
import { Check, Copy, Loader2, Pencil, RefreshCw, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

interface Props {
  content: string;
  formatting?: boolean;
  onFormat: (rawText: string) => Promise<void>;
  onSave: (value: string) => void;
  disabled?: boolean;
}

export default function BefundeSection({
  content,
  formatting = false,
  onFormat,
  onSave,
  disabled = false,
}: Props) {
  const [mode, setMode] = useState<"view" | "paste" | "edit">(content ? "view" : "paste");
  const [rawText, setRawText] = useState("");
  const [draft, setDraft] = useState("");
  const [reforDialog, setReforDialog] = useState(false);
  const [reforRaw, setReforRaw] = useState("");
  const [copied, setCopied] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (content && mode === "paste") setMode("view");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content]);

  async function handleFormat() {
    await onFormat(rawText);
    setRawText("");
  }

  async function handleReformat() {
    await onFormat(reforRaw);
    setReforRaw("");
    setReforDialog(false);
  }

  function startEdit() {
    setDraft(content);
    setMode("edit");
  }

  function cancelEdit() {
    setMode("view");
    setDraft("");
  }

  function handleChange(value: string) {
    setDraft(value);
    setSaveStatus("saving");
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      onSave(value);
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    }, 800);
  }

  function handleCopy() {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <>
      <div className="border rounded-md overflow-hidden">
        <div className="flex items-center gap-1.5 px-3 py-2 bg-muted/40 border-b">
          <h3 className="flex-1 text-sm font-semibold">Befunde</h3>

          {mode === "view" && (
            <>
              <Button variant="ghost" size="icon-xs" onClick={handleCopy} title="Kopieren" disabled={disabled}>
                {copied ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
              </Button>
              <Button variant="ghost" size="icon-xs" onClick={startEdit} title="Bearbeiten" disabled={disabled || formatting}>
                <Pencil className="size-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={() => { setReforRaw(""); setReforDialog(true); }}
                title="Neu formatieren"
                disabled={disabled || formatting}
              >
                {formatting ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
              </Button>
            </>
          )}

          {mode === "edit" && (
            <Button variant="ghost" size="icon-xs" onClick={cancelEdit} title="Abbrechen">
              <X className="size-3.5" />
            </Button>
          )}
        </div>

        <div className="relative">
          {formatting && (
            <div className="absolute inset-0 flex items-center justify-center bg-background/70 z-10">
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" /> Formatiere…
              </span>
            </div>
          )}

          {mode === "paste" && (
            <div className="p-3 space-y-2">
              <p className="text-xs text-muted-foreground">SAP-Befunde einfügen und formatieren lassen:</p>
              <Textarea
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                placeholder="Roh-Befunde aus SAP hier einfügen…"
                rows={6}
                className="text-sm resize-none font-mono"
                disabled={disabled || formatting}
                spellCheck={false}
              />
              <div className="flex justify-end gap-2">
                <Button
                  size="sm"
                  onClick={handleFormat}
                  disabled={disabled || formatting || !rawText.trim()}
                >
                  {formatting ? (
                    <><Loader2 className="size-3.5 animate-spin" /> Formatiere…</>
                  ) : (
                    "Formatieren"
                  )}
                </Button>
              </div>
            </div>
          )}

          {mode === "view" && content && (
            <div className="px-4 py-3 prose prose-sm max-w-none text-sm [&_ul]:my-1 [&_li]:my-0">
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
          )}

          {mode === "edit" && (
            <div className="p-3 space-y-1">
              <Textarea
                value={draft}
                onChange={(e) => handleChange(e.target.value)}
                rows={8}
                className="text-sm resize-none w-full font-mono"
                spellCheck={false}
                autoFocus
              />
              <div className={cn("h-4", saveStatus === "idle" && "invisible")}>
                {saveStatus === "saving" && (
                  <span className="text-xs text-muted-foreground">Speichert…</span>
                )}
                {saveStatus === "saved" && (
                  <span className="text-xs text-emerald-600">Gespeichert</span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <Dialog open={reforDialog} onOpenChange={setReforDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Befunde neu formatieren</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Neuen SAP-Roh-Export einfügen. Der bestehende formatierte Text wird ersetzt.
          </p>
          <Textarea
            value={reforRaw}
            onChange={(e) => setReforRaw(e.target.value)}
            placeholder="SAP-Roh-Export…"
            rows={8}
            className="text-sm font-mono resize-none"
            spellCheck={false}
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setReforDialog(false)}>Abbrechen</Button>
            <Button onClick={handleReformat} disabled={!reforRaw.trim() || formatting}>
              {formatting ? <><Loader2 className="size-3.5 animate-spin" /> Formatiere…</> : "Formatieren"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
