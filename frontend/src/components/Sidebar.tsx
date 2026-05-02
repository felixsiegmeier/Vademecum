import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import NewPatientDialog from "./NewPatientDialog";

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
      <aside className="w-[280px] flex-shrink-0 border-r border-gray-200 bg-white flex flex-col h-screen overflow-y-auto">
        <div className="px-4 py-4 border-b border-gray-200">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
            Navigation
          </p>
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `block px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-gray-100 text-gray-900"
                  : "text-gray-700 hover:bg-gray-50"
              }`
            }
          >
            Chat
          </NavLink>
        </div>

        <div className="px-4 py-4 flex-1">
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
              Patienten
            </p>
            <button
              onClick={() => setDialogOpen(true)}
              className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-blue-600 hover:bg-blue-50 transition-colors"
              title="Neuen Patienten anlegen"
            >
              <span className="text-base leading-none">+</span>
              <span>Neu</span>
            </button>
          </div>

          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setFilter("aktiv")}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                filter === "aktiv"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              Aktiv
            </button>
            <button
              onClick={() => setFilter("alle")}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                filter === "alle"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              Alle
            </button>
          </div>

          {loading && <p className="text-sm text-gray-400">Lade Patienten…</p>}

          {error && (
            <div>
              <p className="text-sm text-red-600">Fehler beim Laden</p>
              <p className="text-xs text-gray-400 mt-1">{error}</p>
            </div>
          )}

          {!loading && !error && (
            <div className="space-y-1">
              {visible.map((p) => (
                <NavLink
                  key={p.id}
                  to={`/patients/${p.id}/chat`}
                  className={({ isActive }) =>
                    `block px-3 py-2 rounded-lg transition-colors ${
                      isActive ? "bg-gray-100" : "hover:bg-gray-50"
                    }`
                  }
                >
                  <p className="text-sm font-medium text-gray-800">{p.name}</p>
                  <p className="text-xs text-gray-400">
                    {p.bettplatz ?? "—"}
                    {!p.aktiv && <span className="ml-1 text-gray-300">(inaktiv)</span>}
                  </p>
                </NavLink>
              ))}
              {visible.length === 0 && (
                <p className="text-sm text-gray-400">Keine Patienten gefunden.</p>
              )}
            </div>
          )}
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
