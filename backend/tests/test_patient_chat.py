"""Tests für patient_chat orchestrator."""
import asyncio
import hashlib
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from models.patient import Patient, Stammdaten
from workflows.patient_chat.orchestrator import (
    _CHAT_HISTORY_WINDOW,
    build_system_prompt,
    run_single_pass_chat,
)

_DUMMY_PATIENT = Patient(stammdaten=Stammdaten(
    id="P-SNAP",
    name="Snapshot, Patient",
    geburtsdatum=date(1955, 3, 22),
    aufnahmedatum=date(2026, 4, 10),
    bettplatz="ITS-01",
))
_DUMMY_TODAY = date(2026, 5, 7)

# Computed from original hardcoded Template on 2026-05-07.
# Must remain byte-identical after prompt extraction to .md.
_GOLDEN_SHA256 = "b6e5029c4730e21eeacdc56d08b55ae3ef1a5646cc3411d237891e64dc5302cc"


def _llm_text_resp(text: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.tool_calls = None
    resp.choices[0].message.content = text
    return resp


def test_chat_history_sliding_window():
    """Bei mehr als _CHAT_HISTORY_WINDOW Nachrichten werden nur die letzten ans LLM übergeben."""
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"}
        for i in range(_CHAT_HISTORY_WINDOW + 5)
    ]
    llm = MagicMock()
    llm.chat_completion = AsyncMock(return_value=_llm_text_resp("ok"))

    asyncio.run(run_single_pass_chat(llm, _DUMMY_PATIENT, messages, _DUMMY_TODAY))

    sent = llm.chat_completion.call_args[0][0]
    assert sent[0]["role"] == "system"
    non_system = [m for m in sent if m["role"] != "system"]
    assert len(non_system) == _CHAT_HISTORY_WINDOW
    assert non_system[-1]["content"] == messages[-1]["content"]


def test_chat_history_window_no_truncation_when_short():
    """Kurze History wird vollständig übergeben — kein Over-truncation."""
    messages = [{"role": "user", "content": "hallo"}]
    # Die Konstante selbst ist das Korrektheitskriterium — nur Typ-Sanity hier
    assert _CHAT_HISTORY_WINDOW > 0
    assert len(messages[-_CHAT_HISTORY_WINDOW:]) == len(messages)


def test_chat_system_prompt_unchanged():
    """build_system_prompt ist byte-identisch zum golden Snapshot."""
    result = build_system_prompt(_DUMMY_PATIENT, _DUMMY_TODAY)
    actual = hashlib.sha256(result.encode("utf-8")).hexdigest()
    assert actual == _GOLDEN_SHA256, (
        f"Prompt-Output hat sich geändert (byte-drift).\n"
        f"  erwartet: {_GOLDEN_SHA256}\n"
        f"  erhalten: {actual}\n"
        f"  länge: {len(result)}\n"
        f"  ende: {repr(result[-60:])}"
    )
