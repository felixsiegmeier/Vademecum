import { useState } from "react";
import { ChevronDown, ChevronRight, AlertCircle, Pencil, FileText } from "lucide-react";
import {
  type ArgsRecord,
  type ArgValue,
  type Patient,
  type Proposal,
  type ToolCall,
  STAMMDATEN_FELD_LABELS,
  THERAPIE_KATEGORIEN,
  TOOL_LABELS,
} from "../types";
import { resolveById } from "../utils/resolveById";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
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
  proposal: Proposal;
  patient: Patient | null;
  selected: boolean;
  onToggle: () => void;
  /** Args werden zurückgegeben — bei "update" via add_call, bei add/update_singleton via call. delete editiert nichts. */
  onArgsChange: (args: ArgsRecord) => void;
  /** Optional: Apply ist fehlgeschlagen — Inline-Fehler anzeigen. */
  failedSummary?: string | null;
}

const READONLY_KEYS = new Set(["source_quote", "id"]);
const DATE_KEY_HINTS = ["datum", "beginn", "ende", "geburtsdatum", "aufnahmedatum"];

function isDateKey(key: string): boolean {
  return DATE_KEY_HINTS.includes(key) || key.endsWith("datum");
}

function shorten(text: string, max = 60): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "…";
}

function getMainTextFromAdd(args: ArgsRecord, tool: string): string {
  if (tool === "add_therapie") return String(args.bezeichnung ?? "");
  return String(args.text ?? args.bezeichnung ?? "");
}

function getSingletonMainText(call: ToolCall): string {
  const { tool, args } = call;
  switch (tool) {
    case "update_anamnese":
    case "update_therapieziel":
      return String(args.text ?? "");
    case "update_status":
      return `aktiv: ${args.aktiv ? "ja" : "nein"}`;
    case "update_bettplatz":
      return String(args.bettplatz ?? "");
    case "update_verlegungsziel":
      return String(args.verlegungsziel ?? "");
    case "update_stammdaten": {
      const feld = String(args.feld ?? "");
      const wert = String(args.wert ?? "");
      const label = STAMMDATEN_FELD_LABELS[feld] ?? feld;
      return `${label}: ${wert}`;
    }
    default:
      return "";
  }
}

interface ArgFieldProps {
  argKey: string;
  value: ArgValue;
  onChange: (key: string, value: ArgValue) => void;
  readOnly?: boolean;
  isStammdatenFeld?: boolean;
  /** Value of the `feld` arg when rendering the `wert` key for update_stammdaten. */
  stammdatenFeldContext?: string;
}

function ArgField({ argKey, value, onChange, readOnly, isStammdatenFeld, stammdatenFeldContext }: ArgFieldProps) {
  const ro = readOnly || READONLY_KEYS.has(argKey) || isStammdatenFeld;
  const labelEl = (
    <Label className="text-xs font-medium text-muted-foreground mb-1">{argKey}</Label>
  );

  // Boolean (update_status.aktiv)
  if (typeof value === "boolean") {
    return (
      <div className="space-y-1">
        {labelEl}
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={value}
            disabled={ro}
            onCheckedChange={(v) => onChange(argKey, v === true)}
          />
          <span>{value ? "aktiv" : "inaktiv"}</span>
        </label>
      </div>
    );
  }

  // Therapie-Kategorie als Select
  if (argKey === "kategorie") {
    return (
      <div className="space-y-1">
        {labelEl}
        <Select
          value={String(value ?? "")}
          disabled={ro}
          onValueChange={(v) => onChange(argKey, v)}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(THERAPIE_KATEGORIEN).map(([key, meta]) => (
              <SelectItem key={key} value={key}>
                {meta.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  }

  const stringValue = String(value ?? "");

  // Source-Quote oder andere read-only Felder grau anzeigen
  if (ro) {
    return (
      <div className="space-y-1">
        {labelEl}
        <div className="w-full rounded-md border bg-muted/40 px-2.5 py-1.5 text-xs text-muted-foreground whitespace-pre-wrap break-words min-h-[1.5rem]">
          {stringValue || <span className="italic">(leer)</span>}
        </div>
      </div>
    );
  }

  // update_stammdaten: typed input for 'wert' based on which field is being edited
  if (argKey === "wert" && stammdatenFeldContext) {
    if (stammdatenFeldContext === "geschlecht") {
      return (
        <div className="space-y-1">
          {labelEl}
          <Select
            value={stringValue}
            onValueChange={(v) => onChange(argKey, v)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="—" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="m">m — männlich</SelectItem>
              <SelectItem value="w">w — weiblich</SelectItem>
              <SelectItem value="d">d — divers</SelectItem>
            </SelectContent>
          </Select>
        </div>
      );
    }
    if (stammdatenFeldContext === "geburtsdatum" || stammdatenFeldContext === "aufnahmedatum") {
      return (
        <div className="space-y-1">
          {labelEl}
          <Input
            type="date"
            value={stringValue}
            onChange={(e) => onChange(argKey, e.target.value)}
          />
        </div>
      );
    }
    if (stammdatenFeldContext === "aufnahme_quelle") {
      return (
        <div className="space-y-1">
          {labelEl}
          <Input
            type="text"
            value={stringValue}
            placeholder="z.B. elektiv, notfall, extern"
            onChange={(e) => onChange(argKey, e.target.value)}
          />
        </div>
      );
    }
  }

  if (isDateKey(argKey)) {
    return (
      <div className="space-y-1">
        {labelEl}
        <Input
          type="date"
          value={stringValue}
          onChange={(e) => onChange(argKey, e.target.value)}
        />
      </div>
    );
  }

  if (stringValue.length > 60) {
    return (
      <div className="space-y-1">
        {labelEl}
        <Textarea
          value={stringValue}
          rows={3}
          onChange={(e) => onChange(argKey, e.target.value)}
          className="resize-none"
        />
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {labelEl}
      <Input
        type="text"
        value={stringValue}
        onChange={(e) => onChange(argKey, e.target.value)}
      />
    </div>
  );
}

function styleForType(type: Proposal["type"], selected: boolean): string {
  if (!selected) {
    return "border-border bg-muted/20 opacity-60";
  }
  switch (type) {
    case "delete":
      return "border-destructive/30 bg-destructive/5";
    case "update":
      return "border-amber-300 bg-amber-50/60";
    default:
      return "border-blue-200 bg-blue-50/40";
  }
}

export default function ProposalCard({
  proposal,
  patient,
  selected,
  onToggle,
  onArgsChange,
  failedSummary,
}: Props) {
  // Welche Args sind editierbar? add/update_singleton: call.args; update: add_call.args; delete: nichts.
  const editableSourceArgs: ArgsRecord | null =
    proposal.type === "update" ? (proposal.add_call?.args ?? null) :
    proposal.type === "delete" ? null :
    (proposal.call?.args ?? null);

  const [expanded, setExpanded] = useState(false);
  const [showQuote, setShowQuote] = useState(false);
  const [localArgs, setLocalArgs] = useState<ArgsRecord>(editableSourceArgs ?? {});

  function handleArgChange(key: string, value: ArgValue) {
    const next = { ...localArgs, [key]: value };
    setLocalArgs(next);
    onArgsChange(next);
  }

  // ── Header + mainText pro Discriminator bauen ──
  let header: React.ReactNode = null;
  let mainContent: React.ReactNode = null;
  let kategorieBadge: React.ReactNode = null;
  let sourceQuote = "";

  if (proposal.type === "add" && proposal.call) {
    const { tool, args } = proposal.call;
    header = TOOL_LABELS[tool] ?? tool;
    sourceQuote = String(args.source_quote ?? "");
    if (tool === "add_therapie") {
      const kat = String(args.kategorie ?? "");
      const meta = THERAPIE_KATEGORIEN[kat];
      if (meta) {
        kategorieBadge = (
          <Badge variant="secondary" className="ml-2">
            {meta.label}
          </Badge>
        );
      }
    }
    mainContent = <span className="text-foreground/70">{shorten(getMainTextFromAdd(localArgs, tool))}</span>;
  } else if (proposal.type === "update_singleton" && proposal.call) {
    const { tool, args } = proposal.call;
    sourceQuote = String(args.source_quote ?? "");
    if (tool === "update_stammdaten") {
      header = TOOL_LABELS[tool];
      const feld = String(args.feld ?? "");
      const wert = String(args.wert ?? "");
      const label = STAMMDATEN_FELD_LABELS[feld] ?? feld;
      mainContent = <span className="text-foreground/70">{shorten(`${label}: ${wert}`)}</span>;
    } else {
      header = TOOL_LABELS[tool] ?? tool;
      const previewCall: ToolCall = { tool, args: { ...args, ...localArgs } };
      mainContent = <span className="text-foreground/70">{shorten(getSingletonMainText(previewCall))}</span>;
    }
  } else if (proposal.type === "update" && proposal.add_call && proposal.delete_call) {
    const addTool = proposal.add_call.tool;
    header = TOOL_LABELS[addTool] ?? addTool;
    sourceQuote = String(proposal.add_call.args.source_quote ?? "");
    if (addTool === "add_therapie") {
      const kat = String((localArgs.kategorie ?? proposal.add_call.args.kategorie) ?? "");
      const meta = THERAPIE_KATEGORIEN[kat];
      if (meta) {
        kategorieBadge = (
          <Badge variant="secondary" className="ml-2">
            {meta.label}
          </Badge>
        );
      }
    }
    const oldId = String(proposal.delete_call.args.id ?? "");
    const resolved = resolveById(patient, oldId);
    const newText = getMainTextFromAdd(localArgs, addTool);
    if (resolved) {
      mainContent = (
        <span className="text-foreground/70">
          <span className="line-through text-muted-foreground">{shorten(resolved.text)}</span>
          <span className="mx-1.5 text-muted-foreground">→</span>
          <span className="font-medium text-foreground">{shorten(newText)}</span>
        </span>
      );
    } else {
      mainContent = (
        <span className="text-foreground/70">
          <span className="italic text-muted-foreground line-through">
            Eintrag …{oldId.slice(-6)} (nicht im Stand auffindbar)
          </span>
          <span className="mx-1.5 text-muted-foreground">→</span>
          <span className="font-medium text-foreground">{shorten(newText)}</span>
        </span>
      );
    }
  } else if (proposal.type === "delete" && proposal.call) {
    const args = proposal.call.args;
    sourceQuote = String(args.source_quote ?? "");
    const oldId = String(args.id ?? "");
    const resolved = resolveById(patient, oldId);
    header = resolved
      ? `${TOOL_LABELS["delete_entry"]} — ${resolved.section}`
      : TOOL_LABELS["delete_entry"];
    mainContent = resolved ? (
      <span className="line-through text-muted-foreground">{shorten(resolved.text)}</span>
    ) : (
      <span className="italic text-muted-foreground">
        Eintrag …{oldId.slice(-6)} <span>(nicht im Stand auffindbar)</span>
      </span>
    );
  }

  const styleClass = styleForType(proposal.type, selected);
  const isUpdate = proposal.type === "update";

  // Diff-View-Daten für Update-Gruppen
  const diffOldText = isUpdate && proposal.delete_call
    ? resolveById(patient, String(proposal.delete_call.args.id ?? ""))?.text ?? null
    : null;
  const diffOldId = isUpdate && proposal.delete_call
    ? String(proposal.delete_call.args.id ?? "")
    : "";

  return (
    <div className={cn("rounded-md border text-sm transition-colors", styleClass, failedSummary && "border-destructive/40")}>
      {/* Header row */}
      <div className="flex items-start gap-2 px-3 py-2">
        <Checkbox
          checked={selected}
          onCheckedChange={onToggle}
          className="mt-0.5"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline">
            <span className="font-medium text-foreground">{header}</span>
            {kategorieBadge}
          </div>
          {mainContent && <div className="mt-0.5 truncate">{mainContent}</div>}
        </div>
        <div className="flex gap-1 shrink-0">
          <Button
            variant="ghost"
            size="xs"
            onClick={() => setExpanded((v) => !v)}
            className="text-primary"
          >
            {expanded ? <ChevronDown className="size-3.5" /> : <Pencil className="size-3.5" />}
            <span className="ml-1">
              {expanded ? "Schließen" : isUpdate ? "Details" : proposal.type === "delete" ? "Details" : "Bearbeiten"}
            </span>
          </Button>
          {sourceQuote && (
            <Button
              variant="ghost"
              size="xs"
              onClick={() => setShowQuote((v) => !v)}
              className="text-muted-foreground"
            >
              {showQuote ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
              <FileText className="size-3.5" />
              <span className="ml-1">Quelle</span>
            </Button>
          )}
        </div>
      </div>

      {/* Edit / details mode */}
      {expanded && (
        <div className="border-t px-3 py-2 space-y-2 bg-background/40">

          {/* delete: ID + source_quote read-only */}
          {proposal.type === "delete" && proposal.call && (
            <>
              <ArgField
                argKey="id"
                value={String(proposal.call.args.id ?? "")}
                onChange={() => {}}
                readOnly
              />
              <ArgField
                argKey="source_quote"
                value={String(proposal.call.args.source_quote ?? "")}
                onChange={() => {}}
                readOnly
              />
            </>
          )}

          {/* add / update_singleton: generischer Arg-Loop */}
          {(proposal.type === "add" || proposal.type === "update_singleton") && editableSourceArgs &&
            Object.entries(localArgs).map(([key, value]) => {
              const isStammFeld =
                proposal.type === "update_singleton" &&
                proposal.call?.tool === "update_stammdaten" &&
                key === "feld";
              const stammdatenFeldContext =
                proposal.type === "update_singleton" &&
                proposal.call?.tool === "update_stammdaten" &&
                key === "wert"
                  ? String(localArgs.feld ?? "")
                  : undefined;
              return (
                <ArgField
                  key={key}
                  argKey={key}
                  value={value}
                  onChange={handleArgChange}
                  isStammdatenFeld={isStammFeld}
                  stammdatenFeldContext={stammdatenFeldContext}
                />
              );
            })}

          {/* update: Diff-View (Alter Eintrag → Neuer Eintrag) + restliche Felder */}
          {isUpdate && proposal.add_call && (
            <>
              {/* Bisheriger Eintrag */}
              <div>
                <p className="text-xs font-medium text-destructive/80 mb-1">Bisheriger Eintrag</p>
                {diffOldText !== null ? (
                  <div className="w-full rounded-md border border-destructive/20 bg-destructive/5 px-2.5 py-1.5 text-xs text-muted-foreground whitespace-pre-wrap break-words">
                    <s>{diffOldText}</s>
                  </div>
                ) : (
                  <div className="text-xs italic text-muted-foreground">
                    Eintrag …{diffOldId.slice(-6)} nicht im aktuellen Stand auffindbar.
                  </div>
                )}
              </div>

              {/* Neuer Eintrag (Merge, bearbeitbar) */}
              <div className="space-y-1">
                <Label className="text-xs font-medium text-primary mb-1">Neuer Eintrag (Merge)</Label>
                <Textarea
                  value={String(localArgs.text ?? proposal.add_call.args.text ?? "")}
                  rows={4}
                  onChange={(e) => handleArgChange("text", e.target.value)}
                  className="resize-none border-primary/30 bg-primary/5"
                />
              </div>

              {/* Restliche Felder (datum, source_quote) — ohne text */}
              {Object.entries(localArgs)
                .filter(([key]) => key !== "text")
                .map(([key, value]) => (
                  <ArgField key={key} argKey={key} value={value} onChange={handleArgChange} />
                ))}

              {/* zu löschende ID */}
              <ArgField
                argKey="(zu löschende ID)"
                value={diffOldId}
                onChange={() => {}}
                readOnly
              />
            </>
          )}
        </div>
      )}

      {/* Source quote */}
      {showQuote && sourceQuote && (
        <div className="border-t px-3 py-2 bg-background/40">
          <p className="text-xs text-muted-foreground mb-1">Quelle:</p>
          <p className="text-xs italic text-muted-foreground whitespace-pre-wrap">{sourceQuote}</p>
        </div>
      )}

      {/* Apply-Fehler inline */}
      {failedSummary && (
        <div className="border-t border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive flex items-center gap-1.5">
          <AlertCircle className="size-3.5 shrink-0" />
          <span>{failedSummary}</span>
        </div>
      )}
    </div>
  );
}
