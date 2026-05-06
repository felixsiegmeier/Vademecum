import { useRef, useState } from "react";
import { Check, Copy, GraduationCap, Loader2, Pencil, RefreshCw, X } from "lucide-react";
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
  title: string;
  content: string;
  generating?: boolean;
  onRegenerate?: (extraContext?: string) => void;
  onPolish?: (extraContext?: string) => void;
  onLearn?: () => void;
  canLearn?: boolean;
  onSave?: (value: string) => void;
  disabled?: boolean;
}

type RefreshMode = "polish" | "regenerate";

export default function BriefSection({
  title,
  content,
  generating = false,
  onRegenerate,
  onPolish,
  onLearn,
  canLearn = false,
  onSave,
  disabled = false,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [initialDraft, setInitialDraft] = useState("");
  const [copied, setCopied] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Refresh dialog
  const [showRefreshDialog, setShowRefreshDialog] = useState(false);
  const [refreshMode, setRefreshMode] = useState<RefreshMode>("polish");
  const [refreshContext, setRefreshContext] = useState("");

  function startEdit() {
    setDraft(content);
    setInitialDraft(content);
    setEditing(true);
  }

  function handleConfirm() {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    onSave?.(draft);
    setEditing(false);
    setDraft("");
    setSaveStatus("idle");
  }

  function handleCancel() {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    onSave?.(initialDraft);
    setEditing(false);
    setDraft("");
    setSaveStatus("idle");
  }

  function handleChange(value: string) {
    setDraft(value);
    setSaveStatus("saving");
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      onSave?.(value);
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    }, 800);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleConfirm();
    } else if (e.key === "Escape") {
      e.preventDefault();
      handleCancel();
    }
  }

  function handleCopy() {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function handleRefreshConfirm() {
    const ctx = refreshContext.trim() || undefined;
    if (refreshMode === "polish") {
      onPolish?.(ctx);
    } else {
      onRegenerate?.(ctx);
    }
    setRefreshContext("");
    setShowRefreshDialog(false);
  }

  const showRefreshBtn = !editing && (onRegenerate || onPolish);

  return (
    <div className="border rounded-md overflow-hidden">
      <div className="flex items-center gap-1.5 px-3 py-2 bg-muted/40 border-b">
        <h3 className="flex-1 text-sm font-semibold">{title}</h3>

        {!editing && (
          <>
            <Button variant="ghost" size="icon-xs" onClick={handleCopy} title="Kopieren" disabled={disabled}>
              {copied ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
            </Button>
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={startEdit}
              title="Bearbeiten"
              disabled={disabled || generating}
            >
              <Pencil className="size-3.5" />
            </Button>
            {onLearn && (
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={onLearn}
                title={canLearn ? "Aus Änderungen lernen" : "Keine Änderungen seit letzter Generierung"}
                disabled={disabled || !canLearn}
              >
                <GraduationCap className="size-3.5" />
              </Button>
            )}
          </>
        )}

        {editing && (
          <>
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={handleConfirm}
              title="Bestätigen (⌘↵)"
              className="text-emerald-600 hover:text-emerald-700"
            >
              <Check className="size-3.5" />
            </Button>
            <Button variant="ghost" size="icon-xs" onClick={handleCancel} title="Abbrechen (Esc)">
              <X className="size-3.5" />
            </Button>
          </>
        )}

        {showRefreshBtn && (
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => setShowRefreshDialog(true)}
            title="Glätten / Neu generieren"
            disabled={disabled || generating}
          >
            {generating ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RefreshCw className="size-3.5" />
            )}
          </Button>
        )}
      </div>

      <div className="relative">
        {generating && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/70 z-10">
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" /> Generiere…
            </span>
          </div>
        )}

        {editing ? (
          <div className="p-3 space-y-1">
            <Textarea
              value={draft}
              onChange={(e) => handleChange(e.target.value)}
              onKeyDown={handleKeyDown}
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
        ) : content ? (
          <div className="px-4 py-3 prose prose-sm max-w-none text-sm [&_ul]:my-1 [&_li]:my-0">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        ) : (
          <p className="px-4 py-3 text-sm text-muted-foreground italic">Noch nicht generiert.</p>
        )}
      </div>

      {/* Refresh dialog */}
      <Dialog open={showRefreshDialog} onOpenChange={setShowRefreshDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Sektion „{title}" regenerieren</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div className="flex gap-2">
              <button
                onClick={() => setRefreshMode("polish")}
                className={cn(
                  "flex-1 rounded-md border px-3 py-2.5 text-sm text-left transition-colors",
                  refreshMode === "polish"
                    ? "border-primary bg-primary/5 font-medium"
                    : "border-border bg-background text-muted-foreground hover:text-foreground"
                )}
              >
                <div className="font-medium mb-0.5">Glätten</div>
                <div className="text-xs text-muted-foreground">Stilistische Überarbeitung, klinische Fakten bleiben</div>
              </button>
              <button
                onClick={() => setRefreshMode("regenerate")}
                className={cn(
                  "flex-1 rounded-md border px-3 py-2.5 text-sm text-left transition-colors",
                  refreshMode === "regenerate"
                    ? "border-primary bg-primary/5 font-medium"
                    : "border-border bg-background text-muted-foreground hover:text-foreground"
                )}
              >
                <div className="font-medium mb-0.5">Neu generieren</div>
                <div className="text-xs text-muted-foreground">Vollständige Pipeline, Edits werden verworfen</div>
              </button>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Zusatzkontext (optional)
              </label>
              <Textarea
                value={refreshContext}
                onChange={(e) => setRefreshContext(e.target.value)}
                placeholder="Hinweise für diese Regenerierung…"
                rows={3}
                className="text-sm resize-none"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowRefreshDialog(false)}>
              Abbrechen
            </Button>
            <Button onClick={handleRefreshConfirm} disabled={generating}>
              {generating ? (
                <><Loader2 className="size-3.5 animate-spin mr-1" /> Generiere…</>
              ) : (
                "Regenerieren"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
