"""Tests für Brief-Generator V1: brief_storage, agent_brief, Endpoints."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import agent_brief
import brief_storage
import storage
from main import app
from models.patient import Patient, Stammdaten

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_patient(pid: str = "P-0001") -> Patient:
    p = Patient(stammdaten=Stammdaten(id=pid, name="Test, Patient", aufnahmedatum="2026-04-01"))
    storage.save_patient(p)
    return p


def _llm_resp(content: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


# ── 1. brief_storage: leeres Skelett ─────────────────────────────────────────

def test_brief_storage_load_empty(isolated_data):
    """load_brief auf nie-existenten patient_id → leeres Skelett mit allen 5 Keys = ''."""
    result = brief_storage.load_brief("P-9999")
    for section in brief_storage.BRIEF_SECTIONS:
        assert result[section] == "", f"Sektion '{section}' sollte '' sein"


# ── 2. brief_storage: save + load Roundtrip ───────────────────────────────────

def test_brief_storage_save_and_load(isolated_data):
    """save → load gibt identischen Inhalt zurück; updated_at ist gesetzt."""
    brief = {
        "diagnosen": "Aortenklappenstenose",
        "anamnese": "Patient aufgenommen am 01.04.2026.",
        "therapie": "AVR am 02.04.2026.",
        "befunde": "",
        "verlauf": "Prolongiertes Weaning.",
    }
    brief_storage.save_brief("P-0001", brief)
    loaded = brief_storage.load_brief("P-0001")
    assert loaded["diagnosen"] == "Aortenklappenstenose"
    assert loaded["anamnese"] == "Patient aufgenommen am 01.04.2026."
    assert loaded["therapie"] == "AVR am 02.04.2026."
    assert loaded["befunde"] == ""
    assert loaded["verlauf"] == "Prolongiertes Weaning."
    assert loaded["updated_at"], "updated_at muss gesetzt sein"


# ── 3. brief_storage: atomares Schreiben ─────────────────────────────────────

def test_brief_storage_atomic_write(isolated_data):
    """Temp-Datei vorhanden (Crash vor rename) → Original bleibt intakt."""
    brief_storage.save_brief("P-0001", {
        "diagnosen": "original", "anamnese": "", "therapie": "", "befunde": "", "verlauf": ""
    })

    # Simuliere: Temp-Datei geschrieben, os.replace aber unterbrochen
    path = brief_storage._brief_path("P-0001")
    tmp = path.with_suffix(".yml.tmp")
    tmp.write_text("CORRUPTED: this should never be loaded", encoding="utf-8")

    loaded = brief_storage.load_brief("P-0001")
    assert loaded["diagnosen"] == "original"


# ── 4. brief_storage: unbekannte Sektion → ValueError ────────────────────────

def test_brief_storage_unknown_section_raises(isolated_data):
    """update_section mit unbekanntem Key → ValueError."""
    with pytest.raises(ValueError, match="Unbekannte Sektion"):
        brief_storage.update_section("P-0001", "foo", "content")


# ── 5. brief_storage: Whitelist-Keys alle akzeptiert ─────────────────────────

def test_brief_storage_section_whitelist(isolated_data):
    """Alle 5 Whitelist-Sektionen werden ohne Fehler akzeptiert."""
    for section in brief_storage.BRIEF_SECTIONS:
        result = brief_storage.update_section("P-0001", section, f"Inhalt für {section}")
        assert result[section] == f"Inhalt für {section}"


# ── 6. agent_brief: Diagnosen JSON → Markdown ─────────────────────────────────

def test_generate_diagnosen_renders_json(isolated_data):
    """LLM-Mock gibt JSON zurück → korrekte Markdown-Struktur mit fetter Hauptdiagnose."""
    payload = json.dumps({
        "behandlung": ["Aortenklappenstenose", "• KHK 3-Gefäß"],
        "verlauf": ["AV-Block III°"],
        "vorbekannt": ["Arterielle Hypertonie"],
    })
    patient = Patient(stammdaten=Stammdaten(id="P-0001", name="Test, Patient", aufnahmedatum="2026-04-01"))

    mock_client = MagicMock()
    mock_client.chat_completion = AsyncMock(return_value=_llm_resp(payload))

    with patch("agent_brief._lite", return_value=mock_client):
        result = asyncio.run(agent_brief.generate_diagnosen(patient))

    assert "**Behandlungsdiagnosen:**" in result
    assert "**Aortenklappenstenose**" in result
    assert "• KHK 3-Gefäß" in result
    assert "**Verlaufsdiagnosen:**" in result
    assert "AV-Block III°" in result
    assert "**Vorbekannte Diagnosen:**" in result
    assert "Arterielle Hypertonie" in result


# ── 7. agent_brief: Therapie JSON → 3 Sub-Blöcke ────────────────────────────

def test_generate_therapie_renders_three_subblocks(isolated_data):
    """LLM-Mock gibt JSON zurück → alle 3 Sub-Blöcke im Markdown-Output."""
    payload = json.dumps({
        "initial_op": "02.04.2026: AVR (Perikardbioprothese 23mm)",
        "antimikrobiell": ["02.04.–04.04. Cefuroxim 1.5g — peri-OP"],
        "weitere": ["05.04.2026: Elektrische Kardioversion bei VHFl"],
    })
    patient = Patient(stammdaten=Stammdaten(id="P-0001", name="Test, Patient", aufnahmedatum="2026-04-01"))

    mock_client = MagicMock()
    mock_client.chat_completion = AsyncMock(return_value=_llm_resp(payload))

    with patch("agent_brief._lite", return_value=mock_client):
        result = asyncio.run(agent_brief.generate_therapie(patient))

    assert "**Initial-OP:**" in result
    assert "AVR" in result
    assert "**Antimikrobielle Therapie:**" in result
    assert "Cefuroxim" in result
    assert "**Weitere Prozeduren:**" in result
    assert "Kardioversion" in result


# ── 8. agent_brief: Verlauf bekommt alle Kontext-Parameter ────────────────────

def test_generate_verlauf_passes_all_context(isolated_data):
    """generate_verlauf injiziert meilenstein/befunde/3 Sektionen in den Prompt."""
    patient = Patient(stammdaten=Stammdaten(id="P-0001", name="Test, Patient", aufnahmedatum="2026-04-01"))

    mock_client = MagicMock()
    mock_client.chat_completion = AsyncMock(
        return_value=_llm_resp("Der Verlauf war komplikationslos.")
    )

    with patch("agent_brief._flash", return_value=mock_client):
        asyncio.run(agent_brief.generate_verlauf(
            patient,
            meilenstein="MEILENSTEIN-TEXT",
            befunde_formatted="BEFUNDE-TEXT",
            diagnosen="DIAGNOSEN-TEXT",
            anamnese="ANAMNESE-TEXT",
            therapie="THERAPIE-TEXT",
        ))

    call_args = mock_client.chat_completion.call_args
    messages = call_args[0][0]
    prompt_text = messages[0]["content"]
    assert "MEILENSTEIN-TEXT" in prompt_text
    assert "BEFUNDE-TEXT" in prompt_text
    assert "DIAGNOSEN-TEXT" in prompt_text
    assert "ANAMNESE-TEXT" in prompt_text
    assert "THERAPIE-TEXT" in prompt_text


# ── 9. agent_brief: format_sap_befunde ────────────────────────────────────────

def test_format_sap_befunde_strips_boilerplate(isolated_data):
    """format_sap_befunde ruft LLM auf und gibt dessen Antwort zurück."""
    mock_client = MagicMock()
    mock_client.chat_completion = AsyncMock(
        return_value=_llm_resp("**TTE vom 01.04.2026**\nLVEF 55%.")
    )

    with patch("agent_brief._lite", return_value=mock_client):
        result = asyncio.run(agent_brief.format_sap_befunde("Rohtext SAP"))

    assert mock_client.chat_completion.called
    assert "**TTE vom 01.04.2026**" in result


# ── 10. Endpoint: generate full brief ────────────────────────────────────────

def test_endpoint_generate_full_brief(isolated_data):
    """POST /generate → 200, alle 4 Sektionen befüllt, befunde unverändert (leer)."""
    _make_patient("P-0001")

    with (
        patch("agent_brief.generate_diagnosen", new_callable=AsyncMock) as m_diag,
        patch("agent_brief.generate_anamnese", new_callable=AsyncMock) as m_anam,
        patch("agent_brief.generate_therapie", new_callable=AsyncMock) as m_ther,
        patch("agent_brief.generate_verlauf", new_callable=AsyncMock) as m_verl,
    ):
        m_diag.return_value = "Diagnosen-Text"
        m_anam.return_value = "Anamnese-Text"
        m_ther.return_value = "Therapie-Text"
        m_verl.return_value = "Verlauf-Text"

        res = client.post("/api/brief/P-0001/generate")

    assert res.status_code == 200
    body = res.json()
    assert body["diagnosen"] == "Diagnosen-Text"
    assert body["anamnese"] == "Anamnese-Text"
    assert body["therapie"] == "Therapie-Text"
    assert body["verlauf"] == "Verlauf-Text"
    assert body["befunde"] == ""


# ── 11. Endpoint: generate preserves existing befunde ─────────────────────────

def test_endpoint_generate_full_preserves_existing_befunde(isolated_data):
    """POST /generate überschreibt befunde-Sektion NICHT."""
    _make_patient("P-0001")
    brief_storage.update_section("P-0001", "befunde", "Vorhandener Befund")

    with (
        patch("agent_brief.generate_diagnosen", new_callable=AsyncMock) as m_diag,
        patch("agent_brief.generate_anamnese", new_callable=AsyncMock) as m_anam,
        patch("agent_brief.generate_therapie", new_callable=AsyncMock) as m_ther,
        patch("agent_brief.generate_verlauf", new_callable=AsyncMock) as m_verl,
    ):
        m_diag.return_value = "D"
        m_anam.return_value = "A"
        m_ther.return_value = "T"
        m_verl.return_value = "V"

        res = client.post("/api/brief/P-0001/generate")

    assert res.status_code == 200
    assert res.json()["befunde"] == "Vorhandener Befund"


# ── 12. Endpoint: regenerate verlauf uses current storage state ───────────────

def test_endpoint_regenerate_section_verlauf_uses_current_state(isolated_data):
    """POST /generate-section/verlauf übergibt aktuellen diagnosen/anamnese/therapie als Kontext."""
    _make_patient("P-0001")
    brief_storage.save_brief("P-0001", {
        "diagnosen": "Gespeicherte Diagnosen",
        "anamnese": "Gespeicherte Anamnese",
        "therapie": "Gespeicherte Therapie",
        "befunde": "Gespeicherte Befunde",
        "verlauf": "",
    })

    captured: dict = {}

    async def capture_verlauf(patient, meilenstein, befunde, diagnosen, anamnese, therapie):
        captured["diagnosen"] = diagnosen
        captured["anamnese"] = anamnese
        captured["therapie"] = therapie
        captured["befunde"] = befunde
        return "Neuer Verlauf"

    with patch("agent_brief.generate_verlauf", side_effect=capture_verlauf):
        res = client.post("/api/brief/P-0001/generate-section/verlauf")

    assert res.status_code == 200
    assert captured["diagnosen"] == "Gespeicherte Diagnosen"
    assert captured["anamnese"] == "Gespeicherte Anamnese"
    assert captured["therapie"] == "Gespeicherte Therapie"
    assert captured["befunde"] == "Gespeicherte Befunde"


# ── 13. Endpoint: befunde-Sektion nicht re-generierbar ───────────────────────

def test_endpoint_regenerate_section_befunde_rejected(isolated_data):
    """POST /generate-section/befunde → 400."""
    _make_patient("P-0001")
    res = client.post("/api/brief/P-0001/generate-section/befunde")
    assert res.status_code == 400


# ── 14. Endpoint: format-befunde ─────────────────────────────────────────────

def test_endpoint_format_befunde(isolated_data):
    """POST /format-befunde → LLM-Antwort in befunde-Sektion persistiert."""
    _make_patient("P-0001")

    with patch("agent_brief.format_sap_befunde", new_callable=AsyncMock) as mock_fmt:
        mock_fmt.return_value = "**TTE vom 01.04.2026**\nLVEF 55%."
        res = client.post("/api/brief/P-0001/format-befunde", json={"raw_text": "SAP Roh-Export"})

    assert res.status_code == 200
    assert res.json()["befunde"] == "**TTE vom 01.04.2026**\nLVEF 55%."

    stored = brief_storage.load_brief("P-0001")
    assert stored["befunde"] == "**TTE vom 01.04.2026**\nLVEF 55%."


# ── 15. Endpoint: save-section-edit (Autosave) ────────────────────────────────

def test_endpoint_save_section_edit(isolated_data):
    """PUT /section/verlauf → persistiert ohne LLM-Call."""
    _make_patient("P-0001")

    with patch("agent_brief.generate_verlauf", new_callable=AsyncMock) as mock_llm:
        res = client.put(
            "/api/brief/P-0001/section/verlauf",
            json={"content": "Manuell bearbeiteter Verlauf"},
        )
        assert not mock_llm.called

    assert res.status_code == 200
    assert res.json()["verlauf"] == "Manuell bearbeiteter Verlauf"

    stored = brief_storage.load_brief("P-0001")
    assert stored["verlauf"] == "Manuell bearbeiteter Verlauf"
