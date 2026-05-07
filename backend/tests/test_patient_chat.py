"""Snapshot-Test: build_system_prompt byte-identisch vor und nach Prompt-Extraktion."""
import hashlib
from datetime import date

from models.patient import Patient, Stammdaten
from workflows.patient_chat.orchestrator import build_system_prompt

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
