"""Tests für B2+B3: last_meilenstein-Persistierung, learn-from-edits, save-rules, rebuild-rule."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import storage
import learning_storage
import main as _main
import agent_meilenstein_learning as _la
from main import app
from fastapi.testclient import TestClient
from models.patient import Patient, Stammdaten

client = TestClient(app)


# ── Storage: last_meilenstein ─────────────────────────────────────────────────

def test_last_meilenstein_roundtrip(isolated_data):
    """save_last_meilenstein → load_last_meilenstein gibt gleichen Text zurück."""
    text = "=== Patientenübersicht ===\n\n== Befunde ==\n- TTE: LVEF 30%"
    learning_storage.save_last_meilenstein("P-0001", text)
    loaded = learning_storage.load_last_meilenstein("P-0001")
    assert loaded == text


def test_load_last_meilenstein_returns_none_when_missing(isolated_data):
    """Datei nicht vorhanden → None, kein Fehler."""
    result = learning_storage.load_last_meilenstein("P-9999")
    assert result is None


# ── Endpoint: generate persistiert last_meilenstein ──────────────────────────

def _make_patient_minimal(pid: str = "P-0001") -> Patient:
    p = Patient(
        stammdaten=Stammdaten(id=pid, name="Test, Patient", aufnahmedatum="2026-04-01"),
    )
    storage.save_patient(p)
    return p


def _llm_resp(text: str):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    return resp


_MOCK_CONTENT = "=== Patientenübersicht ===\n\n== Befunde ==\n- TTE: LVEF 30%"
_MOCK_LLM_OUT = f"```plain text\n{_MOCK_CONTENT}\n```"


def test_generate_meilenstein_persists_last_meilenstein(isolated_data):
    """Nach POST generate ist load_last_meilenstein nicht None und enthält den generierten Text."""
    _make_patient_minimal("P-0001")

    with patch.object(_main.llm, "chat_completion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _llm_resp(_MOCK_LLM_OUT)
        res = client.post("/api/patients/P-0001/meilenstein/generate", json={})

    assert res.status_code == 200
    saved = learning_storage.load_last_meilenstein("P-0001")
    assert saved is not None
    assert "Patientenübersicht" in saved


# ── Endpoint: learn-from-edits ────────────────────────────────────────────────

def test_learn_from_edits_404_when_no_reference(isolated_data):
    """POST learn-from-edits ohne vorherigen generate → 404."""
    _make_patient_minimal("P-0001")
    res = client.post("/api/meilenstein/learn-from-edits", json={
        "patient_id": "P-0001",
        "edited_meilenstein": "irgendwas",
    })
    assert res.status_code == 404


def test_learn_from_edits_empty_when_unchanged(isolated_data):
    """Inhalt unverändert → leere rule_candidates + trivial_changes, kein LLM-Call."""
    text = "=== Patientenübersicht ===\n\n== Befunde ==\n- TTE: LVEF 30%"
    learning_storage.save_last_meilenstein("P-0001", text)

    res = client.post("/api/meilenstein/learn-from-edits", json={
        "patient_id": "P-0001",
        "edited_meilenstein": text,
    })
    assert res.status_code == 200
    body = res.json()
    assert body["rule_candidates"] == []
    assert body["trivial_changes"] == []


def test_learn_from_edits_returns_candidates_with_conflict_field(isolated_data):
    """Inhaltsänderung → Kandidaten mit conflict-Feld (None wenn kein Konflikt)."""
    learning_storage.save_last_meilenstein("P-0001", _MOCK_CONTENT)

    from agent_meilenstein_learning import ConflictResult, ExtractionResult, RuleCandidate, TrivialChange

    extraction = ExtractionResult(
        candidates=[
            RuleCandidate(
                section="Befunde",
                rule_text="Immer LVEF im Echo nennen",
                reasoning="Arzt hat LVEF ergänzt",
                anchor="TTE: LVEF 30%",
            )
        ],
        trivial_changes=[TrivialChange(description="Tippfehler korrigiert", anchor="LVEF 30%")],
    )
    conflict = ConflictResult(has_conflict=False, explanation="", conflicting_rule_id="")

    with (
        patch.object(_la, "extract_rule_candidates", new_callable=AsyncMock) as mock_extract,
        patch.object(_la, "detect_conflict", new_callable=AsyncMock) as mock_conflict,
    ):
        mock_extract.return_value = extraction
        mock_conflict.return_value = conflict

        res = client.post("/api/meilenstein/learn-from-edits", json={
            "patient_id": "P-0001",
            "edited_meilenstein": _MOCK_CONTENT + "\n- EKG: SR",
        })

    assert res.status_code == 200
    body = res.json()

    assert len(body["rule_candidates"]) == 1
    c = body["rule_candidates"][0]
    assert c["section"] == "Befunde"
    assert c["rule_text"] == "Immer LVEF im Echo nennen"
    assert c["reasoning"] == "Arzt hat LVEF ergänzt"
    assert c["anchor"] == "TTE: LVEF 30%"
    assert c["conflict"] is None

    assert len(body["trivial_changes"]) == 1
    tc = body["trivial_changes"][0]
    assert tc["description"] == "Tippfehler korrigiert"


# ── Endpoint: save-rules ─────────────────────────────────────────────────────

def test_save_rules_endpoint_adds_rules(isolated_data):
    """POST save-rules fügt neue Regeln hinzu."""
    res = client.post("/api/meilenstein/save-rules", json={
        "rules_to_add": [
            {"section": "Befunde", "rule_text": "Immer LVEF im Echo nennen"},
            {"section": "Behandlungsdiagnosen", "rule_text": "KHK mit DES-Vorgeschichte konsolidieren"},
        ],
        "rule_ids_to_delete": [],
    })
    assert res.status_code == 200
    body = res.json()
    assert body["saved_count"] == 2
    assert body["deleted_count"] == 0
    assert body["total_rules"] == 2

    stored = learning_storage.load_rules()
    assert len(stored) == 2


def test_save_rules_endpoint_deletes_then_adds(isolated_data):
    """POST save-rules löscht alte Regel und fügt neue hinzu (Konflikt-Ersetzen-Pfad)."""
    # Erstmal eine Regel speichern
    rule = learning_storage.new_rule("Befunde", "Alte Regel")
    learning_storage.save_rules([rule])

    res = client.post("/api/meilenstein/save-rules", json={
        "rules_to_add": [
            {"section": "Befunde", "rule_text": "Neue bessere Regel"},
        ],
        "rule_ids_to_delete": [rule.id],
    })
    assert res.status_code == 200
    body = res.json()
    assert body["saved_count"] == 1
    assert body["deleted_count"] == 1
    assert body["total_rules"] == 1

    stored = learning_storage.load_rules()
    assert stored[0].rule_text == "Neue bessere Regel"


def test_save_rules_endpoint_rejects_invalid_section(isolated_data):
    """POST save-rules mit ungültiger Sektion → 422."""
    res = client.post("/api/meilenstein/save-rules", json={
        "rules_to_add": [
            {"section": "UNGÜLTIG", "rule_text": "Eine Regel"},
        ],
        "rule_ids_to_delete": [],
    })
    assert res.status_code == 422


# ── Endpoint: rebuild-rule ────────────────────────────────────────────────────

def test_rebuild_rule_endpoint_returns_refined(isolated_data):
    """POST rebuild-rule liefert verfeinerten rule_text und reasoning (Mock-LLM)."""
    from agent_meilenstein_learning import RebuildResult

    rebuild_result = RebuildResult(
        rule_text="KHK mit DES-Vorgeschichte und Bypass-OP konsolidieren",
        reasoning="Arzt hat klargestellt, dass auch OP-Daten gehören",
    )

    with patch.object(_la, "rebuild_rule_candidate", new_callable=AsyncMock) as mock_rebuild:
        mock_rebuild.return_value = rebuild_result
        res = client.post("/api/meilenstein/rebuild-rule", json={
            "section": "Behandlungsdiagnosen",
            "original_rule_text": "KHK mit DES-Vorgeschichte konsolidieren",
            "original_reasoning": "Arzt hat KHK ergänzt",
            "anchor": "KHK mit DES 2019",
            "clarification": "Auch Bypass-OPs sollen erwähnt werden",
        })

    assert res.status_code == 200
    body = res.json()
    assert body["section"] == "Behandlungsdiagnosen"
    assert body["rule_text"] == "KHK mit DES-Vorgeschichte und Bypass-OP konsolidieren"
    assert body["anchor"] == "KHK mit DES 2019"


# ── Endpoint: rules-list + delete-rule ───────────────────────────────────────

def test_get_rules_endpoint_returns_stored_rules(isolated_data):
    """GET /api/meilenstein/rules gibt alle gespeicherten Regeln zurück."""
    rule = learning_storage.new_rule("Befunde", "LVEF immer nennen")
    learning_storage.save_rules([rule])

    res = client.get("/api/meilenstein/rules")
    assert res.status_code == 200
    body = res.json()
    assert len(body["rules"]) == 1
    assert body["rules"][0]["rule_text"] == "LVEF immer nennen"


def test_delete_rule_endpoint_removes_rule(isolated_data):
    """DELETE /api/meilenstein/rules/{id} entfernt die Regel."""
    rule = learning_storage.new_rule("Befunde", "LVEF immer nennen")
    learning_storage.save_rules([rule])

    res = client.delete(f"/api/meilenstein/rules/{rule.id}")
    assert res.status_code == 204

    stored = learning_storage.load_rules()
    assert stored == []


def test_delete_rule_endpoint_404_for_unknown(isolated_data):
    """DELETE /api/meilenstein/rules/{id} mit unbekannter ID → 404."""
    res = client.delete("/api/meilenstein/rules/UNBEKANNT")
    assert res.status_code == 404


# ── Prompt Smoke Tests ────────────────────────────────────────────────────────

_EXTRACTION_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "learning_rule_extraction.txt"
_CONFLICT_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "learning_conflict_detection.txt"
_REBUILD_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "learning_rule_rebuild.txt"


def test_extraction_prompt_contains_anonymization_clause():
    """Extraction-Prompt enthält Anonymisierungsklausel."""
    text = _EXTRACTION_PROMPT_PATH.read_text(encoding="utf-8")
    has_clause = (
        "Anonymisierung" in text
        or "patientenspezifisch" in text
        or "Identifikator" in text
        or "Namen" in text
    )
    assert has_clause, "Extraction-Prompt muss eine Anonymisierungsklausel enthalten."


def test_extraction_prompt_contains_section_whitelist():
    """Extraction-Prompt listet alle gültigen Sektionen auf."""
    text = _EXTRACTION_PROMPT_PATH.read_text(encoding="utf-8")
    for section in learning_storage.VALID_SECTIONS:
        assert section in text, f"Sektion '{section}' fehlt im Extraction-Prompt."


def test_rebuild_prompt_contains_anonymization_clause():
    """Rebuild-Prompt enthält Anonymisierungsklausel."""
    text = _REBUILD_PROMPT_PATH.read_text(encoding="utf-8")
    has_clause = (
        "Anonymisierung" in text
        or "patientenspezifisch" in text
        or "Identifikator" in text
        or "Namen" in text
    )
    assert has_clause, "Rebuild-Prompt muss eine Anonymisierungsklausel enthalten."
