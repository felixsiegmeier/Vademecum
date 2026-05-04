import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { Plus, MessageSquare } from "lucide-react";
import NewPatientDialog from "./NewPatientDialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

interface PatientSummary {
  id: string;
  name: string;
  aktiv: boolean;
  bettplatz: string | null;
  aufnahmedatum: string;
}

type Filter = "aktiv" | "alle";

interface Props {
  refreshTrigger: number;
  onPatientCreated: (patientId: string) => void;
}

export default function Sidebar({ refreshTrigger, onPatientCreated }: Props) {
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("aktiv");
  const [dialogOpen, setDialogOpen] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch("/api/patients")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(setPatients)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [refreshTrigger]);

  const visible =
    filter === "aktiv" ? patients.filter((p) => p.aktiv) : patients;

  return (
    <>
      <aside className="w-[280px] flex-shrink-0 border-r bg-sidebar text-sidebar-foreground flex flex-col h-screen">
        <div className="px-4 py-4 border-b">
          <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Navigation
          </p>
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2 px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-accent text-foreground"
                  : "text-foreground/80 hover:bg-sidebar-accent/50",
              )
            }
          >
            <MessageSquare className="size-4" />
            Chat
          </NavLink>
        </div>

        <div className="px-4 py-4 flex-1 flex flex-col min-h-0">
          <div className="flex items-center justify-between mb-3">
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Patienten
            </p>
            <Button
              size="xs"
              variant="ghost"
              onClick={() => setDialogOpen(true)}
              className="text-primary"
            >
              <Plus className="size-3.5" />
              Neu
            </Button>
          </div>

          <div className="flex gap-1 mb-3">
            <Button
              variant={filter === "aktiv" ? "default" : "ghost"}
              size="xs"
              onClick={() => setFilter("aktiv")}
              className="flex-1"
            >
              Aktiv
            </Button>
            <Button
              variant={filter === "alle" ? "default" : "ghost"}
              size="xs"
              onClick={() => setFilter("alle")}
              className="flex-1"
            >
              Alle
            </Button>
          </div>

          <Separator className="mb-2" />

          <ScrollArea className="flex-1 -mx-1 pr-1">
            <div className="px-1">
              {loading && <p className="text-sm text-muted-foreground py-1">Lade Patienten…</p>}

              {error && (
                <div className="space-y-1">
                  <p className="text-sm text-destructive">Fehler beim Laden</p>
                  <p className="text-xs text-muted-foreground">{error}</p>
                </div>
              )}

              {!loading && !error && (
                <div className="space-y-0.5">
                  {visible.map((p) => (
                    <NavLink
                      key={p.id}
                      to={`/patients/${p.id}/chat`}
                      className={({ isActive }) =>
                        cn(
                          "block px-2.5 py-1.5 rounded-md transition-colors border-l-2",
                          isActive
                            ? "bg-sidebar-accent border-primary"
                            : "border-transparent hover:bg-sidebar-accent/50",
                        )
                      }
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-medium text-foreground truncate">{p.name}</p>
                        {!p.aktiv && (
                          <Badge variant="outline" className="text-[10px] h-4 px-1.5">inaktiv</Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground truncate">
                        {p.bettplatz ?? "—"}
                      </p>
                    </NavLink>
                  ))}
                  {visible.length === 0 && (
                    <p className="text-sm text-muted-foreground py-1">Keine Patienten gefunden.</p>
                  )}
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      </aside>

      <NewPatientDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={(patientId) => {
          setDialogOpen(false);
          onPatientCreated(patientId);
        }}
      />
    </>
  );
}
