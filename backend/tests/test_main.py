"""Smoke-Tests für die wichtigsten REST-Endpoints (GET /patients/{id}, apply-proposals)."""
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import storage
from agent_stammdaten_extraction import StammdatenExtractResult
from main import app
from models.patient import Patient, Stammdaten


client = TestClient(app)


# ── GET /api/patients/{id} ────────────────────────────────────────────────────


def _make_patient(pid: str = "P-0001") -> Patient:
    p = Patient(
        stammdaten=Stammdaten(id=pid, name="Test, Patient", aufnahmedatum="2026-04-01"),
        anamnese="Vorgeschichte X",
    )
    storage.save_patient(p)
    return p


def test_get_patient_returns_full_payload(isolated_data):
    _make_patient("P-0001")
    res = client.get("/api/patients/P-0001")
    assert res.status_code == 200
    body = res.json()
    assert body["stammdaten"]["id"] == "P-0001"
    assert body["stammdaten"]["name"] == "Test, Patient"
    assert body["anamnese"] == "Vorgeschichte X"
    # leere Listen müssen als [] mitkommen, damit das FE sie ohne Sonderfall verarbeiten kann
    assert body["behandlungsdiagnosen"] == []
    assert body["verlaufseintraege"] == []


def test_get_patient_unknown_returns_404(isolated_data):
    res = client.get("/api/patients/P-9999")
    assert res.status_code == 404


# ── apply-proposals: Reihenfolge bei type="update" ────────────────────────────


def _add_via_endpoint(pid: str, tool: str, args: dict) -> dict:
    proposal = {"type": "add", "call": {"tool": tool, "args": args}, "delete_call": None, "add_call": None}
    res = client.post(f"/api/patients/{pid}/apply-proposals", json={"proposals": [proposal]})
    assert res.status_code == 200, res.text
    return res.json()["results"][0]


def test_apply_update_runs_add_before_delete(isolated_data):
    """Add muss VOR delete laufen — nach Apply existieren beide IDs nie gleichzeitig komplett verloren."""
    _make_patient("P-0001")
    seed = _add_via_endpoint(
        "P-0001",
        "add_verlaufsdiagnose",
        {"text": "COPD", "datum": "2026-04-01", "source_quote": "q"},
    )
    old_id = seed["id"]

    update_proposal = {
        "type": "update",
        "call": None,
        "delete_call": {"tool": "delete_entry", "args": {"id": old_id, "source_quote": "korrektur"}},
        "add_call": {
            "tool": "add_verlaufsdiagnose",
            "args": {"text": "COPD GOLD 3", "datum": "2026-04-01", "source_quote": "korrektur"},
        },
    }
    res = client.post("/api/patients/P-0001/apply-proposals", json={"proposals": [update_proposal]})
    assert res.status_code == 200
    result = res.json()["results"][0]
    assert result["ok"] is True
    new_id = result["id"]
    assert new_id != old_id

    p = storage.load_patient("P-0001")
    ids = [d.id for d in p.verlaufsdiagnosen]
    assert old_id not in ids
    assert new_id in ids


def test_apply_update_skips_delete_when_add_fails(isolated_data):
    """add fail → delete läuft nicht → altes Item bleibt erhalten (kein Datenverlust)."""
    _make_patient("P-0001")
    seed = _add_via_endpoint(
        "P-0001",
        "add_verlaufsdiagnose",
        {"text": "COPD", "datum": "2026-04-01", "source_quote": "q"},
    )
    old_id = seed["id"]

    # add_call mit ungültigem Datum → add scheitert
    update_proposal = {
        "type": "update",
        "call": None,
        "delete_call": {"tool": "delete_entry", "args": {"id": old_id, "source_quote": "korrektur"}},
        "add_call": {
            "tool": "add_verlaufsdiagnose",
            "args": {"text": "Neu", "datum": "kein-datum", "source_quote": "korrektur"},
        },
    }
    res = client.post("/api/patients/P-0001/apply-proposals", json={"proposals": [update_proposal]})
    assert res.status_code == 200
    result = res.json()["results"][0]
    assert result["ok"] is False
    assert "summary" in result

    # Original-Item muss noch da sein
    p = storage.load_patient("P-0001")
    assert any(d.id == old_id for d in p.verlaufsdiagnosen), "altes Item wurde fälschlich gelöscht"


def test_apply_update_treats_missing_id_as_success(isolated_data):
    """delete schlägt fehl, weil ID nicht (mehr) existiert → als Success werten."""
    _make_patient("P-0001")
    update_proposal = {
        "type": "update",
        "call": None,
        "delete_call": {
            "tool": "delete_entry",
            "args": {"id": "FAKE_ULID_DOES_NOT_EXIST_XX", "source_quote": "x"},
        },
        "add_call": {
            "tool": "add_verlaufsdiagnose",
            "args": {"text": "COPD GOLD 3", "datum": "2026-04-01", "source_quote": "korrektur"},
        },
    }
    res = client.post("/api/patients/P-0001/apply-proposals", json={"proposals": [update_proposal]})
    assert res.status_code == 200
    result = res.json()["results"][0]
    assert result["ok"] is True
    p = storage.load_patient("P-0001")
    assert any(d.text == "COPD GOLD 3" for d in p.verlaufsdiagnosen)


def test_apply_proposals_results_use_summary_field(isolated_data):
    """Response-Schema: jedes Result hat ok+summary (kein `error`)."""
    _make_patient("P-0001")
    res = client.post("/api/patients/P-0001/apply-proposals", json={"proposals": [
        {"type": "add", "call": {"tool": "add_vorbekannte_diagnose", "args": {"text": "T2DM", "source_quote": "q"}}, "delete_call": None, "add_call": None},
    ]})
    assert res.status_code == 200
    result = res.json()["results"][0]
    assert result["ok"] is True
    assert "summary" in result
    assert "error" not in result


# ── POST /api/extract-stammdaten ──────────────────────────────────────────────


def test_extract_stammdaten_all_fields(isolated_data):
    """Vollständiges Dokument: alle Felder werden korrekt zurückgegeben."""
    mock_result = StammdatenExtractResult(
        name="Celik, Sadik",
        geburtsdatum="1966-08-10",
        geschlecht="m",
        bettplatz="WD2I_05B",
        aufnahmedatum="2026-04-03",
        aufnahme_quelle="notfall",
    )
    with patch("main.extract_stammdaten", new=AsyncMock(return_value=mock_result)):
        res = client.post(
            "/api/extract-stammdaten",
            files={"file": ("test.pdf", b"dummy", "application/pdf")},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Celik, Sadik"
    assert body["geburtsdatum"] == "1966-08-10"
    assert body["geschlecht"] == "m"
    assert body["bettplatz"] == "WD2I_05B"
    assert body["aufnahmedatum"] == "2026-04-03"
    assert body["aufnahme_quelle"] == "notfall"


def test_extract_stammdaten_non_patient_all_null(isolated_data):
    """Kein Patientendokument: alle Felder sind null."""
    mock_result = StammdatenExtractResult()
    with patch("main.extract_stammdaten", new=AsyncMock(return_value=mock_result)):
        res = client.post(
            "/api/extract-stammdaten",
            files={"file": ("paper.pdf", b"research paper", "application/pdf")},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] is None
    assert body["geburtsdatum"] is None
    assert body["geschlecht"] is None
    assert body["bettplatz"] is None
    assert body["aufnahmedatum"] is None
    assert body["aufnahme_quelle"] is None


def test_extract_stammdaten_partial_nullable(isolated_data):
    """Teildokument: einzelne Felder null, Pydantic akzeptiert das ohne Fehler."""
    mock_result = StammdatenExtractResult(
        name="Müller, Hans",
        geburtsdatum=None,
        geschlecht="m",
        bettplatz=None,
        aufnahmedatum="2026-01-15",
        aufnahme_quelle=None,
    )
    with patch("main.extract_stammdaten", new=AsyncMock(return_value=mock_result)):
        res = client.post(
            "/api/extract-stammdaten",
            files={"file": ("scan.jpg", b"img", "image/jpeg")},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Müller, Hans"
    assert body["geburtsdatum"] is None
    assert body["geschlecht"] == "m"
    assert body["aufnahmedatum"] == "2026-01-15"
    assert body["aufnahme_quelle"] is None


def test_extract_stammdaten_bad_mime_returns_400(isolated_data):
    """Nicht unterstützter MIME-Typ: 400 ohne LLM-Call."""
    res = client.post(
        "/api/extract-stammdaten",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )
    assert res.status_code == 400
