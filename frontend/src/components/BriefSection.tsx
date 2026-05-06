import { useRef, useState } from "react";
import { Check, Copy, GraduationCap, Loader2, MessageSquarePlus, Pencil, RefreshCw, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

interface Props {
  title: string;
  content: string;
  generating?: boolean;
  onRegenerate?: (extraContext?: string) => void;
  onLearn?: () => void;
  canLearn?: boolean;
  onSave?: (value: string) => void;
  disabled?: boolean;
}

export default function BriefSection({
  title,
  content,
  generating = false,
  onRegenerate,
  onLearn,
  canLearn = false,
  onSave,
  disabled = false,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [copied, setCopied] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [showContext, setShowContext] = useState(false);
  const [contextText, setContextText] = useState("");

  function startEdit() {
    setDraft(content);
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
    setDraft("");
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

  function handleCopy() {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function handleRegenerate() {
    onRegenerate?.(contextText.trim() || undefined);
    setContextText("");
    setShowContext(false);
  }

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
          <Button variant="ghost" size="icon-xs" onClick={cancelEdit} title="Abbrechen">
            <X className="size-3.5" />
          </Button>
        )}

        {onRegenerate && !editing && (
          <>
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={() => setShowContext((v) => !v)}
              title="Zusatzkontext eingeben"
              disabled={disabled || generating}
              className={cn(showContext && "text-amber-600 bg-amber-50")}
            >
              <MessageSquarePlus className="size-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={handleRegenerate}
              title="Neu generieren"
              disabled={disabled || generating}
            >
              {generating ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <RefreshCw className="size-3.5" />
              )}
            </Button>
          </>
        )}
      </div>

      {showContext && !editing && (
        <div className="border-b bg-amber-50/50 px-3 py-2 flex gap-2 items-start">
          <Textarea
            value={contextText}
            onChange={(e) => setContextText(e.target.value)}
            placeholder="Zusatzkontext für Neu-Generierung…"
            rows={2}
            className="flex-1 text-xs resize-none bg-white"
            autoFocus
          />
          <Button
            size="xs"
            variant="ghost"
            onClick={() => { setShowContext(false); setContextText(""); }}
            className="mt-0.5 shrink-0"
          >
            <X className="size-3" />
          </Button>
        </div>
      )}

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
    </div>
  );
}
