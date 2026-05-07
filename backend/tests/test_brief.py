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


# ── 8. agent_brief: Verlauf 3-Pass — Kontext-Durchreichung ───────────────────

def test_generate_verlauf_passes_all_context(isolated_data):
    """generate_verlauf: 3 LLM-Calls; Pass 1 enthält alle Kontext-Inputs; Ergebnis = Pass-3-Output."""
    patient = Patient(stammdaten=Stammdaten(id="P-0001", name="Test, Patient", aufnahmedatum="2026-04-01"))

    collected_stub = "CLUSTER A — ÜBERNAHME\n- Aufnahme nach OP\nSCHLUSS_INDIKATOR: KEINE_DOKUMENTATION"
    audited_stub = collected_stub + "\nAUDIT_RESULT: ALLES_ABGEDECKT"
    final_stub = "Der Verlauf war komplikationslos."

    mock_client = MagicMock()
    mock_client.chat_completion = AsyncMock(side_effect=[
        _llm_resp(collected_stub),
        _llm_resp(audited_stub),
        _llm_resp(final_stub),
    ])

    with patch("agent_brief._lite", return_value=mock_client):
        result = asyncio.run(agent_brief.generate_verlauf(
            patient,
            meilenstein="MEILENSTEIN-TEXT",
            befunde_formatted="BEFUNDE-TEXT",
            diagnosen="DIAGNOSEN-TEXT",
            anamnese="ANAMNESE-TEXT",
            therapie="THERAPIE-TEXT",
        ))

    assert result == final_stub
    assert mock_client.chat_completion.call_count == 3

    # Pass 1 (collect): alle Original-Inputs müssen im Prompt stehen
    pass1_prompt = mock_client.chat_completion.call_args_list[0][0][0][0]["content"]
    assert "MEILENSTEIN-TEXT" in pass1_prompt
    assert "BEFUNDE-TEXT" in pass1_prompt
    assert "DIAGNOSEN-TEXT" in pass1_prompt
    assert "ANAMNESE-TEXT" in pass1_prompt
    assert "THERAPIE-TEXT" in pass1_prompt

    # Pass 2 (audit): muss den collect-Output als {collected_substance} erhalten haben
    pass2_prompt = mock_client.chat_completion.call_args_list[1][0][0][0]["content"]
    assert "CLUSTER A — ÜBERNAHME" in pass2_prompt

    # Pass 3 (curate): muss den audit-Output als {audited_substance} erhalten haben
    pass3_prompt = mock_client.chat_completion.call_args_list[2][0][0][0]["content"]
    assert "AUDIT_RESULT: ALLES_ABGEDECKT" in pass3_prompt


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

    async def capture_verlauf(patient, meilenstein, befunde, diagnosen, anamnese, therapie, extra_context=""):
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


# ── 16. extra_context: Helper injiziert Block bei nicht-leerem Context ─────────

def test_inject_extra_context_nonempty(isolated_data):
    """_inject_extra_context ersetzt Platzhalter mit Hinweis-Block bei nicht-leerem Context."""
    prompt = "Prefix\n{extra_context}\nSuffix"
    result = agent_brief._inject_extra_context(prompt, "Wichtige Zusatzinfo")
    assert "Zusätzliche Anmerkungen" in result
    assert "Wichtige Zusatzinfo" in result
    assert "{extra_context}" not in result


# ── 17. extra_context: Helper entfernt Platzhalter bei leerem Context ──────────

def test_inject_extra_context_empty(isolated_data):
    """_inject_extra_context entfernt Platzhalter spurlos bei leerem extra_context."""
    prompt = "Prefix\n{extra_context}\nSuffix"
    result = agent_brief._inject_extra_context(prompt, "")
    assert "{extra_context}" not in result
    assert "Zusätzliche Anmerkungen" not in result
    assert "Prefix" in result
    assert "Suffix" in result


# ── 18. Endpoint /generate: extra_context Body wird durchgereicht ──────────────

def test_endpoint_generate_accepts_extra_context_body(isolated_data):
    """POST /generate mit extra_context-Body → Context wird an Sub-Agents weitergegeben."""
    _make_patient("P-0001")

    captured: dict = {}

    async def capture_diag(patient, extra_context=""):
        captured["extra_context"] = extra_context
        return "D"

    with (
        patch("agent_brief.generate_diagnosen", side_effect=capture_diag),
        patch("agent_brief.generate_anamnese", new_callable=AsyncMock, return_value="A"),
        patch("agent_brief.generate_therapie", new_callable=AsyncMock, return_value="T"),
        patch("agent_brief.generate_verlauf", new_callable=AsyncMock, return_value="V"),
    ):
        res = client.post(
            "/api/brief/P-0001/generate",
            json={"extra_context": "Spezieller Hinweis für alle Sektionen"},
        )

    assert res.status_code == 200
    assert captured.get("extra_context") == "Spezieller Hinweis für alle Sektionen"


# ── 19. Endpoint /generate-section: extra_context wird weitergereicht ──────────

def test_endpoint_regenerate_section_passes_extra_context(isolated_data):
    """POST /generate-section/anamnese mit extra_context-Body → Context korrekt übergeben."""
    _make_patient("P-0001")

    captured: dict = {}

    async def capture_anam(patient, extra_context=""):
        captured["extra_context"] = extra_context
        return "Neue Anamnese"

    with patch("agent_brief.generate_anamnese", side_effect=capture_anam):
        res = client.post(
            "/api/brief/P-0001/generate-section/anamnese",
            json={"extra_context": "Hinweis nur für Anamnese"},
        )

    assert res.status_code == 200
    assert captured.get("extra_context") == "Hinweis nur für Anamnese"


# ── 20. Prompt-Validierung: collect-Prompt enthält keine fertigen Brief-Sätze ──

def test_collect_prompt_contains_no_finished_sentences(isolated_data):
    """brief_verlauf_collect.txt darf keine Few-Shot-Fließtext-Sätze enthalten."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_collect.txt")
    # Sammler-Prompt soll kein fertiges Schluss-Pattern im Fließtext-Stil haben
    assert "Wir verlegen" not in prompt
    assert "verstarb am" not in prompt
    # Stattdessen: CLUSTER-Struktur und Bullet-Format muss erkennbar sein
    assert "CLUSTER" in prompt
    assert "SCHLUSS_INDIKATOR" in prompt


# ── 21. Prompt-Validierung: audit-Prompt hat read-only-Klausel ───────────────

def test_audit_prompt_is_read_only_for_existing_items(isolated_data):
    """brief_verlauf_audit.txt muss die Klausel 'NICHTS löschen oder umformulieren' enthalten."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_audit.txt")
    assert "NICHTS löschen oder umformulieren" in prompt
    assert "{collected_substance}" in prompt
    assert "AUDIT_RESULT" in prompt


# ── 22. Prompt-Validierung: curate-Prompt verbietet neue Fakten ──────────────

def test_curate_prompt_forbids_new_facts(isolated_data):
    """brief_verlauf_curate_shared.txt muss die Klausel 'KEINE NEUEN FAKTEN' enthalten."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_curate_shared.txt")
    assert "KEINE NEUEN FAKTEN" in prompt
    assert "{audited_substance}" in prompt
    assert "SCHLUSS_INDIKATOR" in prompt


# ── 23. Prompt-Validierung: collect-Prompt enthält Aufenthaltsdauer-Logik ─────

def test_collect_prompt_includes_aufenthaltsdauer_logic(isolated_data):
    """brief_verlauf_collect.txt muss SUBSTANZ_TIEFE und die 4-Stufen-Liste enthalten."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_collect.txt")
    assert "SUBSTANZ_TIEFE" in prompt
    assert "minimal" in prompt
    assert "kompakt" in prompt
    assert "mittel" in prompt
    assert "ausführlich" in prompt
    assert "AUFENTHALTSDAUER_TAGE" in prompt


# ── 24. DELETE /api/brief/{patient_id} ────────────────────────────────────────

def test_delete_brief_endpoint_removes_brief_and_snapshots(isolated_data):
    """DELETE /api/brief/{id} löscht Brief + last-Snapshots, lässt rules.yml in Ruhe."""
    import learning_storage

    pid = "P-0001"
    _make_patient(pid)

    # Brief anlegen
    brief_storage.save_brief(pid, {
        "diagnosen": "AKS", "anamnese": "x", "therapie": "y",
        "befunde": "", "verlauf": "z",
    })

    # Last-Snapshots für alle Sections anlegen
    for section in learning_storage.BRIEF_SECTIONS_WITH_LEARNING:
        learning_storage.save_last_output(pid, f"snapshot-{section}", domain="brief", section=section)

    # Regel anlegen — sollte nach Delete NICHT gelöscht werden
    rule = learning_storage.new_rule("Diagnosen", "Regel bleibt erhalten")
    learning_storage.save_rules([rule], domain="brief", section="diagnosen")

    res = client.delete(f"/api/brief/{pid}")
    assert res.status_code == 204

    # Brief weg
    loaded = brief_storage.load_brief(pid)
    for section in brief_storage.BRIEF_SECTIONS:
        assert loaded[section] == "", f"Sektion '{section}' sollte leer sein"

    # Snapshots weg
    for section in learning_storage.BRIEF_SECTIONS_WITH_LEARNING:
        snap = learning_storage.load_last_output(pid, domain="brief", section=section)
        assert snap is None, f"Snapshot für '{section}' sollte gelöscht sein"

    # Regeln noch da
    rules = learning_storage.load_rules(domain="brief", section="diagnosen")
    assert len(rules) == 1


def test_delete_brief_endpoint_404_when_no_brief(isolated_data):
    """DELETE /api/brief/{id} ohne existierenden Brief → 404."""
    _make_patient("P-0001")
    res = client.delete("/api/brief/P-0001")
    assert res.status_code == 404


# ── 25. POST /api/brief/{patient_id}/polish-section/{section} ─────────────────

def test_polish_section_endpoint(isolated_data):
    """POST /api/brief/{id}/polish-section/anamnese → LLM-Call + gespeicherter Result."""
    pid = "P-0001"
    _make_patient(pid)
    brief_storage.save_brief(pid, {
        "diagnosen": "AKS", "anamnese": "Patient wurde aufgenommen.",
        "therapie": "AVR", "befunde": "", "verlauf": "",
    })

    polished = "Frau Test wurde am 01.04.2026 aufgenommen."
    mock_resp = _llm_resp(polished)

    with patch.object(agent_brief._lite(), "chat_completion", new=AsyncMock(return_value=mock_resp)):
        res = client.post("/api/brief/P-0001/polish-section/anamnese", json={})
    assert res.status_code == 200
    data = res.json()
    assert data["anamnese"] == polished

    loaded = brief_storage.load_brief(pid)
    assert loaded["anamnese"] == polished


def test_polish_section_endpoint_empty_section(isolated_data):
    """POST /api/brief/{id}/polish-section/diagnosen auf leerer Sektion → 400."""
    pid = "P-0001"
    _make_patient(pid)
    # Brief mit leerer diagnosen-Sektion
    brief_storage.save_brief(pid, {
        "diagnosen": "", "anamnese": "x", "therapie": "y", "befunde": "", "verlauf": "",
    })
    res = client.post("/api/brief/P-0001/polish-section/diagnosen", json={})
    assert res.status_code == 400


def test_polish_section_endpoint_invalid_section(isolated_data):
    """POST /api/brief/{id}/polish-section/befunde → 400 (befunde nicht polierbar)."""
    pid = "P-0001"
    _make_patient(pid)
    res = client.post("/api/brief/P-0001/polish-section/befunde", json={})
    assert res.status_code == 400


# ── 26. polish_section — Lektor-Verhalten ─────────────────────────────────────

def test_polish_section_verlauf_uses_verlauf_polish_prompt(isolated_data):
    """polish_section(verlauf) muss brief_verlauf_polish.txt laden, nicht brief_verlauf_curate_shared.txt."""
    import agent_brief as ab

    captured_prompts = []

    async def capture_and_return(messages, **kwargs):
        captured_prompts.append(messages[0]["content"])
        return _llm_resp(messages[0]["content"])  # Echo input

    with patch.object(ab._lite(), "chat_completion", new=capture_and_return):
        import asyncio
        asyncio.run(ab.polish_section(
            section="verlauf",
            current_text="Patient wurde verlegt.",
        ))

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert "AUFGABE: Korrekturlesen" in prompt, "Verlauf-Polish muss Lektor-Klausel enthalten"
    assert "SUBSTANZ_TIEFE" not in prompt, "Curate-Prompt darf nicht geladen werden"
    assert "HYBRID-STRUKTUR" not in prompt, "Curate-Prompt-Klauseln dürfen nicht erscheinen"


def test_polish_section_output_unchanged_when_no_errors(isolated_data):
    """Wenn LLM den Input zurückgibt, ist der Output identisch (kein Aufblähen)."""
    import agent_brief as ab

    original = "Die Patientin wurde am 01.04.2026 aufgenommen."

    with patch.object(ab._lite(), "chat_completion", new=AsyncMock(return_value=_llm_resp(original))):
        import asyncio
        result = asyncio.run(ab.polish_section(section="anamnese", current_text=original))

    assert result == original


def test_polish_section_corrects_typo(isolated_data):
    """Wenn LLM einen Tippfehler korrigiert, gibt polish_section die korrigierte Version zurück."""
    import agent_brief as ab

    original = "Die Patientinn wurde aufgenommen."
    corrected = "Die Patientin wurde aufgenommen."

    with patch.object(ab._lite(), "chat_completion", new=AsyncMock(return_value=_llm_resp(corrected))):
        import asyncio
        result = asyncio.run(ab.polish_section(section="anamnese", current_text=original))

    assert result == corrected


def test_polish_section_all_sections_use_lektor_prompt(isolated_data):
    """Alle 4 Sektionen landen im Lektor-Prompt (AUFGABE: Korrekturlesen)."""
    import agent_brief as ab

    for section in ("diagnosen", "anamnese", "therapie", "verlauf"):
        captured = []

        async def cap(messages, **kwargs):
            captured.append(messages[0]["content"])
            return _llm_resp("ok")

        with patch.object(ab._lite(), "chat_completion", new=cap):
            import asyncio
            asyncio.run(ab.polish_section(section=section, current_text="x"))

        assert "AUFGABE: Korrekturlesen" in captured[0], f"Sektion '{section}' hat kein Lektor-Prompt"


# ── 30. AUFENTHALTSDAUER hartes Limit — Prompt-Klausel-Assertions ────────────

def test_collect_prompt_has_hard_limit_clause(isolated_data):
    """collect-Prompt enthält hartes AUFENTHALTSDAUER-Limit und NEGATIV-BEISPIEL."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_collect.txt")
    assert "HARTES SUBSTANZ_TIEFE-LIMIT" in prompt, "Hartes-Limit-Klausel fehlt"
    assert "unter 48h" in prompt, "Bed-and-Breakfast-Grenze fehlt"
    assert "INHALTLICHE KOMPLEXITÄT" in prompt, "Komplexitäts-Override-Verbot fehlt"
    assert "KOMPLIKATIONS-OVERRIDE" in prompt, "Override-Whitelist fehlt"
    assert "NEGATIV-BEISPIEL" in prompt, "Negativ-Beispiel fehlt"
    assert "CABG" in prompt, "Negativ-Beispiel-Skelett fehlt"


def test_collect_prompt_its_liegezeit_not_hospital_los(isolated_data):
    """collect-Prompt berechnet ITS-Liegezeit, nicht Hospital-Liegezeit."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_collect.txt")
    assert "ITS-Liegezeit" in prompt, "ITS-Liegezeit-Klausel fehlt"
    assert "hospital_los_fallback" in prompt, "Fallback-Marker fehlt"
    assert "Präoperative Normalstations-Aufenthalte werden NICHT mitgezählt" in prompt


def test_curate_prompt_has_substanz_tiefe_disziplin(isolated_data):
    """curate-Prompt enthält SUBSTANZ_TIEFE-DISZIPLIN-Klausel."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_curate_shared.txt")
    assert "SUBSTANZ_TIEFE-DISZIPLIN" in prompt, "Disziplin-Klausel fehlt"
    assert "verbindlich" in prompt, "Verbindlichkeits-Formulierung fehlt"
    assert "Aufblähen" in prompt, "Aufblähverbot fehlt"


def test_curate_prompt_has_sicherheitspflicht_regel(isolated_data):
    """Alte 'alle-Cluster'-Pflicht durch SICHERHEITS-PFLICHT-INHALTE ersetzt."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_curate_shared.txt")
    assert "SICHERHEITS-PFLICHT-INHALTE" in prompt
    assert "Pending Items" in prompt, "Pending-Items in Sicherheits-Pflicht fehlen"
    assert "explizit weggelassen" in prompt, "Routine-Streich-Erlaubnis fehlt"
    assert "Cluster und Hauptaussagen aus der Substanz müssen" not in prompt, (
        "Alte 'alle-Cluster'-Pflicht noch vorhanden — muss durch SICHERHEITS-PFLICHT ersetzt sein"
    )


def test_collect_prompt_bed_and_breakfast_boundary(isolated_data):
    """collect-Prompt nennt 48h-Grenze und maximal-Satz-Zahl für minimal."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_collect.txt")
    assert "48h" in prompt
    assert "4-5 Sätze" in prompt or "maximal 4-5" in prompt


def test_collect_prompt_komplikations_override_whitelist(isolated_data):
    """collect-Prompt enthält mindestens Reanimation und Tracheotomie in der Override-Whitelist."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_collect.txt")
    assert "Reanimation" in prompt, "Reanimation als Override fehlt"
    assert "Tracheotomie" in prompt, "Tracheotomie als Override fehlt"
    assert "Versterben" in prompt, "Versterben als Override fehlt"


def test_collect_prompt_no_override_noradrenalin(isolated_data):
    """collect-Prompt benennt Noradrenalin-Boli explizit als KEIN Override-Kriterium."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_collect.txt")
    assert "Noradrenalin" in prompt, "Nicht-Override-Beispiel Noradrenalin fehlt"
    assert "NICHT als Override" in prompt, "Nicht-Override-Klausel fehlt"


# ── 31. Prompt-Loader: .md bevorzugt, .txt als Fallback ──────────────────────

def test_prompt_loader_prefers_md_over_txt(isolated_data):
    """_get_prompt bevorzugt .md wenn beide Varianten existieren."""
    import agent_brief as ab

    stem = "_test_loader_pref"
    txt_path = ab._PROMPTS_DIR / f"{stem}.txt"
    md_path = ab._PROMPTS_DIR / f"{stem}.md"
    txt_path.write_text("TXT_CONTENT", encoding="utf-8")
    md_path.write_text("MD_CONTENT", encoding="utf-8")
    ab._PROMPT_CACHE.pop(f"{stem}.txt", None)
    try:
        result = ab._get_prompt(f"{stem}.txt")
        assert result == "MD_CONTENT", f"Erwartet MD_CONTENT, got {result!r}"
    finally:
        txt_path.unlink(missing_ok=True)
        md_path.unlink(missing_ok=True)
        ab._PROMPT_CACHE.pop(f"{stem}.txt", None)


def test_prompt_loader_txt_fallback(isolated_data):
    """_get_prompt fällt auf .txt zurück wenn kein .md existiert."""
    import agent_brief as ab

    stem = "_test_loader_fallback"
    txt_path = ab._PROMPTS_DIR / f"{stem}.txt"
    txt_path.write_text("TXT_ONLY", encoding="utf-8")
    ab._PROMPT_CACHE.pop(f"{stem}.txt", None)
    try:
        result = ab._get_prompt(f"{stem}.txt")
        assert result == "TXT_ONLY", f"Erwartet TXT_ONLY, got {result!r}"
    finally:
        txt_path.unlink(missing_ok=True)
        ab._PROMPT_CACHE.pop(f"{stem}.txt", None)


# ── 32. Adressaten-Profil-Mechanik ───────────────────────────────────────────

def test_load_adressatenprofil_existing(isolated_data):
    """_load_adressatenprofil lädt normalstation_intern erfolgreich."""
    import agent_brief as ab
    profil = ab._load_adressatenprofil("normalstation_intern")
    assert "ADRESSATENPROFIL" in profil, "Header fehlt im Profil"
    assert "NORMALSTATION" in profil, "Profil-Bezeichnung fehlt"


def test_load_adressatenprofil_fallback(isolated_data):
    """_load_adressatenprofil fällt bei unbekanntem Namen auf normalstation_intern zurück."""
    import agent_brief as ab
    profil = ab._load_adressatenprofil("nicht_vorhanden_xyz")
    # Fallback: normalstation_intern-Inhalt erwartet
    assert "NORMALSTATION" in profil, "Fallback-Profil nicht geladen"


def test_curate_prompt_contains_adressatenprofil(isolated_data):
    """generate_verlauf: Curate-Prompt (Pass 3) enthält das Adressaten-Profil."""
    patient = Patient(stammdaten=Stammdaten(id="P-0001", name="Test, Patient", aufnahmedatum="2026-04-01"))

    captured_prompts: list[str] = []

    async def capture(messages, **kwargs):
        captured_prompts.append(messages[0]["content"])
        return _llm_resp("ok")

    with patch("agent_brief._lite", return_value=MagicMock(chat_completion=capture)):
        asyncio.run(agent_brief.generate_verlauf(
            patient, meilenstein=None, befunde_formatted="", diagnosen="", anamnese="", therapie=""
        ))

    assert len(captured_prompts) == 3, "Erwartet 3 LLM-Calls"
    curate_prompt = captured_prompts[2]
    assert "NORMALSTATION" in curate_prompt, "Adressaten-Profil nicht im Curate-Prompt"
    assert "ADRESSATENPROFIL" in curate_prompt, "Profil-Header fehlt im Curate-Prompt"


def test_generate_verlauf_accepts_adressat_argument(isolated_data):
    """generate_verlauf akzeptiert adressat-Argument ohne TypeError."""
    patient = Patient(stammdaten=Stammdaten(id="P-0001", name="Test, Patient", aufnahmedatum="2026-04-01"))

    mock_client = MagicMock()
    mock_client.chat_completion = AsyncMock(side_effect=[
        _llm_resp("CLUSTER A\nSCHLUSS_INDIKATOR: KEINE_DOKUMENTATION"),
        _llm_resp("AUDIT_RESULT: ALLES_ABGEDECKT"),
        _llm_resp("Komplikationsloser Verlauf."),
    ])

    with patch("agent_brief._lite", return_value=mock_client):
        result = asyncio.run(agent_brief.generate_verlauf(
            patient, meilenstein=None, befunde_formatted="", diagnosen="", anamnese="", therapie="",
            adressat="normalstation_intern",
        ))
    assert result == "Komplikationsloser Verlauf."


# ── 33. Routine-Filter + Negativ-Beispiel + Diagnose-Logging ─────────────────

def test_curate_prompt_has_routine_filter(isolated_data):
    """brief_verlauf_curate_shared.txt enthält ROUTINE-FILTER-Klausel."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_curate_shared.txt")
    assert "ROUTINE-FILTER" in prompt, "ROUTINE-FILTER-Klausel fehlt"
    assert "abgeschlossenen Phase" in prompt, "Kernaussage fehlt"
    assert "Auffüllen ist verboten" in prompt, "Auffüll-Verbot fehlt"


def test_curate_prompt_has_negativ_beispiel(isolated_data):
    """brief_verlauf_curate_shared.txt enthält NEGATIV-BEISPIEL-Abschnitt."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_curate_shared.txt")
    assert "NEGATIV-BEISPIEL" in prompt, "NEGATIV-BEISPIEL-Marker fehlt"
    assert "SO NICHT" in prompt, "Negativ-Marker fehlt"
    assert "RICHTIG" in prompt, "Positiv-Gegenbeispiel fehlt"


def test_generate_verlauf_short_cabg_output_under_100_words(isolated_data):
    """generate_verlauf: unkomplizierter ~36h-CABG-Verlauf → Curate-Output < 100 Wörter."""
    patient = Patient(stammdaten=Stammdaten(id="P-0001", name="Schönberg, Karl", aufnahmedatum="2026-04-01"))

    collected = (
        "CLUSTER A -- UEBERNAHME\n"
        "- 01.04.2026: Postoperativ nach CABG (2-Gefäß-Bypass)\n"
        "AUFENTHALTSDAUER_TAGE: 2\n"
        "SUBSTANZ_TIEFE: kompakt\n"
        "SCHLUSS_INDIKATOR: KEINE_DOKUMENTATION\n"
    )
    audited = collected + "\nAUDIT_RESULT: ALLES_ABGEDECKT"
    final = (
        "Herr Schönberg wurde am 01.04.2026 postoperativ nach koronarer Bypassoperation übernommen. "
        "Der hämodynamische und respiratorische Verlauf gestaltete sich komplikationslos "
        "bei zeitgerechter Entwöhnung von Katecholaminen und regelrechter Extubation. "
        "Zum Zeitpunkt der Briefverfassung befand sich Herr Schönberg weiterhin auf der "
        "Intensivstation in Vorbereitung der Verlegung auf die Normalstation."
    )

    mock_client = MagicMock()
    mock_client.chat_completion = AsyncMock(side_effect=[
        _llm_resp(collected),
        _llm_resp(audited),
        _llm_resp(final),
    ])

    with patch("agent_brief._lite", return_value=mock_client):
        result = asyncio.run(agent_brief.generate_verlauf(
            patient, meilenstein=None, befunde_formatted="", diagnosen="", anamnese="", therapie=""
        ))

    word_count = len(result.split())
    assert word_count < 100, f"Erwartet < 100 Wörter für CABG-Kurzbrief, got {word_count}: {result!r}"


def test_generate_verlauf_diagnostic_logging(isolated_data, capsys):
    """generate_verlauf schreibt [BR-C1.7-DIAG]-Marker auf stderr."""
    patient = Patient(stammdaten=Stammdaten(id="P-0001", name="Test, Patient", aufnahmedatum="2026-04-01"))

    collected = "CLUSTER A\nSCHLUSS_INDIKATOR: KEINE_DOKUMENTATION"
    audited = collected + "\nAUDIT_RESULT: ALLES_ABGEDECKT"
    final = "Komplikationsloser Verlauf."

    mock_client = MagicMock()
    mock_client.chat_completion = AsyncMock(side_effect=[
        _llm_resp(collected),
        _llm_resp(audited),
        _llm_resp(final),
    ])

    with patch("agent_brief._lite", return_value=mock_client):
        asyncio.run(agent_brief.generate_verlauf(
            patient, meilenstein=None, befunde_formatted="", diagnosen="", anamnese="", therapie=""
        ))

    captured = capsys.readouterr()
    assert "[BR-C1.7-DIAG]" in captured.err, "Diagnose-Log-Marker fehlt auf stderr"
    assert "verlauf_collect" in captured.err, "Pass-1-Marker fehlt"
    assert "verlauf_curate" in captured.err, "Pass-3-Marker fehlt"


def test_curate_prompt_has_konnektoren_disziplin(isolated_data):
    """KONNEKTOREN-DISZIPLIN-Block mit erlaubter und verbotener Kategorie vorhanden."""
    prompt = agent_brief._get_prompt("brief_verlauf_curate_shared.txt")
    assert "KONNEKTOREN-DISZIPLIN" in prompt
    assert "kausal-logisch" in prompt, "Erlaubte Kategorie fehlt"
    assert "parallel hierzu" in prompt, "Verbotene Beispiel-Phrase fehlt"


def test_curate_prompt_has_konnektoren_faustregel(isolated_data):
    """Faustregel-Marker für den Füllkonnektor-Test vorhanden."""
    prompt = agent_brief._get_prompt("brief_verlauf_curate_shared.txt")
    assert "Faustregel" in prompt


def test_curate_prompt_has_minimal_beispiel(isolated_data):
    """Minimal-Beispiel-Marker für few-shot-Kalibrierung kurzer Verläufe vorhanden."""
    prompt = agent_brief._get_prompt("brief_verlauf_curate_minimal.txt")
    assert "Minimal-Beispiel" in prompt


def test_collect_prompt_has_pending_marker(isolated_data):
    """collect-Prompt enthält PENDING-ITEMS-Klausel mit [PENDING]-Marker."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_collect.txt")
    assert "PENDING-ITEMS" in prompt, "PENDING-ITEMS-Sektion fehlt"
    assert "[PENDING]" in prompt, "[PENDING]-Marker-Anweisung fehlt"


def test_curate_prompt_no_im_weiteren_verlauf_in_kohäsion(isolated_data):
    """'im weiteren Verlauf' als Konnektor-Beispiel wurde aus KOHÄSION a) entfernt."""
    import agent_brief as ab
    prompt = ab._get_prompt("brief_verlauf_curate_shared.txt")
    assert '"im weiteren Verlauf"' not in prompt, (
        "'im weiteren Verlauf' noch als Konnektor-Beispiel vorhanden — Floskel-Risiko"
    )


def test_curate_prompt_no_pauschales_konnektoren_verbot(isolated_data):
    """Altes pauschales Konnektoren-Verbot ist durch KONNEKTOREN-DISZIPLIN ersetzt."""
    prompt = agent_brief._get_prompt("brief_verlauf_curate_shared.txt")
    assert "Floskeln, Konnektoren" not in prompt, (
        "Pauschales Konnektoren-Verbot gefunden — muss durch KONNEKTOREN-DISZIPLIN-Block ersetzt sein"
    )


def test_curate_prompt_has_pending_replacement_rule(isolated_data):
    """Curate-Prompt enthält [PENDING]-Marker-Replacement-Anweisung."""
    prompt = agent_brief._get_prompt("brief_verlauf_curate_shared.txt")
    assert "[PENDING]-Marker-Regel" in prompt, "Marker-Replacement-Klausel fehlt"
    assert "NIEMALS literal" in prompt, "Literal-Verbot fehlt"


def test_curate_prompt_has_sofern_vorhanden(isolated_data):
    """SICHERHEITS-PFLICHT-INHALTE enthält 'sofern im Patientenfall vorhanden'."""
    prompt = agent_brief._get_prompt("brief_verlauf_curate_shared.txt")
    assert "sofern im Patientenfall vorhanden" in prompt


def test_curate_pending_marker_not_in_final_output(isolated_data):
    """[PENDING] aus Sammler-Output darf nicht literal im Curate-Ergebnis erscheinen."""
    patient = Patient(stammdaten=Stammdaten(id="P-0001", name="Test, Patient", aufnahmedatum="2026-04-01"))

    collected = (
        "CLUSTER A -- ÜBERNAHME\n"
        "- 01.04.2026: Postoperativ nach CABG\n"
        "CLUSTER J -- WUNDEN\n"
        "- Drainagen-Ex vorgesehen [PENDING]\n"
        "AUFENTHALTSDAUER_TAGE: 1\nSUBSTANZ_TIEFE: minimal\n"
        "SCHLUSS_INDIKATOR: LEBEND_VERLEGUNG\nSCHLUSS_DATUM: 02.04.2026\nSCHLUSS_ZIEL: Normalstation\n"
        "LETZTER_DOKUMENTIERTER_ZUSTAND: Stabil.\n"
    )
    audited = collected + "\nAUDIT: OK"
    final = (
        "Herr Test wurde am 01.04.2026 postoperativ nach CABG übernommen. "
        "Der Verlauf gestaltete sich komplikationslos; der Drain-Zug ist auf Station vorgesehen. "
        "Wir verlegen Herrn Test in stabilem Zustand auf die Normalstation und danken für die unkomplizierte Übernahme. "
        "Für Rückfragen stehen wir jederzeit zur Verfügung."
    )

    mock_client = MagicMock()
    mock_client.chat_completion = AsyncMock(side_effect=[
        _llm_resp(collected), _llm_resp(audited), _llm_resp(final),
    ])

    with patch("agent_brief._lite", return_value=mock_client):
        result = asyncio.run(agent_brief.generate_verlauf(
            patient, meilenstein=None, befunde_formatted="", diagnosen="", anamnese="", therapie=""
        ))

    assert "[PENDING]" not in result, f"[PENDING] literal im Output: {result!r}"
    assert "vorgesehen" in result or "steht noch aus" in result or "auf Station" in result


# ── 40. BR-C1.8: _extract_substanz_tiefe + _load_curate_prompt ───────────────

def test_extract_substanz_tiefe_parses_correctly(isolated_data):
    """_extract_substanz_tiefe liest SUBSTANZ_TIEFE-Zeile korrekt aus Sammler-Output."""
    import agent_brief as ab
    for tiefe in ("minimal", "kompakt", "mittel", "ausführlich"):
        collected = f"CLUSTER A -- TEST\n- foo\nSUBSTANZ_TIEFE: {tiefe}\n"
        assert ab._extract_substanz_tiefe(collected) == tiefe


def test_extract_substanz_tiefe_fallback_on_missing(isolated_data):
    """_extract_substanz_tiefe gibt 'kompakt' zurück wenn SUBSTANZ_TIEFE fehlt."""
    import agent_brief as ab
    result = ab._extract_substanz_tiefe("CLUSTER A -- TEST\n- foo\n")
    assert result == "kompakt"


def test_load_curate_prompt_minimal_contains_format_header(isolated_data):
    """_load_curate_prompt('minimal') enthält FORMAT: MINIMAL aus der format-spezifischen Datei."""
    import agent_brief as ab
    ab._PROMPT_CACHE.clear()
    prompt = ab._load_curate_prompt("minimal")
    assert "FORMAT: MINIMAL" in prompt
    assert "KEINE NEUEN FAKTEN" in prompt, "Shared-Inhalt fehlt in kombiniertem Prompt"


def test_load_curate_prompt_kompakt_contains_format_header(isolated_data):
    """_load_curate_prompt('kompakt') enthält FORMAT: KOMPAKT."""
    import agent_brief as ab
    ab._PROMPT_CACHE.clear()
    prompt = ab._load_curate_prompt("kompakt")
    assert "FORMAT: KOMPAKT" in prompt
    assert "KEINE NEUEN FAKTEN" in prompt


def test_load_curate_prompt_ausfuehrlich_contains_format_header(isolated_data):
    """_load_curate_prompt('ausführlich') enthält FORMAT: AUSFUEHRLICH."""
    import agent_brief as ab
    ab._PROMPT_CACHE.clear()
    prompt = ab._load_curate_prompt("ausführlich")
    assert "FORMAT: AUSFUEHRLICH" in prompt
    assert "KEINE NEUEN FAKTEN" in prompt


def test_load_curate_prompt_mittel_maps_to_kompakt(isolated_data):
    """_load_curate_prompt('mittel') → selber Prompt wie 'kompakt', kein Warning."""
    import agent_brief as ab
    ab._PROMPT_CACHE.clear()
    with patch("workflows.brief.verlauf.skill.logger") as mock_logger:
        prompt = ab._load_curate_prompt("mittel")
        mock_logger.warning.assert_not_called()
    assert "FORMAT: KOMPAKT" in prompt


def test_load_curate_prompt_unknown_falls_back_to_kompakt(isolated_data):
    """_load_curate_prompt mit unbekanntem Wert → Fallback kompakt + logger.warning."""
    import agent_brief as ab
    ab._PROMPT_CACHE.clear()
    with patch("workflows.brief.verlauf.skill.logger") as mock_logger:
        prompt = ab._load_curate_prompt("unbekannt")
        mock_logger.warning.assert_called_once()
    assert "FORMAT: KOMPAKT" in prompt


def test_no_cross_contamination_minimal_has_no_ausfuehrlich_stilanker(isolated_data):
    """Minimal-Prompt enthält keine Ausführlich-Stil-Anker (Vasoplegie, Impella)."""
    import agent_brief as ab
    ab._PROMPT_CACHE.clear()
    prompt = ab._load_curate_prompt("minimal")
    assert "vasoplegisch" not in prompt.lower()
    assert "Impella" not in prompt
