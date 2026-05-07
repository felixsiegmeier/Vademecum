import hashlib
import json
import os
import re
from pathlib import Path

import yaml

from models.patient import Patient

# Alle Patientendaten liegen als plain-text Dateien im data/-Verzeichnis.
# Kein Datenbankserver nötig — einfaches Dateisystem als Storage-Backend.
DATA_DIR = Path(__file__).parent / "data"
PATIENTS_DIR = DATA_DIR / "patienten"     # P-0001.yml, P-0002.yml, ...
MEILENSTEINE_DIR = DATA_DIR / "meilensteine"  # P-0001.md + P-0001.meta.json

# ── Patienten-Verwaltung ──────────────────────────────────────────────────────

def list_patient_ids() -> list[str]:
    """Gibt alle bekannten Patienten-IDs alphabetisch sortiert zurück."""
    return sorted(p.stem for p in PATIENTS_DIR.glob("*.yml"))


def next_patient_id() -> str:
    """Generiert die nächste freie ID im Format P-NNNN (lückenlos aufsteigend)."""
    ids = []
    for p in PATIENTS_DIR.glob("P-*.yml"):
        m = re.match(r"P-(\d{4})", p.stem)
        if m:
            ids.append(int(m.group(1)))
    n = max(ids) + 1 if ids else 1
    return f"P-{n:04d}"


def load_patient(patient_id: str) -> Patient:
    """Liest die YAML-Datei und validiert sie gegen das Pydantic-Modell."""
    path = PATIENTS_DIR / f"{patient_id}.yml"
    if not path.exists():
        raise FileNotFoundError(f"Patient {patient_id} not found")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Patient.model_validate(data)


def save_patient(patient: Patient) -> None:
    """Schreibt den Patient atomar in data/patients/{patient_id}.yml.

    Atomar via tmp-Datei + os.replace, damit bei Absturz keine korrupte Datei entsteht.
    """
    path = PATIENTS_DIR / f"{patient.stammdaten.id}.yml"
    tmp = path.with_suffix(".yml.tmp")
    payload = patient.model_dump(exclude_none=True, mode="json")
    full_payload = {"schema_version": "0.4", **payload}
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            full_payload,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=100,
        )
    os.replace(tmp, path)


def delete_patient(patient_id: str) -> None:
    """Löscht YAML, Meilenstein-, Brief- und Chat-Dateien eines Patienten."""
    yaml_path = PATIENTS_DIR / f"{patient_id}.yml"
    if yaml_path.exists():
        yaml_path.unlink()
    import brief_storage as _brief_storage
    _brief_storage.delete_brief(patient_id)
    delete_meilenstein(patient_id)
    from chat_storage import delete_chat
    delete_chat(patient_id)

# ── Staleness-Erkennung ───────────────────────────────────────────────────────
# Wir erkennen veraltete Generierungen durch Vergleich von SHA-256-Hashes.
# Ändert sich das YAML, weicht der gespeicherte Hash vom aktuellen ab → is_stale = True.

def patient_yaml_hash(patient_id: str) -> str:
    """SHA-256 des rohen YAML-Inhalts — für Meilenstein-Staleness."""
    path = PATIENTS_DIR / f"{patient_id}.yml"
    if not path.exists():
        raise FileNotFoundError(f"Patient {patient_id} not found")
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()


# ── Meilenstein-IO ────────────────────────────────────────────────────────────
# Meilenstein = zwei Dateien: .md (Inhalt) + .meta.json (Zeitstempel + Hash)

def load_meilenstein(patient_id: str) -> tuple[str, dict] | None:
    """Gibt (md_content, meta_dict) zurück oder None wenn nicht vorhanden."""
    md_path = MEILENSTEINE_DIR / f"{patient_id}.md"
    meta_path = MEILENSTEINE_DIR / f"{patient_id}.meta.json"
    if not md_path.exists():
        return None
    md_content = md_path.read_text(encoding="utf-8")
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return md_content, meta


def save_meilenstein(patient_id: str, md_content: str, meta: dict) -> None:
    """Schreibt MD + meta. Nicht atomar — beide Schreibvorgänge hintereinander."""
    MEILENSTEINE_DIR.mkdir(parents=True, exist_ok=True)
    md_path = MEILENSTEINE_DIR / f"{patient_id}.md"
    meta_path = MEILENSTEINE_DIR / f"{patient_id}.meta.json"
    md_path.write_text(md_content, encoding="utf-8")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def update_meilenstein_content(patient_id: str, md_content: str) -> None:
    """Überschreibt nur den MD-Inhalt — meta (Hash/Zeitstempel) bleibt unverändert.

    Wird beim manuellen Bearbeiten durch den Arzt aufgerufen (Autosave).
    Der Hash bleibt bewusst alt, damit is_stale weiterhin korrekt ist.
    """
    MEILENSTEINE_DIR.mkdir(parents=True, exist_ok=True)
    md_path = MEILENSTEINE_DIR / f"{patient_id}.md"
    md_path.write_text(md_content, encoding="utf-8")

def delete_meilenstein(patient_id: str) -> None:
    """Löscht die Meilenstein-Dateien eines Patienten."""
    md_path = MEILENSTEINE_DIR / f"{patient_id}.md"
    if md_path.exists():
        md_path.unlink()
    meta_path = MEILENSTEINE_DIR / f"{patient_id}.meta.json"
    if meta_path.exists():
        meta_path.unlink()

