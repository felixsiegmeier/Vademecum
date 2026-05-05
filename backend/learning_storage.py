"""Lernlog-Storage für Meilenstein-Regeln.

Schreibt/liest strukturierte Regel-Listen als YAML unter
data/learnings/<user_id>/meilenstein.yml.

B1 (dieser Stand): Lese-Pfad.
B2 (geplant): Schreib-API-Endpoint.
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

# Aktuelles Patient-Schema — muss synchron mit storage.save_patient bleiben.
# Beim Schema-Bump: diese Konstante erhöhen.
PATIENT_SCHEMA_VERSION = "0.4"

# Lernlog-Datei-Schemaversion (unabhängig vom Patient-Schema).
SCHEMA_VERSION = "0.1"

LEARNINGS_DIR = Path(__file__).parent / "data" / "learnings"

VALID_SECTIONS = [
    "Operationen & Prozeduren",
    "Behandlungsdiagnosen",
    "Relevante Nebendiagnosen",
    "Kardiale Funktion",
    "Antikoagulation",
    "Antimikrobielle Therapie",
    "Befunde",
    "Therapieziel / Patientenwille",
]

# Crockford-Base32 ULID (analog agent_tools.py)
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
    section: str
    rule_text: str
    created_at: str
    patient_schema_version_at_creation: str

    @field_validator("section")
    @classmethod
    def section_must_be_valid(cls, v: str) -> str:
        if v not in VALID_SECTIONS:
            raise ValueError(f"Ungültige Sektion: '{v}'. Erlaubt: {VALID_SECTIONS}")
        return v

    @field_validator("rule_text")
    @classmethod
    def rule_text_must_be_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rule_text darf nicht leer sein.")
        return v


def new_rule(section: str, rule_text: str) -> Rule:
    """Erzeugt eine neue Rule mit frischer ID + Timestamps."""
    return Rule(
        id=_generate_ulid(),
        section=section,
        rule_text=rule_text,
        created_at=datetime.now(timezone.utc).isoformat(),
        patient_schema_version_at_creation=PATIENT_SCHEMA_VERSION,
    )


def _storage_path(user_id: str) -> Path:
    path = LEARNINGS_DIR / user_id / "meilenstein.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_rules(user_id: str = "default") -> list[Rule]:
    """Lädt Regeln für user_id. Nicht-existente Datei → leere Liste.

    Warnt bei Schema-Versionsmismatch, lädt trotzdem weiter.
    """
    path = _storage_path(user_id)
    if not path.exists():
        return []

    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    file_schema = data.get("schema_version", "")
    if file_schema != SCHEMA_VERSION:
        logger.warning(
            "learning_storage: schema_version '%s' != erwartet '%s' — "
            "Forward-Compat-Modus, lade weiter.",
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
                "learning_storage: Regel '%s' wurde bei patient_schema_version '%s' erstellt, "
                "aktuell ist '%s' — möglicherweise veraltet.",
                rule.id,
                rule.patient_schema_version_at_creation,
                PATIENT_SCHEMA_VERSION,
            )
        rules.append(rule)

    return rules


def save_rules(rules: list[Rule], user_id: str = "default") -> None:
    """Schreibt Regeln atomar (tempfile + os.replace)."""
    path = _storage_path(user_id)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "rules": [r.model_dump() for r in rules],
    }
    tmp = path.with_suffix(".yml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    os.replace(tmp, path)
