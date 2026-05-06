"""Brief-Storage — verwaltet den generierten Arztbrief pro Patient.

Persistiert als YAML unter data/briefs/<patient_id>.yml.
Schemaversion "0.1": 5 Markdown-Sektionen + Metadaten.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

BRIEFS_DIR = Path(__file__).parent / "data" / "briefs"

BRIEF_SECTIONS = {"diagnosen", "anamnese", "therapie", "befunde", "verlauf"}

_SCHEMA_VERSION = "0.1"


def _brief_path(patient_id: str) -> Path:
    return BRIEFS_DIR / f"{patient_id}.yml"


def _empty_brief(patient_id: str) -> dict:
    return {
        "schema_version": _SCHEMA_VERSION,
        "patient_id": patient_id,
        "diagnosen": "",
        "anamnese": "",
        "therapie": "",
        "befunde": "",
        "verlauf": "",
        "updated_at": "",
    }


def load_brief(patient_id: str) -> dict:
    """Lädt Brief. Nicht-existente Datei → leeres Skelett (ohne Datei anzulegen)."""
    path = _brief_path(patient_id)
    if not path.exists():
        return _empty_brief(patient_id)
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    for section in BRIEF_SECTIONS:
        if section not in data:
            data[section] = ""
    return data


def save_brief(patient_id: str, brief: dict) -> None:
    """Speichert Brief atomar (temp-Datei + os.replace)."""
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    path = _brief_path(patient_id)
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "patient_id": patient_id,
        "diagnosen": brief.get("diagnosen", ""),
        "anamnese": brief.get("anamnese", ""),
        "therapie": brief.get("therapie", ""),
        "befunde": brief.get("befunde", ""),
        "verlauf": brief.get("verlauf", ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = path.with_suffix(".yml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    os.replace(tmp, path)


def delete_brief(patient_id: str) -> bool:
    """Löscht Brief-Datei. Gibt True zurück wenn vorhanden, False wenn nicht."""
    path = _brief_path(patient_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def update_section(patient_id: str, section: str, content: str) -> dict:
    """Lädt, patcht eine Sektion, speichert, gibt neuen State zurück."""
    if section not in BRIEF_SECTIONS:
        raise ValueError(
            f"Unbekannte Sektion '{section}'. Erlaubt: {sorted(BRIEF_SECTIONS)}"
        )
    brief = load_brief(patient_id)
    brief[section] = content
    save_brief(patient_id, brief)
    return load_brief(patient_id)
