"""Tests für backend/learning_storage.py (B1: Lese-Pfad)."""
import logging

import pytest

import learning_storage
from learning_storage import Rule, load_rules, new_rule, save_rules


def _make_rule(section: str = "Behandlungsdiagnosen", rule_text: str = "KHK immer konsolidieren") -> Rule:
    return new_rule(section=section, rule_text=rule_text)


# ── 1. Leere Liste wenn Datei nicht existiert ─────────────────────────────────

def test_load_rules_empty_returns_empty_list(isolated_data):
    """Datei existiert nicht → leere Liste, kein Fehler."""
    result = load_rules(user_id="default")
    assert result == []


# ── 2. Roundtrip: schreiben + lesen = gleich ─────────────────────────────────

def test_save_and_load_rules_roundtrip(isolated_data):
    """Drei Rules schreiben und unverändert zurücklesen."""
    rules = [
        _make_rule("Behandlungsdiagnosen", "KHK mit DES-Vorgeschichte konsolidieren"),
        _make_rule("Antikoagulation", "Bei bMKE biologisch alle Layer nennen"),
        _make_rule("Befunde", "Nur TTE/TEE, keine Routine-Labore"),
    ]
    save_rules(rules, user_id="default")
    loaded = load_rules(user_id="default")

    assert len(loaded) == 3
    for orig, back in zip(rules, loaded):
        assert orig.id == back.id
        assert orig.section == back.section
        assert orig.rule_text == back.rule_text
        assert orig.created_at == back.created_at
        assert orig.patient_schema_version_at_creation == back.patient_schema_version_at_creation


# ── 5. Schema-Drift-Warnung ───────────────────────────────────────────────────

def test_load_rules_logs_warning_on_schema_drift(isolated_data, caplog):
    """Rule mit veralteter patient_schema_version_at_creation → Warning, Rule trotzdem geladen."""
    # Regel mit veralteter Schema-Version direkt als Dict speichern
    import yaml, os
    path = learning_storage._storage_path("default")
    payload = {
        "schema_version": learning_storage.SCHEMA_VERSION,
        "rules": [
            {
                "id": "01AAAABBBBCCCCDDDDEEEE00",
                "section": "Befunde",
                "rule_text": "Nur Echo-Befunde",
                "created_at": "2026-01-01T00:00:00+00:00",
                "patient_schema_version_at_creation": "0.3",  # veraltet
            }
        ],
    }
    tmp = path.with_suffix(".yml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp, path)

    with caplog.at_level(logging.WARNING, logger="learning_storage"):
        rules = load_rules(user_id="default")

    # Rule trotzdem geladen
    assert len(rules) == 1
    assert rules[0].id == "01AAAABBBBCCCCDDDDEEEE00"

    # Warning wurde ausgegeben
    assert any("0.3" in record.message and "0.4" in record.message for record in caplog.records), (
        f"Erwartet Warning mit '0.3' und '0.4', bekam: {[r.message for r in caplog.records]}"
    )


# ── Pydantic-Validation ───────────────────────────────────────────────────────

def test_rule_invalid_section_raises():
    """Ungültige Sektion → Pydantic-Fehler."""
    with pytest.raises(Exception, match="Ungültige Sektion"):
        Rule(
            id="X",
            section="VERLAUF",  # nicht mehr gültig
            rule_text="Test",
            created_at="2026-01-01T00:00:00+00:00",
            patient_schema_version_at_creation="0.4",
        )


def test_rule_empty_rule_text_raises():
    """Leerer rule_text → Pydantic-Fehler."""
    with pytest.raises(Exception, match="leer"):
        Rule(
            id="X",
            section="Befunde",
            rule_text="   ",
            created_at="2026-01-01T00:00:00+00:00",
            patient_schema_version_at_creation="0.4",
        )
