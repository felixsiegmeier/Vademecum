import { useRef, useState } from "react";
import { Check, Copy, Loader2, Pencil, RefreshCw, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

interface Props {
  title: string;
  content: string;
  generating?: boolean;
  onRegenerate?: () => void;
  onSave?: (value: string) => void;
  disabled?: boolean;
}

export default function BriefSection({
  title,
  content,
  generating = false,
  onRegenerate,
  onSave,
  disabled = false,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [copied, setCopied] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
          </>
        )}

        {editing && (
          <Button variant="ghost" size="icon-xs" onClick={cancelEdit} title="Abbrechen">
            <X className="size-3.5" />
          </Button>
        )}

        {onRegenerate && !editing && (
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={onRegenerate}
            title="Neu generieren"
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
