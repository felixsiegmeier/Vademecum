"""Tests für BR-B1: Brief-Lernlog — Storage, Endpoints, Agent-Injection."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import storage
import learning_storage
import agent_brief
import brief_storage
from main import app
from fastapi.testclient import TestClient
from models.patient import Patient, Stammdaten

client = TestClient(app)


def _make_patient(pid: str = "P-0001") -> Patient:
    p = Patient(stammdaten=Stammdaten(id=pid, name="Test, Patient", aufnahmedatum="2026-04-01"))
    storage.save_patient(p)
    return p


def _llm_resp(content: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


# ── 1. Storage: Roundtrip für Brief-Domain mit Sektion ───────────────────────

def test_brief_rules_roundtrip(isolated_data):
    """save_rules + load_rules für domain=brief, section=diagnosen → identisch."""
    rule = learning_storage.new_rule("Behandlungsdiagnosen", "KHK immer voll ausschreiben")
    learning_storage.save_rules([rule], domain="brief", section="diagnosen")
    loaded = learning_storage.load_rules(domain="brief", section="diagnosen")
    assert len(loaded) == 1
    assert loaded[0].id == rule.id
    assert loaded[0].rule_text == "KHK immer voll ausschreiben"


# ── 2. Storage: Sektionen sind voneinander isoliert ──────────────────────────

def test_brief_rules_sections_isolated(isolated_data):
    """Regeln für diagnosen und anamnese werden getrennt gespeichert."""
    r1 = learning_storage.new_rule("Behandlungsdiagnosen", "Regel für Diagnosen")
    r2 = learning_storage.new_rule("Anamnese", "Regel für Anamnese")
    learning_storage.save_rules([r1], domain="brief", section="diagnosen")
    learning_storage.save_rules([r2], domain="brief", section="anamnese")

    diag_rules = learning_storage.load_rules(domain="brief", section="diagnosen")
    anam_rules = learning_storage.load_rules(domain="brief", section="anamnese")

    assert len(diag_rules) == 1
    assert diag_rules[0].rule_text == "Regel für Diagnosen"
    assert len(anam_rules) == 1
    assert anam_rules[0].rule_text == "Regel für Anamnese"


# ── 3. Storage: last_output Roundtrip für Brief ───────────────────────────────

def test_brief_last_output_roundtrip(isolated_data):
    """save_last_output → load_last_output für domain=brief gibt gleichen Text zurück."""
    text = "**Aortenklappenstenose**\n- KHK 3-Gefäß"
    learning_storage.save_last_output("P-0001", text, domain="brief", section="diagnosen")
    loaded = learning_storage.load_last_output("P-0001", domain="brief", section="diagnosen")
    assert loaded == text


# ── 4. Endpoint: befunde → 404 ────────────────────────────────────────────────

def test_brief_learn_befunde_rejected(isolated_data):
    """POST /api/learn/brief/befunde/from-edits → 404 (befunde nicht lernfähig)."""
    _make_patient()
    res = client.post("/api/learn/brief/befunde/from-edits", json={
        "patient_id": "P-0001",
        "edited_content": "irgendwas",
    })
    assert res.status_code == 404


# ── 5. Endpoint: from-edits → 404 wenn kein Output als Referenz ──────────────

def test_brief_from_edits_404_when_no_reference(isolated_data):
    """POST /api/learn/brief/diagnosen/from-edits ohne vorherigen generate → 404."""
    _make_patient()
    res = client.post("/api/learn/brief/diagnosen/from-edits", json={
        "patient_id": "P-0001",
        "edited_content": "Aortenklappenstenose",
    })
    assert res.status_code == 404


# ── 6. Endpoint: save-rules für Brief-Sektion ────────────────────────────────

def test_brief_save_rules_endpoint(isolated_data):
    """POST /api/learn/brief/anamnese/save-rules speichert Regel."""
    res = client.post("/api/learn/brief/anamnese/save-rules", json={
        "rules_to_add": [{"section": "Anamnese", "rule_text": "Aufnahmegrund immer mit Datum"}],
        "rule_ids_to_delete": [],
    })
    assert res.status_code == 200
    body = res.json()
    assert body["saved_count"] == 1
    assert body["total_rules"] == 1

    stored = learning_storage.load_rules(domain="brief", section="anamnese")
    assert len(stored) == 1
    assert stored[0].rule_text == "Aufnahmegrund immer mit Datum"


# ── 7. Endpoint: rules-list für Brief-Sektion ────────────────────────────────

def test_brief_rules_endpoint_returns_stored(isolated_data):
    """GET /api/learn/brief/therapie/rules gibt gespeicherte Regeln zurück."""
    rule = learning_storage.new_rule("Therapie", "AB-Therapie immer mit Indikation")
    learning_storage.save_rules([rule], domain="brief", section="therapie")

    res = client.get("/api/learn/brief/therapie/rules")
    assert res.status_code == 200
    body = res.json()
    assert len(body["rules"]) == 1
    assert body["rules"][0]["rule_text"] == "AB-Therapie immer mit Indikation"


# ── 8. Endpoint: delete-rule für Brief-Sektion ───────────────────────────────

def test_brief_delete_rule_endpoint(isolated_data):
    """DELETE /api/learn/brief/verlauf/rules/{id} entfernt die Regel."""
    rule = learning_storage.new_rule("Verlauf", "Schluss immer mit Verlegungssatz")
    learning_storage.save_rules([rule], domain="brief", section="verlauf")

    res = client.delete(f"/api/learn/brief/verlauf/rules/{rule.id}")
    assert res.status_code == 204

    stored = learning_storage.load_rules(domain="brief", section="verlauf")
    assert stored == []


# ── 9. Agent: generate_diagnosen persistiert last_output ─────────────────────

def test_generate_diagnosen_persists_last_output(isolated_data):
    """generate_diagnosen speichert Ergebnis in last_output für domain=brief, section=diagnosen."""
    import json as _json
    patient = Patient(stammdaten=Stammdaten(id="P-0001", name="Test, Patient", aufnahmedatum="2026-04-01"))
    payload = _json.dumps({"behandlung": ["Aortenstenose"], "verlauf": [], "vorbekannt": []})

    mock_client = MagicMock()
    mock_client.chat_completion = AsyncMock(return_value=_llm_resp(payload))

    with patch("agent_brief._lite", return_value=mock_client):
        asyncio.run(agent_brief.generate_diagnosen(patient))

    saved = learning_storage.load_last_output("P-0001", domain="brief", section="diagnosen")
    assert saved is not None
    assert "Aortenstenose" in saved


# ── 10. Agent: Verlauf-Regeln nur in Pass 3 (curate) injiziert ───────────────

def test_verlauf_rules_only_injected_in_curate_pass(isolated_data):
    """Gelernte Verlauf-Regeln erscheinen nur im curate-Prompt (Pass 3), nicht in collect/audit."""
    patient = Patient(stammdaten=Stammdaten(id="P-0001", name="Test, Patient", aufnahmedatum="2026-04-01"))

    rule = learning_storage.new_rule("Verlauf", "Schluss immer mit Verlegungssatz")
    learning_storage.save_rules([rule], domain="brief", section="verlauf")

    collected_stub = "CLUSTER A\nSCHLUSS_INDIKATOR: KEINE_DOKUMENTATION"
    audited_stub = collected_stub + "\nAUDIT_RESULT: ALLES_ABGEDECKT"
    final_stub = "Verlauf war komplikationslos."

    mock_client = MagicMock()
    mock_client.chat_completion = AsyncMock(side_effect=[
        _llm_resp(collected_stub),
        _llm_resp(audited_stub),
        _llm_resp(final_stub),
    ])

    with patch("agent_brief._lite", return_value=mock_client):
        asyncio.run(agent_brief.generate_verlauf(
            patient,
            meilenstein=None,
            befunde_formatted="",
            diagnosen="",
            anamnese="",
            therapie="",
        ))

    pass1_prompt = mock_client.chat_completion.call_args_list[0][0][0][0]["content"]
    pass2_prompt = mock_client.chat_completion.call_args_list[1][0][0][0]["content"]
    pass3_prompt = mock_client.chat_completion.call_args_list[2][0][0][0]["content"]

    assert "Schluss immer mit Verlegungssatz" not in pass1_prompt
    assert "Schluss immer mit Verlegungssatz" not in pass2_prompt
    assert "Schluss immer mit Verlegungssatz" in pass3_prompt


# ── 11. Endpoint: system-prompt Brief-Sektion liefert Prompt-Datei ────────────

def test_brief_system_prompt_endpoint_returns_prompt(isolated_data):
    """GET /api/learn/brief/diagnosen/system-prompt liefert Inhalt von brief_diagnosen.txt."""
    res = client.get("/api/learn/brief/diagnosen/system-prompt")
    assert res.status_code == 200
    body = res.json()
    assert "patient_yaml" in body["content"]
