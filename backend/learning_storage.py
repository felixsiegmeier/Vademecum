"""Lernlog-Storage — Multi-Domain (domain, section?)-Adressierung.

Layout:
  data/learnings/<user_id>/
    meilenstein/
      rules.yml
      last/<pid>.txt
    brief/
      {diagnosen,anamnese,therapie,verlauf}/
        rules.yml
        last/<pid>.txt
"""

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

PATIENT_SCHEMA_VERSION = "0.4"
SCHEMA_VERSION = "0.1"

LEARNINGS_DIR = Path(__file__).parent / "data" / "learnings"

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

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _generate_ulid() -> str:
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    randomness = int.from_bytes(os.urandom(10), "big")
    n = (timestamp_ms << 80) | randomness
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[n & 0x1F])
        n >>= 5
    return "".join(reversed(chars))


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
        id=_generate_ulid(),
        section=section,
        rule_text=rule_text,
        created_at=datetime.now(timezone.utc).isoformat(),
        patient_schema_version_at_creation=PATIENT_SCHEMA_VERSION,
    )


def _rules_path(user_id: str, domain: str, section: Optional[str] = None) -> Path:
    if section:
        path = LEARNINGS_DIR / user_id / domain / section / "rules.yml"
    else:
        path = LEARNINGS_DIR / user_id / domain / "rules.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _last_path(user_id: str, domain: str, section: Optional[str], patient_id: str) -> Path:
    if section:
        path = LEARNINGS_DIR / user_id / domain / section / "last" / f"{patient_id}.txt"
    else:
        path = LEARNINGS_DIR / user_id / domain / "last" / f"{patient_id}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_rules(
    user_id: str = "default",
    domain: str = "meilenstein",
    section: Optional[str] = None,
) -> list[Rule]:
    """Lädt Regeln. Nicht-existente Datei → leere Liste."""
    path = _rules_path(user_id, domain, section)
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
    path = _rules_path(user_id, domain, section)
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
    """Speichert den zuletzt generierten Output atomar."""
    path = _last_path(user_id, domain, section, patient_id)
    tmp = path.with_suffix(".txt.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


def load_last_output(
    patient_id: str,
    user_id: str = "default",
    domain: str = "meilenstein",
    section: Optional[str] = None,
) -> Optional[str]:
    """Lädt den zuletzt generierten Output. None wenn nicht vorhanden."""
    path = _last_path(user_id, domain, section, patient_id)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")
