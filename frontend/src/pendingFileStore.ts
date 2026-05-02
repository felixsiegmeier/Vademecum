// Kurzlebiger Modul-State: überbrückt die Navigationsgrenze zwischen
// NewPatientDialog (setzt Datei) und PatientChatPanel (konsumiert sie einmalig).
// File ist nicht JSON-serialisierbar, daher kein Routing-State.

let _pending: File | null = null;

export function setPendingFile(file: File): void {
  _pending = file;
}

export function takePendingFile(): File | null {
  const file = _pending;
  _pending = null;
  return file;
}
