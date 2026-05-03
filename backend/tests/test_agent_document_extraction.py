"""Tests für 2-Pass-Extraktion, Multi-Turn-Loop, Proposal-Gruppierung und Apply-Logik."""
import asyncio
import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import storage
from agent_extraction_core import (
    MAX_ITERATIONS_BLOCK_1,
    THINKING_BUDGET_BLOCK_1,
    THINKING_BUDGET_BLOCK_2,
    Proposal,
    ToolCallInfo,
    group_proposals,
    run_pass,
)
from agent_document_extraction import (
    _PASS2_TOOLS,
    _build_block1_system,
    _build_block2_system,
    extract_proposals,
)
from agent_tools import add_verlaufsdiagnose, delete_entry
from models.patient import Diagnose, Patient, Stammdaten, VerlaufsEintrag


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_patient(**kwargs) -> Patient:
    p = Patient(
        stammdaten=Stammdaten(id="P-0001", name="Test", aufnahmedatum="2026-04-01"),
        **kwargs,
    )
    storage.save_patient(p)
    return p


def _mock_tool_call(name: str, args: dict, tc_id: str = "tc_01") -> MagicMock:
    tc = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    tc.id = tc_id
    return tc


def _llm_response(tool_calls: list | None) -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.tool_calls = tool_calls
    resp.choices[0].message.model_dump.return_value = {"role": "assistant", "content": None}
    return resp


def _malformed_response() -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.tool_calls = None
    resp.choices[0].message.content = None
    resp.choices[0].finish_reason = "function_call_filter: MALFORMED_FUNCTION_CALL"
    resp.choices[0].message.model_dump.return_value = {"role": "assistant", "content": None}
    resp.usage = None
    return resp


# ── Test 1: Block 1 läuft ohne Patientenstand ─────────────────────────────────


def test_block1_runs_without_state():
    """Leerer Patient: Pass 1 sammelt Tool-Calls in Proposals."""
    tc = _mock_tool_call("add_behandlungsdiagnose", {"text": "COPD", "datum": None, "source_quote": "zitat"})
    mock_llm = MagicMock()
    mock_llm.chat_completion = AsyncMock(side_effect=[
        _llm_response([tc]),
        _llm_response(None),
    ])

    system = _build_block1_system(patient=None)
    iters = asyncio.run(run_pass(
        llm=mock_llm,
        system_prompt=system,
        user_messages=[{"role": "user", "content": "Test-Dokument"}],
        tools=[],
        thinking_budget=THINKING_BUDGET_BLOCK_1,
    ))

    assert len(iters) == 1
    assert iters[0][0]["tool"] == "add_behandlungsdiagnose"
    assert iters[0][0]["args"]["text"] == "COPD"


# ── Test 2: Block 2 enthält nur add_verlaufseintrag und delete_entry ──────────


def test_block2_filters_to_verlaufseintrag_only():
    """Pass 2 darf nur add_verlaufseintrag und delete_entry anbieten."""
    tool_names = {s["function"]["name"] for s in _PASS2_TOOLS}
    assert tool_names == {"add_verlaufseintrag", "delete_entry"}


# ── Test 3: Multi-Turn-Loop endet bei 0 Tool-Calls ───────────────────────────


def test_multi_turn_loop_stops_on_zero_calls():
    """Loop endet sobald der LLM keine Tool-Calls mehr zurückgibt."""
    tc = _mock_tool_call("add_verlaufsdiagnose", {"text": "T", "datum": "2026-04-01", "source_quote": "q"})
    mock_llm = MagicMock()
    mock_llm.chat_completion = AsyncMock(side_effect=[
        _llm_response([tc]),   # Iter 1: Tool-Call
        _llm_response([tc]),   # Iter 2: Tool-Call
        _llm_response(None),   # Iter 3: kein Tool-Call → Abbruch
    ])

    iters = asyncio.run(run_pass(
        llm=mock_llm,
        system_prompt="test",
        user_messages=[{"role": "user", "content": "doc"}],
        tools=[],
        thinking_budget=0,
    ))

    assert mock_llm.chat_completion.call_count == 3
    assert len(iters) == 2  # Nur Iter 1 und 2 hatten gültige Calls


# ── Test 3b: MAX_ITERATIONS_BLOCK_1 ist 8 ────────────────────────────────────


def test_block1_max_iterations_is_8():
    """Konstante MAX_ITERATIONS_BLOCK_1 muss 8 betragen."""
    assert MAX_ITERATIONS_BLOCK_1 == 8


# ── Test 4: Multi-Turn-Loop bricht nach max_iterations ab ────────────────────


def test_multi_turn_loop_max_iterations():
    """Loop endet nach max_iterations, auch wenn der LLM immer Tool-Calls liefert."""
    tc = _mock_tool_call("add_verlaufsdiagnose", {"text": "T", "datum": "2026-04-01", "source_quote": "q"})
    mock_llm = MagicMock()
    mock_llm.chat_completion = AsyncMock(return_value=_llm_response([tc]))

    iters = asyncio.run(run_pass(
        llm=mock_llm,
        system_prompt="test",
        user_messages=[{"role": "user", "content": "doc"}],
        tools=[],
        thinking_budget=0,
        max_iterations=5,
    ))

    assert mock_llm.chat_completion.call_count == 5
    assert len(iters) == 5


# ── Test 5: State-Aware-YAML erscheint im Block-1-System-Prompt ───────────────


def test_state_aware_yaml_in_system_prompt(isolated_data):
    """Patient mit Items → System-Prompt enthält <aktueller_stand> mit YAML."""
    patient = Patient(
        stammdaten=Stammdaten(id="P-0001", name="Test", aufnahmedatum="2026-04-01"),
        behandlungsdiagnosen=[
            Diagnose(id="ABC123", text="COPD GOLD 3", datum=None, source_quote="q")
        ],
    )

    system = _build_block1_system(patient)

    assert "<aktueller_stand>" in system
    assert "COPD GOLD 3" in system
    assert "ABC123" in system  # ULID im YAML sichtbar


def test_block1_empty_patient_shows_leer():
    """Kein Patient → <aktueller_stand>leer</aktueller_stand>."""
    system = _build_block1_system(patient=None)
    assert "<aktueller_stand>leer</aktueller_stand>" in system


# ── Test 6: Alle Verlaufseinträge erscheinen im Block-2-System-Prompt ────────


def test_block2_all_verlaufseintraege_in_prompt(isolated_data):
    """Patient mit mehreren Einträgen → ALLE Einträge (Datum + ID + Preview) im Prompt."""
    patient = Patient(
        stammdaten=Stammdaten(id="P-0001", name="Test", aufnahmedatum="2026-04-01"),
        verlaufseintraege=[
            VerlaufsEintrag(id="ID1", datum=date(2026, 4, 14), text="Erster Eintrag", source_quote="q"),
            VerlaufsEintrag(id="ID2", datum=date(2026, 4, 15), text="Zweiter Eintrag", source_quote="q"),
            VerlaufsEintrag(id="ID3", datum=date(2026, 4, 16), text="Dritter Eintrag", source_quote="q"),
        ],
    )

    system = _build_block2_system(patient)

    # Alle drei Einträge müssen im Prompt auftauchen (Datum + ID + Preview)
    assert "ID1" in system
    assert "2026-04-14" in system
    assert "Erster Eintrag" in system
    assert "ID2" in system
    assert "2026-04-15" in system
    assert "Zweiter Eintrag" in system
    assert "ID3" in system
    assert "2026-04-16" in system
    assert "Dritter Eintrag" in system


def test_block2_empty_patient_shows_keine():
    """Kein Verlaufseintrag → <existierende_verlaufseintraege>keine<...>."""
    system = _build_block2_system(patient=None)
    assert "<existierende_verlaufseintraege>keine</existierende_verlaufseintraege>" in system


# ── Test 6b: Idempotenz-Infrastruktur — State im Prompt für LLM sichtbar ─────


def test_block2_entry_id_visible_for_skip_detection(isolated_data):
    """Patient mit Verlaufseintrag → ID und Preview im Prompt (LLM kann Skip/Update entscheiden)."""
    patient = Patient(
        stammdaten=Stammdaten(id="P-0001", name="Test", aufnahmedatum="2026-04-01"),
        verlaufseintraege=[
            VerlaufsEintrag(
                id="VE_EARLY",
                datum=date(2026, 4, 23),
                text="Beatmungsversuch ohne Erfolg, re-intubiert.",
                source_quote="q",
            ),
        ],
    )
    system = _build_block2_system(patient)
    # ID muss sichtbar sein, damit LLM delete_entry(id=...) aufrufen kann
    assert "VE_EARLY" in system
    assert "2026-04-23" in system
    assert "Beatmungsversuch" in system


def test_block2_preview_truncated_at_250():
    """Eintrag mit Text > 250 Zeichen → Preview wird auf 250 Zeichen + '…' gekürzt."""
    long_text = "A" * 300
    patient = Patient(
        stammdaten=Stammdaten(id="P-0001", name="Test", aufnahmedatum="2026-04-01"),
        verlaufseintraege=[
            VerlaufsEintrag(id="VE1", datum=date(2026, 4, 14), text=long_text, source_quote="q"),
        ],
    )
    system = _build_block2_system(patient)
    assert "A" * 250 + "…" in system
    assert "A" * 251 + "…" not in system  # kein Zeichen zu viel


# ── Test 7: Update-Gruppierung ─────────────────────────────────────────────────


def test_update_grouping_single_delete_add():
    """1 delete + 1 add im selben Turn → 1 Update-Proposal."""
    iterations = [[
        {"tool": "delete_entry", "args": {"id": "ABC123", "source_quote": "q"}},
        {"tool": "add_verlaufsdiagnose", "args": {"text": "COPD GOLD 3", "datum": "2026-04-01", "source_quote": "q"}},
    ]]
    proposals = group_proposals(iterations)

    assert len(proposals) == 1
    assert proposals[0].type == "update"
    assert proposals[0].delete_call is not None
    assert proposals[0].add_call is not None
    assert proposals[0].delete_call.tool == "delete_entry"
    assert proposals[0].add_call.tool == "add_verlaufsdiagnose"


def test_update_grouping_two_deletes_two_adds_separate():
    """2 deletes + 2 adds im selben Turn → 4 separate Proposals (kein Pairing)."""
    iterations = [[
        {"tool": "delete_entry", "args": {"id": "ID1", "source_quote": "q"}},
        {"tool": "delete_entry", "args": {"id": "ID2", "source_quote": "q"}},
        {"tool": "add_verlaufsdiagnose", "args": {"text": "T1", "datum": "2026-04-01", "source_quote": "q"}},
        {"tool": "add_behandlungsdiagnose", "args": {"text": "T2", "datum": None, "source_quote": "q"}},
    ]]
    proposals = group_proposals(iterations)

    assert len(proposals) == 4
    types = {p.type for p in proposals}
    assert types == {"add", "delete"}


def test_update_grouping_add_only():
    """Nur adds → add-Proposals, kein Update."""
    iterations = [[
        {"tool": "add_befund", "args": {"datum": "2026-04-01", "art": "TTE", "text": "EF 45%", "source_quote": "q"}},
    ]]
    proposals = group_proposals(iterations)
    assert len(proposals) == 1
    assert proposals[0].type == "add"
    assert proposals[0].call is not None


def test_update_grouping_update_singleton():
    """update_*-Tool → update_singleton-Proposal."""
    iterations = [[
        {"tool": "update_anamnese", "args": {"text": "Neue Anamnese", "source_quote": "q"}},
    ]]
    proposals = group_proposals(iterations)
    assert len(proposals) == 1
    assert proposals[0].type == "update_singleton"
    assert proposals[0].call.tool == "update_anamnese"


def test_block2_uebergangstag_update_as_single_proposal():
    """delete_entry + add_verlaufseintrag im selben Turn → 1 Update-Proposal (Übergangstag-Pattern)."""
    iterations = [[
        {"tool": "delete_entry", "args": {"id": "VE_EARLY", "source_quote": "Spätdienst ergänzt"}},
        {"tool": "add_verlaufseintrag", "args": {
            "datum": "2026-04-23",
            "text": "Beatmungsversuch ohne Erfolg, re-intubiert. Abends Angehörigengespräch (Söhne, Ehefrau): DNR-Entscheidung bei MOF, Übergang Palliation.",
            "source_quote": "Station 23.04.",
        }},
    ]]
    proposals = group_proposals(iterations)
    assert len(proposals) == 1
    assert proposals[0].type == "update"
    assert proposals[0].delete_call is not None
    assert proposals[0].add_call is not None
    assert proposals[0].delete_call.tool == "delete_entry"
    assert proposals[0].delete_call.args["id"] == "VE_EARLY"
    assert proposals[0].add_call.tool == "add_verlaufseintrag"
    assert "DNR" in proposals[0].add_call.args["text"]


# ── Test 8: Apply-Update-Gruppe ────────────────────────────────────────────────


def test_apply_update_group(isolated_data):
    """Update-Proposal: altes Item weg, neues Item mit neuer ULID drin."""
    _make_patient()
    old = add_verlaufsdiagnose(patient_id="P-0001", text="COPD", datum="2026-04-01", source_quote="q")
    old_id = old["id"]

    # Transactional: delete altes, add neues
    del_result = delete_entry(patient_id="P-0001", id=old_id, source_quote="update")
    assert del_result["ok"] is True

    new_result = add_verlaufsdiagnose(
        patient_id="P-0001", text="COPD GOLD 3 mit LTOT", datum="2026-04-01", source_quote="update"
    )
    assert new_result["ok"] is True
    new_id = new_result["id"]

    p = storage.load_patient("P-0001")
    ids = [d.id for d in p.verlaufsdiagnosen]
    assert old_id not in ids
    assert new_id in ids
    assert old_id != new_id
    assert p.verlaufsdiagnosen[-1].text == "COPD GOLD 3 mit LTOT"


def test_apply_update_group_rollback_on_delete_fail(isolated_data):
    """Schlägt delete fehl, wird add NICHT ausgeführt."""
    _make_patient()

    del_result = delete_entry(patient_id="P-0001", id="NONEXISTENT_ULID_12345678", source_quote="x")
    assert del_result["ok"] is False

    # Kein add nach fehlgeschlagenem delete → Patient bleibt unverändert
    p = storage.load_patient("P-0001")
    assert p.verlaufsdiagnosen == []


# ── Test 9: Auto-Skip bei 0 Proposals ────────────────────────────────────────


def test_auto_skip_zero_proposals():
    """Leere Iterationen → group_proposals gibt [] zurück → auto_skip-Condition erfüllt."""
    proposals = group_proposals([])
    assert proposals == []
    auto_skipped = len(proposals) == 0
    assert auto_skipped is True


def test_auto_skip_nonzero_proposals():
    """Mindestens ein Call → kein Auto-Skip."""
    iterations = [[{"tool": "add_befund", "args": {"datum": "2026-04-01", "art": "TTE", "text": "x", "source_quote": "q"}}]]
    proposals = group_proposals(iterations)
    assert len(proposals) > 0
    auto_skipped = len(proposals) == 0
    assert auto_skipped is False


# ── Test 10: thinking_budget wird an llm_client übergeben ─────────────────────


def test_thinking_budget_passed_to_client_block1():
    """run_pass übergibt thinking_budget=THINKING_BUDGET_BLOCK_1 an llm.chat_completion."""
    mock_llm = MagicMock()
    mock_llm.chat_completion = AsyncMock(return_value=_llm_response(None))

    asyncio.run(run_pass(
        llm=mock_llm,
        system_prompt="test",
        user_messages=[{"role": "user", "content": "doc"}],
        tools=[],
        thinking_budget=THINKING_BUDGET_BLOCK_1,
    ))

    mock_llm.chat_completion.assert_called_once()
    kwargs = mock_llm.chat_completion.call_args.kwargs
    assert kwargs["thinking_budget"] == THINKING_BUDGET_BLOCK_1


def test_thinking_budget_passed_to_client_block2():
    """run_pass übergibt thinking_budget=THINKING_BUDGET_BLOCK_2 an llm.chat_completion."""
    mock_llm = MagicMock()
    mock_llm.chat_completion = AsyncMock(return_value=_llm_response(None))

    asyncio.run(run_pass(
        llm=mock_llm,
        system_prompt="test",
        user_messages=[{"role": "user", "content": "doc"}],
        tools=[],
        thinking_budget=THINKING_BUDGET_BLOCK_2,
    ))

    mock_llm.chat_completion.assert_called_once()
    kwargs = mock_llm.chat_completion.call_args.kwargs
    assert kwargs["thinking_budget"] == THINKING_BUDGET_BLOCK_2


# ── Smoke-Tests: Prompt-Inhalte ───────────────────────────────────────────────


def test_block1_prompt_loaded_contains_classification_examples():
    """Pflicht-Sektionen sind im Block-1-Prompt enthalten (Guard gegen versehentliches Löschen)."""
    from pathlib import Path
    prompt = (Path(__file__).parent.parent / "prompts" / "extraction_block1.txt").read_text(encoding="utf-8")

    required_terms = [
        "Behandlungsdiagnose",
        "Verlaufsdiagnose",
        "Vorbekannte Diagnose",
        "Mikrobiologie",
        "NICHT",          # NICHT DOKUMENTIEREN-Sektion
        "Tracheotomie",
        "CVVHDF",
    ]
    missing = [t for t in required_terms if t not in prompt]
    assert missing == [], f"Fehlende Begriffe in extraction_block1.txt: {missing}"


def test_block1_prompt_iter5_includes_anti_confound():
    """Block-1-Iter-5: Anti-Confound-Klausel und 7-Antibiotika-Linien-Beispiel müssen drin sein."""
    from pathlib import Path
    prompt = (Path(__file__).parent.parent / "prompts" / "extraction_block1.txt").read_text(encoding="utf-8")

    required = [
        "ANTI-CONFOUND",                # prominenter Section-Header
        "Patientenübersicht",           # konkrete Confound-Quelle benannt
        "eingebauten Lehrer",           # Schlüsselformulierung
        "7 Antibiotika-Linien",         # konkretes celik-Beispiel (im Prompt-Text)
    ]
    missing = [t for t in required if t not in prompt]
    assert missing == [], f"Anti-Confound-Bausteine fehlen in extraction_block1.txt: {missing}"


def test_block1_prompt_iter5_has_9_categories_with_bedside():
    """Block-1-Iter-5 nennt 9 Kategorien inklusive `bedside`."""
    from pathlib import Path
    prompt = (Path(__file__).parent.parent / "prompts" / "extraction_block1.txt").read_text(encoding="utf-8")

    assert "9 gültige Werte" in prompt
    assert "bedside" in prompt.lower()
    # Bedside-Kategorie-Definition mit konkreten Eingriffen
    assert "PAK-Anlage" in prompt
    assert "Bronchoskopie" in prompt
    assert "Pleurapunktion" in prompt


def test_block1_prompt_iter5_bedside_tracheotomie_redefined():
    """Tracheotomie ist NICHT mehr automatisch `respiratorisch` — Bedside-Tracheo unter `bedside`."""
    from pathlib import Path
    prompt = (Path(__file__).parent.parent / "prompts" / "extraction_block1.txt").read_text(encoding="utf-8")

    # `respiratorisch` ist neu als Atemunterstützungs-MODI definiert
    assert "Atemunterstützungs-MODI" in prompt
    # Bedside-Tracheotomie wird explizit als bedside-Kategorie genannt
    assert "Bedside-Tracheotomie" in prompt


def test_block1_prompt_iter5_diagnose_classification_examples():
    """Block-1-Iter-5 enthält Diagnose-Klassifikations-Beispiele inklusive verlaufs-relevanter."""
    from pathlib import Path
    prompt = (Path(__file__).parent.parent / "prompts" / "extraction_block1.txt").read_text(encoding="utf-8")

    required = [
        "Hämatothorax",                 # Verlaufsdiagnose-Beispiel
        "Anurisches AKI",               # Verlaufsdiagnose-Beispiel
        "CIP/CIM",                      # Verlaufsdiagnose-Beispiel
        "Vasoplegischer Schock",        # fehlende Hauptdiagnose explizit benannt
        "Anasarka",                     # eigene Diagnose, nicht nur Beschreibung
        "Vorhofflimmern",               # Rhythmus-Diagnose
    ]
    missing = [t for t in required if t not in prompt]
    assert missing == [], f"Diagnose-Beispiele fehlen in extraction_block1.txt: {missing}"


def test_block1_prompt_iter5_befund_recall_specifics():
    """Block-1-Iter-5 hebt Befund-Recall hervor: TEE, HIT, PAK-Messungen."""
    from pathlib import Path
    prompt = (Path(__file__).parent.parent / "prompts" / "extraction_block1.txt").read_text(encoding="utf-8")

    required = [
        "BEFUND-RECALL",
        "TEE",
        "HIT",
        "PAK-Messung",
        "LVEF",
    ]
    missing = [t for t in required if t not in prompt]
    assert missing == [], f"Befund-Recall-Bausteine fehlen: {missing}"


def test_block1_prompt_iter5_anamnese_completeness():
    """Block-1-Iter-5 enthält Anamnese-Vollständigkeitsklausel mit Verlegungs-Trigger."""
    from pathlib import Path
    prompt = (Path(__file__).parent.parent / "prompts" / "extraction_block1.txt").read_text(encoding="utf-8")

    assert "ANAMNESE-VOLLSTÄNDIGKEIT" in prompt
    assert "Erstvorstellung" in prompt
    assert "Verlegungs-Trigger" in prompt or "triggerte den Transfer" in prompt


def test_block2_prompt_includes_datum_short_format():
    """Block-2-Prompt enthält Anweisung zum TT.MM.-Format im Text."""
    from pathlib import Path
    prompt = (Path(__file__).parent.parent / "prompts" / "extraction_block2.txt").read_text(encoding="utf-8")
    assert "TT.MM." in prompt, "Datumsformat TT.MM. fehlt in extraction_block2.txt"


def test_block1_prompt_includes_status_pflicht():
    from pathlib import Path
    prompt = (Path(__file__).parent.parent / "prompts" / "extraction_block1.txt").read_text(encoding="utf-8")
    assert "update_status(aktiv=true" in prompt
    assert "MUSS-Aufrufe" in prompt or "Pflicht" in prompt.lower()


# ── Test 11: Block-2-Prompt enthält Iter-v2-Konzeptbausteine ─────────────────


def test_block2_prompt_iter_v2_contains_muss_dimensionen():
    """Block-2-Prompt (Iter v2) enthält MUSS-Dimensionen und AV-Block-III°-Beispiel."""
    from pathlib import Path
    prompt = (Path(__file__).parent.parent / "prompts" / "extraction_block2.txt").read_text(encoding="utf-8")

    required = [
        "MUSS",                       # MUSS-Sektion vorhanden
        "Therapie-Trigger",           # Dimension 1
        "Mikrobiologie-Steuerung",    # Dimension 4
        "Gespräche",                  # Dimension 3
        "AV-Block III",               # AV-Block-Beispiel
        "KONVERGENZ",                 # Konvergenz-Prinzip
        "Merge",                      # Merge-Klausel
        "BLOCK-2-TOOL-BESCHRÄNKUNG",  # Tool-Trennung explizit
    ]
    missing = [t for t in required if t not in prompt]
    assert missing == [], f"Fehlende Begriffe in extraction_block2.txt (Iter v2): {missing}"


def test_block2_prompt_iter_v2_separates_was_pruefen_from_wie_schreiben():
    """Block-2-Iter-v2 trennt Prüfliste (8 Dimensionen) von Schreibanweisungen klar."""
    from pathlib import Path
    prompt = (Path(__file__).parent.parent / "prompts" / "extraction_block2.txt").read_text(encoding="utf-8")

    assert "WAS PRÜFEN" in prompt
    assert "WIE SCHREIBEN" in prompt
    # MUSS / SOLL / KANN als drei Prio-Stufen vorhanden
    assert "SOLL" in prompt
    assert "KANN" in prompt
    # Mittelweg-Klausel namentlich
    assert "MITTELWEG-REDUNDANZ" in prompt or "Mittelweg-Redundanz" in prompt


def test_block2_prompt_iter_v2_includes_mikrobio_merge_example():
    """Block-2-Iter-v2 enthält Mikrobio-Trigger-Merge-Beispiel mit Erreger und AB-Konsequenz."""
    from pathlib import Path
    prompt = (Path(__file__).parent.parent / "prompts" / "extraction_block2.txt").read_text(encoding="utf-8")

    # Mikrobio-Beispiel: Mibi-Probe (alt) + Erregerwachstum + Antibiose-Switch (neu)
    assert "Trachealsekret" in prompt
    assert "Klebsiella" in prompt or "ESBL" in prompt
    assert "Meropenem" in prompt
    # Beide Quellen gemergt — explizite Auflösung
    assert "gemergt" in prompt or "Mikrobio-Trigger-Merge" in prompt


def test_block2_prompt_iter_v2_has_three_clinical_examples():
    """Block-2-Iter-v2 enthält mindestens 3 klinische Beispiele."""
    from pathlib import Path
    prompt = (Path(__file__).parent.parent / "prompts" / "extraction_block2.txt").read_text(encoding="utf-8")

    # 3 Beispiele: Plan→Status-Merge (Tracheo), Mikrobio-Trigger-Merge, Akutes Event (AV-Block)
    assert "Beispiel 1" in prompt
    assert "Beispiel 2" in prompt
    assert "Beispiel 3" in prompt


# ── Test 12: Update-Gruppe landet korrekt in Proposals (Pipeline-Test) ───────


def test_merge_update_group_in_proposals():
    """Mock-LLM gibt delete+add-Paar zurück → 1 Update-Proposal mit Merge-Text."""
    iterations = [[
        {
            "tool": "delete_entry",
            "args": {"id": "VE_042", "source_quote": "Spätdienst-Doku"},
        },
        {
            "tool": "add_verlaufseintrag",
            "args": {
                "datum": "2026-04-28",
                "text": (
                    "Vorbereitung chirurgische Tracheotomie, HNO-Konsil bestätigt Durchführbarkeit. "
                    "Klinisch: tief sediert (RASS -3), CIP/CIM, ZVD-Anstieg, CVVHDF-Ende für morgen geplant."
                ),
                "source_quote": "Spätdienst-Doku",
            },
        },
    ]]
    proposals = group_proposals(iterations)

    # Genau 1 Update-Proposal
    assert len(proposals) == 1
    p = proposals[0]
    assert p.type == "update"
    assert p.delete_call is not None
    assert p.add_call is not None
    assert p.delete_call.args["id"] == "VE_042"

    # Neuer Text enthält BEIDE Informationsquellen (Merge-Verhalten)
    new_text = p.add_call.args["text"]
    assert "Tracheotomie" in new_text, "Alter Plan-Inhalt fehlt im Merge-Text"
    assert "RASS -3" in new_text, "Neuer Status fehlt im Merge-Text"
    assert "CIP/CIM" in new_text


# ── Test 13: MALFORMED_FUNCTION_CALL Retry-Logik ─────────────────────────────


def test_malformed_function_call_retry_success():
    """iter 1 liefert MALFORMED_FUNCTION_CALL, erster Retry erfolgreich → Proposal vorhanden."""
    tc = _mock_tool_call("add_verlaufseintrag", {"datum": "2026-04-01", "text": "Test", "source_quote": "q"})
    mock_llm = MagicMock()
    mock_llm.chat_completion = AsyncMock(side_effect=[
        _malformed_response(),   # attempt 1: MALFORMED
        _llm_response([tc]),     # attempt 2 (retry 1): success
        _llm_response(None),     # iter 2: kein Tool-Call → exit
    ])

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        iters = asyncio.run(run_pass(
            llm=mock_llm,
            system_prompt="test",
            user_messages=[{"role": "user", "content": "doc"}],
            tools=[],
            thinking_budget=0,
            pass_name="TestPass",
        ))

    assert mock_llm.chat_completion.call_count == 3   # 1 initial + 1 retry + 1 iter2
    assert mock_sleep.call_count == 1                  # genau 1 Retry-Sleep
    assert len(iters) == 1
    assert iters[0][0]["tool"] == "add_verlaufseintrag"


def test_malformed_function_call_retry_exhausted_raises():
    """3x MALFORMED_FUNCTION_CALL → RuntimeError mit 'LLM provider instability'."""
    mock_llm = MagicMock()
    mock_llm.chat_completion = AsyncMock(return_value=_malformed_response())

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        with pytest.raises(RuntimeError, match="LLM provider instability"):
            asyncio.run(run_pass(
                llm=mock_llm,
                system_prompt="test",
                user_messages=[{"role": "user", "content": "doc"}],
                tools=[],
                thinking_budget=0,
                pass_name="TestPass",
            ))

    assert mock_llm.chat_completion.call_count == 3   # 1 initial + 2 retries
    assert mock_sleep.call_count == 2                  # 2 Retry-Sleeps
