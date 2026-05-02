import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useLocation } from "react-router-dom";
import { PatientChatPanel } from "./PatientChatPanel";
import MeilensteinPanel from "./MeilensteinPanel";
import BriefPanel from "./BriefPanel";

interface Patient {
  stammdaten: {
    id: string;
    name: string;
    bettplatz: string | null;
    aktiv: boolean;
    aufnahmedatum: string;
    geburtsdatum?: string;
  };
}

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

  if (loading) return <div className="p-8 text-sm text-gray-400">Lade Patient…</div>;
  if (notFound) return <div className="p-8 text-sm text-gray-600">Patient nicht gefunden.</div>;
  if (error) return <div className="p-8 text-sm text-red-600">Fehler beim Laden: {error}</div>;
  if (!patient) return null;

  const { name, bettplatz, aktiv, aufnahmedatum } = patient.stammdaten;

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4 shadow-sm">
        <h1 className="text-xl font-semibold text-gray-900">{name}</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {bettplatz ?? "—"} · {aktiv ? "aktiv" : "inaktiv"} · Aufnahme: {aufnahmedatum}
        </p>
      </div>

      {/* Tab bar */}
      <div className="bg-white border-b flex items-center px-4">
        <Link
          to={`/patients/${id}/chat`}
          className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "chat"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          Chat
        </Link>
        <Link
          to={`/patients/${id}/meilenstein`}
          className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "meilenstein"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          Meilenstein
        </Link>
        <Link
          to={`/patients/${id}/brief`}
          className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "brief"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          Brief
        </Link>

        {/* Spacer + action menu */}
        <div className="ml-auto relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((o) => !o)}
            disabled={actionBusy}
            className="px-3 py-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg text-lg leading-none disabled:opacity-40"
            title="Patientenaktionen"
          >
            ⋯
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-full mt-1 w-52 bg-white border border-gray-200 rounded-xl shadow-lg z-20 py-1">
              <button
                onClick={() => handleSetAktiv(!aktiv)}
                className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
              >
                {aktiv ? "Auf inaktiv setzen" : "Auf aktiv setzen"}
              </button>
              <div className="border-t border-gray-100 my-1" />
              <button
                onClick={() => { setMenuOpen(false); setConfirmDelete(true); }}
                className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50"
              >
                Patient löschen
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "chat" && <PatientChatPanel patientId={id!} />}
        {activeTab === "meilenstein" && <MeilensteinPanel patientId={id!} />}
        {activeTab === "brief" && <BriefPanel patientId={id!} />}
      </div>

      {/* Delete confirm modal */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4 p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-2">Patient löschen?</h2>
            <p className="text-sm text-gray-600 mb-6">
              Diese Aktion ist nicht umkehrbar. Patient, Meilenstein und Uploads werden gelöscht.
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setConfirmDelete(false)}
                disabled={actionBusy}
                className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg disabled:opacity-50"
              >
                Abbrechen
              </button>
              <button
                onClick={handleDelete}
                disabled={actionBusy}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50"
              >
                {actionBusy ? "Löschen…" : "Löschen"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
