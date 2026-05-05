"""Tests für B2: last_meilenstein-Persistierung + learn-from-edits-Endpoint."""
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
    """Inhalt unverändert → leere candidates-Liste, kein LLM-Call."""
    text = "=== Patientenübersicht ===\n\n== Befunde ==\n- TTE: LVEF 30%"
    learning_storage.save_last_meilenstein("P-0001", text)

    res = client.post("/api/meilenstein/learn-from-edits", json={
        "patient_id": "P-0001",
        "edited_meilenstein": text,
    })
    assert res.status_code == 200
    assert res.json()["candidates"] == []


def test_learn_from_edits_returns_candidates_with_conflict_field(isolated_data):
    """Inhaltsänderung → Kandidaten werden zurückgegeben inkl. has_conflict-Feld."""
    learning_storage.save_last_meilenstein("P-0001", _MOCK_CONTENT)

    from agent_meilenstein_learning import ConflictResult, ExtractionResult, RuleCandidate

    extraction = ExtractionResult(candidates=[
        RuleCandidate(section="Befunde", rule_text="Immer LVEF im Echo nennen"),
    ])
    conflict = ConflictResult(has_conflict=False, explanation="")

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
    assert len(body["candidates"]) == 1
    c = body["candidates"][0]
    assert c["section"] == "Befunde"
    assert c["rule_text"] == "Immer LVEF im Echo nennen"
    assert c["has_conflict"] is False
    assert "conflict_explanation" in c


# ── Prompt Smoke Tests ────────────────────────────────────────────────────────

_EXTRACTION_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "learning_rule_extraction.txt"
_CONFLICT_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "learning_conflict_detection.txt"


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
