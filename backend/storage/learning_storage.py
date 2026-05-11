"""Lernlog-Storage — zwei getrennte Datenschichten.

Regelmengen (user-spezifisch):
  data/lernlog/<domain>/<section>/<user_id>.yml
  data/lernlog/<domain>/<user_id>.yml          (falls section=None)

Patient-Snapshots (nicht user-spezifisch):
  data/learning_snapshots/<domain>/<pid>.yml
    Brief:       {diagnosen: "...", anamnese: "...", therapie: "...", verlauf: "..."}
    Meilenstein: {content: "..."}
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, field_validator

from paths import BACKEND_DIR, USER_DATA_DIR
from utils.ulid import generate_ulid

logger = logging.getLogger(__name__)

PATIENT_SCHEMA_VERSION = "0.4"
SCHEMA_VERSION = "0.1"

# Regelmengen liegen als gitignorierte default.yml in den jeweiligen Section-lernlog/-Ordnern.
LERNLOG_BASE = BACKEND_DIR / "workflows"
SNAPSHOTS_DIR = USER_DATA_DIR / "learning_snapshots"

# Meilenstein-Sektionen — für Regel-Grouping im System-Prompt-Builder.
MEILENSTEIN_SECTIONS = [
    "Operationen & Prozeduren",
    "Behandlungsdiagnosen",
    "Relevante Nebendiagnosen",
    "Kardiale Funktion",
    "Antikoagulation",
    "Antimikrobielle Therapie",
    "Befunde",
    "Therapieziel / Patientenwille",
]

# Brief-Sektionen mit Lernlog (befunde explizit ausgeschlossen).
BRIEF_SECTIONS_WITH_LEARNING = {"diagnosen", "anamnese", "therapie", "verlauf"}

class Rule(BaseModel):
    id: str
    section: str  # free-form label; für meilenstein: einer der MEILENSTEIN_SECTIONS
    rule_text: str
    created_at: str
    patient_schema_version_at_creation: str

    @field_validator("rule_text")
    @classmethod
    def rule_text_must_be_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rule_text darf nicht leer sein.")
        return v


def new_rule(section: str, rule_text: str) -> Rule:
    return Rule(
        id=generate_ulid(),
        section=section,
        rule_text=rule_text,
        created_at=datetime.now(timezone.utc).isoformat(),
        patient_schema_version_at_creation=PATIENT_SCHEMA_VERSION,
    )


def _rules_path(domain: str, section: Optional[str], user_id: str = "default") -> Path:
    if section:
        path = LERNLOG_BASE / domain / section / "lernlog" / f"{user_id}.yml"
    else:
        path = LERNLOG_BASE / domain / "lernlog" / f"{user_id}.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _snapshot_path(domain: str, patient_id: str) -> Path:
    path = SNAPSHOTS_DIR / domain / f"{patient_id}.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_rules(
    user_id: str = "default",
    domain: str = "meilenstein",
    section: Optional[str] = None,
) -> list[Rule]:
    """Lädt Regeln. Nicht-existente Datei → leere Liste."""
    path = _rules_path(domain, section, user_id)
    if not path.exists():
        return []

    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    file_schema = data.get("schema_version", "")
    if file_schema != SCHEMA_VERSION:
        logger.warning(
            "learning_storage: schema_version '%s' != erwartet '%s' — Forward-Compat-Modus.",
            file_schema,
            SCHEMA_VERSION,
        )

    rules: list[Rule] = []
    for raw in data.get("rules", []):
        try:
            rule = Rule.model_validate(raw)
        except Exception as exc:
            logger.warning("learning_storage: Überspringe ungültige Regel %s: %s", raw, exc)
            continue
        if rule.patient_schema_version_at_creation != PATIENT_SCHEMA_VERSION:
            logger.warning(
                "learning_storage: Regel '%s' bei patient_schema_version '%s' erstellt, "
                "aktuell '%s' — möglicherweise veraltet.",
                rule.id,
                rule.patient_schema_version_at_creation,
                PATIENT_SCHEMA_VERSION,
            )
        rules.append(rule)

    return rules


def save_rules(
    rules: list[Rule],
    user_id: str = "default",
    domain: str = "meilenstein",
    section: Optional[str] = None,
) -> None:
    """Schreibt Regeln atomar (tempfile + os.replace)."""
    path = _rules_path(domain, section, user_id)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "rules": [r.model_dump() for r in rules],
    }
    tmp = path.with_suffix(".yml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    os.replace(tmp, path)


def save_last_output(
    patient_id: str,
    content: str,
    user_id: str = "default",
    domain: str = "meilenstein",
    section: Optional[str] = None,
) -> None:
    """Speichert den zuletzt generierten Output atomar als YAML-Snapshot.

    Alle Sektionen eines Patienten landen in einer einzigen .yml-Datei:
      {diagnosen: "...", anamnese: "...", ...}  (brief)
      {content: "..."}                           (meilenstein)
    """
    path = _snapshot_path(domain, patient_id)
    data: dict = {}
    if path.exists():
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    key = section if section else "content"
    data[key] = content
    tmp = path.with_suffix(".yml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    os.replace(tmp, path)


def load_last_output(
    patient_id: str,
    user_id: str = "default",
    domain: str = "meilenstein",
    section: Optional[str] = None,
) -> Optional[str]:
    """Lädt den zuletzt generierten Output. None wenn nicht vorhanden."""
    path = _snapshot_path(domain, patient_id)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    key = section if section else "content"
    val = data.get(key)
    return val if val else None
