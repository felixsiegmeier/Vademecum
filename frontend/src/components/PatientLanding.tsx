import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { MoreHorizontal, Loader2 } from "lucide-react";
import { PatientChatPanel } from "./PatientChatPanel";
import MeilensteinPanel from "./MeilensteinPanel";
import BriefPanel from "./BriefPanel";
import type { Patient } from "../types";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

interface Props {
  onModified: () => void;
}

export default function PatientLanding({ onModified }: Props) {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  const [patient, setPatient] = useState<Patient | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshPatient = useCallback(async () => {
    if (!id) return;
    const res = await fetch(`/api/patients/${id}`);
    if (res.ok) setPatient(await res.json());
  }, [id]);

  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const activeTab = location.pathname.endsWith("/meilenstein")
    ? "meilenstein"
    : location.pathname.endsWith("/brief")
    ? "brief"
    : "chat";

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    setNotFound(false);
    setPatient(null);

    fetch(`/api/patients/${id}`)
      .then((res) => {
        if (res.status === 404) { setNotFound(true); return null; }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => { if (data) setPatient(data); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  // Close menu on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  async function handleSetAktiv(aktiv: boolean) {
    if (!id || actionBusy) return;
    setMenuOpen(false);
    setActionBusy(true);
    try {
      await fetch(`/api/patients/${id}/aktiv`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ aktiv }),
      });
      setPatient((p) => p ? { ...p, stammdaten: { ...p.stammdaten, aktiv } } : p);
      onModified();
    } finally {
      setActionBusy(false);
    }
  }

  async function handleDelete() {
    if (!id || actionBusy) return;
    setActionBusy(true);
    try {
      await fetch(`/api/patients/${id}`, { method: "DELETE" });
      onModified();
      navigate("/");
    } finally {
      setActionBusy(false);
      setConfirmDelete(false);
    }
  }

  if (loading) return <div className="p-8 text-sm text-muted-foreground">Lade Patient…</div>;
  if (notFound) return <div className="p-8 text-sm text-foreground">Patient nicht gefunden.</div>;
  if (error) return <div className="p-8 text-sm text-destructive">Fehler beim Laden: {error}</div>;
  if (!patient) return null;

  const { name, bettplatz, aktiv, aufnahmedatum } = patient.stammdaten;

  function handleTabChange(value: string) {
    if (value === activeTab) return;
    navigate(`/patients/${id}/${value}`);
  }

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Header */}
      <div className="bg-card border-b px-6 py-3 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-foreground truncate">{name}</h1>
            {!aktiv && (
              <Badge variant="outline" className="text-[10px]">inaktiv</Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {bettplatz ?? "—"} · Aufnahme: {aufnahmedatum}
          </p>
        </div>

        {/* Action menu */}
        <div className="relative shrink-0" ref={menuRef}>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setMenuOpen((o) => !o)}
            disabled={actionBusy}
            title="Patientenaktionen"
          >
            <MoreHorizontal className="size-4" />
          </Button>
          {menuOpen && (
            <div className="absolute right-0 top-full mt-1 w-48 bg-popover text-popover-foreground border rounded-md shadow-md z-20 py-1">
              <button
                onClick={() => handleSetAktiv(!aktiv)}
                className="w-full text-left px-3 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground"
              >
                {aktiv ? "Auf inaktiv setzen" : "Auf aktiv setzen"}
              </button>
              <div className="border-t my-1" />
              <button
                onClick={() => { setMenuOpen(false); setConfirmDelete(true); }}
                className="w-full text-left px-3 py-1.5 text-sm text-destructive hover:bg-destructive/10"
              >
                Patient löschen
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Tab bar */}
      <div className="bg-card border-b px-4">
        <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
          <TabsList variant="line" className="h-10 bg-transparent">
            <TabsTrigger value="chat">Chat</TabsTrigger>
            <TabsTrigger value="meilenstein">Meilenstein</TabsTrigger>
            <TabsTrigger value="brief">Brief</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Content */}
      <div className={cn("flex-1 overflow-hidden", actionBusy && "opacity-50 pointer-events-none")}>
        {activeTab === "chat" && (
          <PatientChatPanel
            patientId={id!}
            patient={patient}
            refreshPatient={refreshPatient}
            onPatientChanged={onModified}
          />
        )}
        {activeTab === "meilenstein" && <MeilensteinPanel patientId={id!} />}
        {activeTab === "brief" && <BriefPanel patientId={id!} />}
      </div>

      {/* Delete confirm modal */}
      <Dialog open={confirmDelete} onOpenChange={(o) => !o && !actionBusy && setConfirmDelete(false)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Patient löschen?</DialogTitle>
            <DialogDescription>
              Diese Aktion ist nicht umkehrbar. Patient, Meilenstein und Uploads werden gelöscht.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmDelete(false)}
              disabled={actionBusy}
            >
              Abbrechen
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={actionBusy}
            >
              {actionBusy ? (<><Loader2 className="size-4 animate-spin" />Löschen…</>) : "Löschen"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
