# workflows/stammdaten_extraction

Workflow: Stammdaten-Extraktion aus Upload-Dokumenten (Single-Pass, JSON-Mode).

Eingang: Dokument-Bytes (PDF).
Ausgang: `StammdatenExtractResult` (Pydantic) — befüllt `Patient.stammdaten`.

Architekturkontext: `backend/AGENTS.md`.
