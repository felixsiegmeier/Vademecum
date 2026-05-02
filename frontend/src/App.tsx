import { useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import ChatWindow from "./components/ChatWindow";
import PatientLanding from "./components/PatientLanding";
import Sidebar from "./components/Sidebar";

// AppContent ist vom Router getrennt, damit useNavigate() funktioniert
// (Router-Hooks sind nur innerhalb von <BrowserRouter> verfügbar)
function AppContent() {
  const navigate = useNavigate();
  // Zähler: Erhöhen zwingt die Sidebar zur Neu-Ladung der Patientenliste
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  function handlePatientCreated(patientId: string) {
    setRefreshTrigger((t) => t + 1);
    navigate(`/patients/${patientId}/chat`);
  }

  function handlePatientModified() {
    setRefreshTrigger((t) => t + 1);
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar refreshTrigger={refreshTrigger} onPatientCreated={handlePatientCreated} />
      <main className="flex-1 overflow-hidden">
        <Routes>
          {/* Startseite: allgemeiner Chat ohne Patient-Kontext */}
          <Route path="/" element={<ChatWindow />} />
          {/* /patients/:id ohne Sub-Route → direkt auf Chat weiterleiten */}
          <Route path="/patients/:id" element={<Navigate to="chat" replace />} />
          {/* Alle drei Tabs (chat / meilenstein / brief) landen im selben Layout-Container */}
          <Route
            path="/patients/:id/chat"
            element={<PatientLanding onModified={handlePatientModified} />}
          />
          <Route
            path="/patients/:id/meilenstein"
            element={<PatientLanding onModified={handlePatientModified} />}
          />
          <Route
            path="/patients/:id/brief"
            element={<PatientLanding onModified={handlePatientModified} />}
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}
