"""Smoke-Tests für die wichtigsten REST-Endpoints (GET /patients/{id}, apply-proposals)."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

import storage
from agent_extraction_core import Proposal, ToolCallInfo
from agent_patient_chat import CHAT_2PASS_CUTOFF
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


# ── apply-proposals: Mismatch-Detection ──────────────────────────────────────


def _make_patient_with_identity(pid: str = "P-0001") -> None:
    from datetime import date as _date
    pat = Patient(
        stammdaten=Stammdaten(
            id=pid,
            name="Celik, Sadik",
            geburtsdatum=_date(1966, 8, 10),
            geschlecht="m",
            aufnahmedatum=_date(2026, 4, 3),
        ),
    )
    storage.save_patient(pat)


def _stammdaten_proposal(feld: str, wert: str) -> dict:
    return {
        "type": "update_singleton",
        "call": {"tool": "update_stammdaten", "args": {"feld": feld, "wert": wert, "source_quote": "test"}},
        "delete_call": None,
        "add_call": None,
    }


def test_mismatch_name_returns_409(isolated_data):
    """update_stammdaten feld=name mit abweichendem Wert → HTTP 409."""
    _make_patient_with_identity("P-0001")
    proposal = _stammdaten_proposal("name", "Schmidt, Erika")
    res = client.post("/api/patients/P-0001/apply-proposals", json={"proposals": [proposal]})
    assert res.status_code == 409
    body = res.json()
    assert body["mismatch_warning"] is True
    conflicts = body["conflicting_fields"]
    assert any(c["feld"] == "name" and c["current"] == "Celik, Sadik" and c["proposed"] == "Schmidt, Erika" for c in conflicts)


def test_mismatch_geburtsdatum_returns_409(isolated_data):
    """update_stammdaten feld=geburtsdatum mit abweichendem Wert → HTTP 409."""
    _make_patient_with_identity("P-0001")
    proposal = _stammdaten_proposal("geburtsdatum", "1980-03-15")
    res = client.post("/api/patients/P-0001/apply-proposals", json={"proposals": [proposal]})
    assert res.status_code == 409
    body = res.json()
    assert body["mismatch_warning"] is True
    conflicts = body["conflicting_fields"]
    assert any(c["feld"] == "geburtsdatum" and c["current"] == "1966-08-10" for c in conflicts)


def test_mismatch_geschlecht_returns_409(isolated_data):
    """update_stammdaten feld=geschlecht mit abweichendem Wert → HTTP 409."""
    _make_patient_with_identity("P-0001")
    proposal = _stammdaten_proposal("geschlecht", "w")
    res = client.post("/api/patients/P-0001/apply-proposals", json={"proposals": [proposal]})
    assert res.status_code == 409
    body = res.json()
    assert body["mismatch_warning"] is True


def test_mismatch_initial_null_no_conflict(isolated_data):
    """Kein Mismatch wenn current null — Initialwert wird ohne Friktion übernommen."""
    from models.patient import Patient, Stammdaten
    from datetime import date as _date
    # Patient ohne geburtsdatum und ohne geschlecht
    pat = Patient(
        stammdaten=Stammdaten(id="P-0001", name="Test, Patient", aufnahmedatum=_date(2026, 4, 1)),
    )
    storage.save_patient(pat)
    proposal = _stammdaten_proposal("geburtsdatum", "1980-01-01")
    res = client.post("/api/patients/P-0001/apply-proposals", json={"proposals": [proposal]})
    assert res.status_code == 200
    assert res.json()["results"][0]["ok"] is True


def test_force_override_bypasses_mismatch(isolated_data):
    """force=True überspringt den Mismatch-Check — Apply läuft durch."""
    _make_patient_with_identity("P-0001")
    proposal = _stammdaten_proposal("name", "Schmidt, Erika")
    res = client.post(
        "/api/patients/P-0001/apply-proposals",
        json={"proposals": [proposal], "force": True},
    )
    assert res.status_code == 200
    result = res.json()["results"][0]
    assert result["ok"] is True
    pat = storage.load_patient("P-0001")
    assert pat.stammdaten.name == "Schmidt, Erika"


def test_mismatch_multifield_all_conflicts_returned(isolated_data):
    """Beide Identitätsfelder kollidieren → beide in conflicting_fields."""
    _make_patient_with_identity("P-0001")
    proposals = [
        _stammdaten_proposal("name", "Schmidt, Erika"),
        _stammdaten_proposal("geburtsdatum", "1980-03-15"),
    ]
    res = client.post("/api/patients/P-0001/apply-proposals", json={"proposals": proposals})
    assert res.status_code == 409
    body = res.json()
    assert body["mismatch_warning"] is True
    felder = {c["feld"] for c in body["conflicting_fields"]}
    assert "name" in felder
    assert "geburtsdatum" in felder


def test_non_identity_stammdaten_field_no_mismatch(isolated_data):
    """update_stammdaten feld=aufnahmedatum (kein Identitätsfeld) → kein Mismatch, normaler 200."""
    _make_patient_with_identity("P-0001")
    proposal = _stammdaten_proposal("aufnahmedatum", "2026-05-01")
    res = client.post("/api/patients/P-0001/apply-proposals", json={"proposals": [proposal]})
    assert res.status_code == 200
    result = res.json()["results"][0]
    assert result["ok"] is True


# ── Chat-Endpoint: Single-Pass vs. 2-Pass-Routing (Phase 4) ──────────────────


def test_chat_short_input_uses_single_pass(isolated_data):
    """Kurzer Input (< CUTOFF) → run_single_pass_chat aufgerufen, nicht extract_proposals."""
    _make_patient("P-0001")
    short_text = "Wie ist der Status des Patienten?"
    assert len(short_text) < CHAT_2PASS_CUTOFF

    with patch("main.run_single_pass_chat", new_callable=AsyncMock) as mock_single, \
         patch("main.extract_proposals", new_callable=AsyncMock) as mock_extract:
        mock_single.return_value = ([], "Patient ist stabil laut YAML.")
        res = client.post(
            "/api/patients/P-0001/chat",
            json={"messages": [{"role": "user", "content": short_text}]},
        )

    assert res.status_code == 200
    mock_single.assert_called_once()
    mock_extract.assert_not_called()
    body = res.json()
    assert body["reply"] == "Patient ist stabil laut YAML."
    assert body["proposals"] == []


def test_chat_long_input_uses_two_pass(isolated_data):
    """Langer Input (> CUTOFF) → extract_proposals aufgerufen, nicht run_single_pass_chat."""
    _make_patient("P-0001")
    long_text = "x" * (CHAT_2PASS_CUTOFF + 1)

    with patch("main.extract_proposals", new_callable=AsyncMock) as mock_extract, \
         patch("main.run_single_pass_chat", new_callable=AsyncMock) as mock_single:
        mock_extract.return_value = []
        res = client.post(
            "/api/patients/P-0001/chat",
            json={"messages": [{"role": "user", "content": long_text}]},
        )

    assert res.status_code == 200
    mock_extract.assert_called_once()
    mock_single.assert_not_called()
    body = res.json()
    assert body["auto_skipped"] is True
    assert body["reply"] is None


def test_chat_tool_call_gives_proposals_no_reply(isolated_data):
    """LLM macht Tool-Call → proposals nicht-leer, reply=null in Response."""
    _make_patient("P-0001")
    proposal = Proposal(
        type="update_singleton",
        call=ToolCallInfo(tool="update_bettplatz", args={"bettplatz": "WD2I_07A", "source_quote": "test"}),
    )

    with patch("main.run_single_pass_chat", new_callable=AsyncMock) as mock_single:
        mock_single.return_value = ([proposal], None)
        res = client.post(
            "/api/patients/P-0001/chat",
            json={"messages": [{"role": "user", "content": "Bettplatz ist jetzt WD2I_07A"}]},
        )

    assert res.status_code == 200
    body = res.json()
    assert len(body["proposals"]) == 1
    assert body["proposals"][0]["type"] == "update_singleton"
    assert body["reply"] is None
    assert body["auto_skipped"] is False


def test_chat_text_reply_no_proposals(isolated_data):
    """LLM antwortet mit Text → proposals leer, reply enthält Antwort."""
    _make_patient("P-0001")

    with patch("main.run_single_pass_chat", new_callable=AsyncMock) as mock_single:
        mock_single.return_value = ([], "Bei HIT-Verdacht wäre Argatroban indiziert.")
        res = client.post(
            "/api/patients/P-0001/chat",
            json={"messages": [{"role": "user", "content": "Was wäre wenn wir Heparin umstellen?"}]},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["proposals"] == []
    assert body["reply"] == "Bei HIT-Verdacht wäre Argatroban indiziert."
    assert body["auto_skipped"] is False


# ── Phase-5: Neue Upload-Formate (Streaming-Endpoint) ────────────────────────


async def _streaming_done(*args, **kwargs):
    """Minimal-Mock für extract_proposals_streaming: liefert sofort done."""
    yield {"type": "done", "total_proposals": 0, "auto_skipped": True}


def _make_upload_mock():
    """MagicMock für extract_proposals_streaming mit side_effect=_streaming_done."""
    return MagicMock(side_effect=_streaming_done)


def _parse_ndjson(text: str) -> list[dict]:
    """Parst NDJSON-Response in eine Liste von Event-Dicts."""
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_upload_txt_passes_text_to_pipeline(isolated_data):
    """text/plain wird UTF-8 dekodiert und als content_type='text' an extract_proposals_streaming übergeben."""
    _make_patient("P-0001")
    payload = b"Patient Celik, aufgenommen 23.04. mit kardiogenem Schock."

    mock_ep = _make_upload_mock()
    with patch("main.extract_proposals_streaming", mock_ep):
        res = client.post(
            "/api/uploads",
            data={"patient_id": "P-0001"},
            files={"file": ("note.txt", payload, "text/plain")},
        )

    assert res.status_code == 200
    args = mock_ep.call_args.args
    kwargs = mock_ep.call_args.kwargs
    content_passed = args[2] if len(args) > 2 else kwargs.get("content")
    content_type_passed = args[3] if len(args) > 3 else kwargs.get("content_type")
    assert content_type_passed == "text"
    assert "Celik" in content_passed


def test_upload_md_accepted(isolated_data):
    """text/markdown wird wie text/plain behandelt — kein 415."""
    _make_patient("P-0001")
    payload = b"# Aufnahme\nPatient kommt mit Dyspnoe."

    mock_ep = _make_upload_mock()
    with patch("main.extract_proposals_streaming", mock_ep):
        res = client.post(
            "/api/uploads",
            data={"patient_id": "P-0001"},
            files={"file": ("note.md", payload, "text/markdown")},
        )

    assert res.status_code == 200
    content_passed = mock_ep.call_args.args[2]
    assert "Dyspnoe" in content_passed


def test_upload_csv_converts_to_markdown_table(isolated_data):
    """text/csv wird in eine Markdown-Tabelle konvertiert, bevor es die Pipeline erreicht."""
    _make_patient("P-0001")
    payload = b"datum,wert\n2026-04-23,Laktat 3.2\n2026-04-24,Laktat 1.8"

    mock_ep = _make_upload_mock()
    with patch("main.extract_proposals_streaming", mock_ep):
        res = client.post(
            "/api/uploads",
            data={"patient_id": "P-0001"},
            files={"file": ("labor.csv", payload, "text/csv")},
        )

    assert res.status_code == 200
    content_passed = mock_ep.call_args.args[2]
    assert "| datum | wert |" in content_passed
    assert "| --- | --- |" in content_passed
    assert "Laktat 3.2" in content_passed


def test_upload_xlsx_converts_to_markdown(isolated_data):
    """xlsx-Datei wird via openpyxl in Markdown-Tabellen umgewandelt."""
    import io as _io
    import openpyxl

    _make_patient("P-0001")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Labor"
    ws.append(["datum", "wert"])
    ws.append(["2026-04-23", "Laktat 3.2"])
    buf = _io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    mock_ep = _make_upload_mock()
    with patch("main.extract_proposals_streaming", mock_ep):
        res = client.post(
            "/api/uploads",
            data={"patient_id": "P-0001"},
            files={"file": ("labor.xlsx", xlsx_bytes,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

    assert res.status_code == 200
    content_passed = mock_ep.call_args.args[2]
    assert "## Labor" in content_passed
    assert "| datum | wert |" in content_passed
    assert "Laktat 3.2" in content_passed


def test_upload_unknown_mime_returns_415(isolated_data):
    """Unbekannter Content-Type → 415 ohne LLM-Call."""
    _make_patient("P-0001")

    mock_ep = _make_upload_mock()
    with patch("main.extract_proposals_streaming", mock_ep):
        res = client.post(
            "/api/uploads",
            data={"patient_id": "P-0001"},
            files={"file": ("weird.bin", b"\x00\x01\x02", "application/octet-stream")},
        )

    assert res.status_code == 415
    mock_ep.assert_not_called()


def test_upload_response_is_ndjson_with_done_event(isolated_data):
    """Streaming-Response enthält valides NDJSON mit done-Event."""
    _make_patient("P-0001")
    payload = b"Befundbericht: EF 45%"

    mock_ep = _make_upload_mock()
    with patch("main.extract_proposals_streaming", mock_ep):
        res = client.post(
            "/api/uploads",
            data={"patient_id": "P-0001"},
            files={"file": ("befund.txt", payload, "text/plain")},
        )

    assert res.status_code == 200
    events = _parse_ndjson(res.text)
    assert len(events) >= 1
    done = next((e for e in events if e["type"] == "done"), None)
    assert done is not None
    assert "total_proposals" in done
    assert "auto_skipped" in done


# ── Meilenstein V1: generate endpoint ────────────────────────────────────────

import main as _main  # noqa: E402 — needed for patch.object on llm instance


def _make_patient_full(pid: str = "P-0001") -> Patient:
    """Minimal patient with operative therapy, antimicrobial therapy, a Befund, and a Verlaufseintrag."""
    import uuid
    from datetime import date as _date
    from models.patient import Befund, Diagnose, Therapie, VerlaufsEintrag

    def _id() -> str:
        return str(uuid.uuid4())

    p = Patient(
        stammdaten=Stammdaten(
            id=pid,
            name="Weber, Gertraud",
            geburtsdatum=_date(1948, 7, 22),
            geschlecht="w",
            bettplatz="ITS-1 / Bett 1",
            aufnahmedatum=_date(2026, 4, 1),
        ),
        behandlungsdiagnosen=[
            Diagnose(
                id=_id(),
                text="Postkardiotomie-Schock nach CABG 3-fach",
                datum=_date(2026, 4, 1),
                source_quote="Aufnahme",
            )
        ],
        therapien=[
            Therapie(
                id=_id(),
                kategorie="operativ",
                bezeichnung="CABG 3-fach (LIMA-LAD, Vene-RCX, Vene-RCA)",
                beginn=_date(2026, 4, 1),
                ende=_date(2026, 4, 1),
                source_quote="OP-Bericht",
            ),
            Therapie(
                id=_id(),
                kategorie="antimikrobiell",
                bezeichnung="Meropenem",
                beginn=_date(2026, 4, 3),
                ende=_date(2026, 4, 7),
                indikation="Pneumonie",
                source_quote="AB-Kurve",
            ),
        ],
        befunde=[
            Befund(
                id=_id(),
                datum=_date(2026, 4, 1),
                text="TTE postop: LVEF 20%, biventrikuläre Dysfunktion",
                source_quote="Echo",
            )
        ],
        verlaufseintraege=[
            VerlaufsEintrag(
                id=_id(),
                datum=_date(2026, 4, 1),
                text="Studienpatient ACCURATE-RCT. Postkardiotomie-Schock, LVEF 20% postop.",
                source_quote="Verlauf",
            )
        ],
    )
    storage.save_patient(p)
    return p


def _llm_resp(text: str):
    """Build a mock LLM response object."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    return resp


_SECTION_HEADERS = [
    "== Operationen & Prozeduren ==",
    "== Behandlungsdiagnosen ==",
    "== Relevante Nebendiagnosen ==",
    "== Kardiale Funktion ==",
    "== Antikoagulation ==",
    "== Antimikrobielle Therapie ==",
    "== Befunde ==",
    "== Besonderheiten ==",
    "== Therapieziel / Patientenwille ==",
]

_MOCK_MEILENSTEIN_BODY = "\n".join([
    "=== Patientenübersicht ===",
    "",
    "Patient: Weber, Gertraud, *22.07.1948, weiblich",
    "Aufnahme: 01.04.2026 | Bett: ITS-1 / Bett 1",
    "letzte Aktualisierung: 05.05.2026",
    "",
    "== Operationen & Prozeduren ==",
    "- 01.04. CABG 3-fach (LIMA-LAD, Vene-RCX, Vene-RCA)",
    "",
    "== Behandlungsdiagnosen ==",
    "- Postkardiotomie-Schock nach CABG 3-fach",
    "",
    "== Relevante Nebendiagnosen ==",
    "—",
    "",
    "== Kardiale Funktion ==",
    "- LVEF 20% postop (TTE 01.04.)",
    "",
    "== Antikoagulation ==",
    "- prophylaktisch UFH bei postop. Phase; danach ASS lebenslang (CABG)",
    "",
    "== Antimikrobielle Therapie ==",
    "- 03.04. Meropenem (Pneumonie) 07.04.",
    "",
    "== Befunde ==",
    "- 01.04. TTE postop: LVEF 20%, biventrikuläre Dysfunktion",
    "",
    "== Besonderheiten ==",
    "- Studienpatient ACCURATE-RCT",
    "",
    "== Therapieziel / Patientenwille ==",
    "—",
])

_MOCK_LLM_OUTPUT = "```plain text\n" + _MOCK_MEILENSTEIN_BODY + "\n```"


def test_meilenstein_generation_mode(isolated_data):
    """Generations-Modus: kein current_meilenstein → alle Sektion-Header present,
    antimikrobielle Therapie mit End-Datum, Besonderheiten mit Studienpatient-Marker."""
    _make_patient_full("P-0001")

    with patch.object(_main.llm, "chat_completion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _llm_resp(_MOCK_LLM_OUTPUT)
        res = client.post(
            "/api/patients/P-0001/meilenstein/generate",
            json={},
        )

    assert res.status_code == 200
    body = res.json()
    content = body["content"]

    # Outer header
    assert "=== Patientenübersicht ===" in content
    assert "Patient: Weber, Gertraud" in content
    assert "Aufnahme: 01.04.2026" in content

    # All 9 section headers
    for header in _SECTION_HEADERS:
        assert header in content, f"Sektion fehlt: {header}"

    # Operative therapy visible, not antimicrobial
    assert "CABG 3-fach" in content

    # Antimicrobial with end date
    assert "Meropenem" in content
    assert "07.04." in content

    # Besonderheiten preserves Studienpatient marker
    assert "Studienpatient ACCURATE-RCT" in content

    # Code block markers stripped from content
    assert "```" not in content

    # LLM called without aktueller_meilenstein block (Generations-Modus)
    call_args = mock_llm.call_args
    user_msg = call_args.args[0][-1]["content"]
    assert "<patient_yaml>" in user_msg
    assert "<generierungsdatum>" in user_msg
    assert "<aktueller_meilenstein>" not in user_msg


def test_meilenstein_konsolidierung_mode(isolated_data):
    """Konsolidierungs-Modus: current_meilenstein mitgesendet → LLM erhält
    <aktueller_meilenstein>-Block mit dem übergebenen Inhalt."""
    _make_patient_full("P-0001")

    existing = (
        "=== Patientenübersicht ===\n\n"
        "Patient: Weber, Gertraud, *22.07.1948, weiblich\n\n"
        "== Besonderheiten ==\n"
        "- Sprachbarriere türkisch\n"
        "- Veraltete Therapie: Unacid (längst beendet)\n"
    )

    mock_output = "```plain text\n" + _MOCK_MEILENSTEIN_BODY + "\n- Sprachbarriere türkisch\n```"

    with patch.object(_main.llm, "chat_completion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _llm_resp(mock_output)
        res = client.post(
            "/api/patients/P-0001/meilenstein/generate",
            json={"current_meilenstein": existing},
        )

    assert res.status_code == 200

    # LLM received <aktueller_meilenstein> block containing our existing content
    call_args = mock_llm.call_args
    user_msg = call_args.args[0][-1]["content"]
    assert "<aktueller_meilenstein>" in user_msg
    assert "Sprachbarriere türkisch" in user_msg
    assert "Veraltete Therapie" in user_msg

    # Response contains the content (code block stripped)
    content = res.json()["content"]
    assert "```" not in content
    assert "=== Patientenübersicht ===" in content


# ── Meilenstein Prompt Smoke Tests (Dateiinhalt-Assertions) ──────────────────

from pathlib import Path as _Path  # noqa: E402

_PROMPT_PATH = _Path(__file__).parent.parent / "prompts" / "meilenstein_system.txt"


def _prompt_text() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def test_meilenstein_prompt_excludes_besonderheiten_section():
    """Besonderheiten-Sektion ist komplett aus dem Prompt entfernt."""
    prompt = _prompt_text()
    assert "== Besonderheiten ==" not in prompt, (
        "Besonderheiten-Sektion muss aus dem Prompt entfernt sein — "
        "sie produziert Verlaufs-Floskeln und ist empirisch fehleranfällig."
    )


def test_meilenstein_prompt_contains_antikoag_negativbeispiel():
    """Antikoag-Sektion enthält Layer-Kumulierung-Beispiel mit bMKE."""
    prompt = _prompt_text()
    has_bmke = "bMKE" in prompt
    has_kumulieren = "kumulativ" in prompt or "kumulieren" in prompt
    assert has_bmke or has_kumulieren, (
        "Antikoagulation-Sektion muss ein Negativbeispiel enthalten, "
        "das alle Layer kumuliert (Stichwort 'bMKE' oder 'kumulativ')."
    )


def test_meilenstein_prompt_contains_allergien_klausel():
    """Nebendiagnosen-Sektion enthält explizite Allergien-MUSS-Klausel."""
    prompt = _prompt_text()
    has_immer = "IMMER" in prompt and ("Allergi" in prompt)
    has_muss = "MUSS" in prompt and ("Allergi" in prompt)
    assert has_immer or has_muss, (
        "Relevante Nebendiagnosen muss eine explizite IMMER/MUSS-Klausel "
        "für Allergien enthalten."
    )
