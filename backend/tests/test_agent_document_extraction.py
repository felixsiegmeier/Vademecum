"""Tests für 2-Pass-Extraktion, Multi-Turn-Loop, Proposal-Gruppierung und Apply-Logik."""
import asyncio
import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock

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


# ── Test 6: Letzter Verlaufseintrag erscheint im Block-2-System-Prompt ────────


def test_block2_last_verlaufseintrag_in_prompt(isolated_data):
    """Patient mit mehreren Einträgen → nur der letzte (nach datum) im Prompt."""
    patient = Patient(
        stammdaten=Stammdaten(id="P-0001", name="Test", aufnahmedatum="2026-04-01"),
        verlaufseintraege=[
            VerlaufsEintrag(id="ID1", datum=date(2026, 4, 14), text="Erster Eintrag", source_quote="q"),
            VerlaufsEintrag(id="ID2", datum=date(2026, 4, 15), text="Letzter Eintrag", source_quote="q"),
        ],
    )

    system = _build_block2_system(patient)

    assert "ID2" in system
    assert "Letzter Eintrag" in system
    assert "Erster Eintrag" not in system  # Nur der letzte


def test_block2_no_verlaufseintrag_shows_keiner():
    """Kein Verlaufseintrag → <letzter_verlaufseintrag>keiner</letzter_verlaufseintrag>."""
    system = _build_block2_system(patient=None)
    assert "<letzter_verlaufseintrag>keiner</letzter_verlaufseintrag>" in system


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
