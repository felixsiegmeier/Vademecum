import pytest

import storage
from tools.patient_tools import (
    TOOL_ARGS,
    TOOL_FUNCTIONS,
    TOOL_SCHEMAS,
    AddBefundArgs,
    AddTherapieArgs,
    AddVerlaufseintragArgs,
    add_befund,
    add_therapie,
    add_verlaufseintrag,
    delete_entry,
    update_anamnese,
    DeleteEntryArgs,
    UpdateAnamneseArgs,
)
from utils.ulid import generate_ulid
from models.patient import Patient, Stammdaten


# ── Schema-Tests ──────────────────────────────────────────────────────────────

def test_strict_mode_set_on_all_tool_schemas():
    for schema in TOOL_SCHEMAS:
        name = schema["function"]["name"]
        assert schema["function"]["strict"] is True, f"{name}: strict nicht True"
        params = schema["function"]["parameters"]
        assert params["additionalProperties"] is False, f"{name}: additionalProperties nicht false"
        # OpenAI strict mode: alle properties müssen in required stehen
        props = set(params["properties"].keys())
        required = set(params["required"])
        assert props == required, f"{name}: properties {props} != required {required}"


def test_add_tools_have_source_quote_required():
    add_tools = [s for s in TOOL_SCHEMAS if s["function"]["name"].startswith("add_")]
    for schema in add_tools:
        name = schema["function"]["name"]
        props = schema["function"]["parameters"]["properties"]
        required = schema["function"]["parameters"]["required"]
        assert "source_quote" in props, f"{name}: source_quote fehlt in properties"
        assert "source_quote" in required, f"{name}: source_quote fehlt in required"


def test_tool_count():
    # 6 add + 5 update (update_status in TOOL_FUNCTIONS only) + 1 delete = 12 schemas; 13 functions
    assert len(TOOL_SCHEMAS) == 12
    assert len(TOOL_FUNCTIONS) == 13


def test_no_add_prozedur_in_tools():
    assert "add_prozedur" not in TOOL_FUNCTIONS
    tool_names = [s["function"]["name"] for s in TOOL_SCHEMAS]
    assert "add_prozedur" not in tool_names


def test_add_therapie_schema_has_9_categories():
    schema = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == "add_therapie")
    enum_values = schema["function"]["parameters"]["properties"]["kategorie"]["enum"]
    expected = {
        "operativ", "MCS", "RRT", "respiratorisch", "interventionell",
        "antimikrobiell", "medikamentös", "bedside", "sonstiges",
    }
    assert set(enum_values) == expected


def test_add_therapie_schema_includes_bedside():
    schema = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == "add_therapie")
    enum_values = schema["function"]["parameters"]["properties"]["kategorie"]["enum"]
    assert "bedside" in enum_values


# ── Funktion-Akzeptiert-source_quote-Tests ────────────────────────────────────

_MINIMAL_ARGS: dict[str, dict] = {
    "add_behandlungsdiagnose": {"text": "Test-Diagnose", "datum": None, "source_quote": "test-zitat"},
    "add_verlaufsdiagnose": {"text": "Test-Verlaufsdiagnose", "datum": "2026-04-15", "source_quote": "test-zitat"},
    "add_vorbekannte_diagnose": {"text": "Test-vorbekannt", "source_quote": "test-zitat"},
    "add_befund": {"datum": "2026-04-15", "art": "TTE", "text": "Test-Befund", "source_quote": "test-zitat"},
    "add_therapie": {
        "kategorie": "antimikrobiell",
        "bezeichnung": "Test-AB",
        "beginn": "2026-04-15",
        "ende": None,
        "indikation": "V.a. Pneumonie",
        "source_quote": "test-zitat",
    },
    "add_verlaufseintrag": {"datum": "2026-04-15", "text": "Test-Verlauf", "source_quote": "test-zitat"},
    "update_anamnese": {"text": "Test-Anamnese", "source_quote": "test-zitat"},
    "update_therapieziel": {"text": "Test-Therapieziel", "source_quote": "test-zitat"},
    "update_status": {"aktiv": True, "source_quote": "test-zitat"},
    "update_bettplatz": {"bettplatz": "ITS-1 / Bett 3", "source_quote": "test-zitat"},
    "update_verlegungsziel": {"verlegungsziel": "IMC", "source_quote": "test-zitat"},
    "update_stammdaten": {"feld": "name", "wert": "Test Name", "source_quote": "test-zitat"},
}


def _make_test_patient():
    p = Patient(
        stammdaten=Stammdaten(id="P-0001", name="Test", aufnahmedatum="2026-01-01"),
    )
    storage.save_patient(p)


@pytest.mark.parametrize("tool_name", [n for n in TOOL_FUNCTIONS if n != "delete_entry"])
def test_tool_function_accepts_source_quote(tool_name, isolated_data):
    _make_test_patient()
    fn = TOOL_FUNCTIONS[tool_name]
    args_class = TOOL_ARGS[tool_name]
    args = args_class.model_validate(_MINIMAL_ARGS[tool_name])
    result = fn("P-0001", args)
    assert result["ok"] is True, f"{tool_name} failed: {result}"


# ── ULID-Tests ────────────────────────────────────────────────────────────────

_CROCKFORD = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")


def test_generate_ulid_format():
    ulid = generate_ulid()
    assert len(ulid) == 26
    assert all(c in _CROCKFORD for c in ulid), f"Ungültige Zeichen in ULID: {ulid}"


def test_two_consecutive_ulids_differ():
    ids = {generate_ulid() for _ in range(100)}
    assert len(ids) == 100  # alle eindeutig


def test_add_befund_assigns_ulid(isolated_data):
    _make_test_patient()
    result = add_befund(
        "P-0001",
        AddBefundArgs(datum="2026-04-15", art="TTE", text="LV-EF 45%", source_quote="LV-EF visuell 45%"),
    )
    assert result["ok"] is True
    p = storage.load_patient("P-0001")
    assert len(p.befunde) == 1
    bid = p.befunde[0].id
    assert len(bid) == 26
    assert all(c in _CROCKFORD for c in bid)
    assert result["id"] == bid


def test_two_adds_get_different_ids(isolated_data):
    _make_test_patient()
    add_befund("P-0001", AddBefundArgs(datum="2026-04-15", art="TTE", text="A", source_quote="q1"))
    add_befund("P-0001", AddBefundArgs(datum="2026-04-16", art="CT", text="B", source_quote="q2"))
    p = storage.load_patient("P-0001")
    assert p.befunde[0].id != p.befunde[1].id


# ── Persistenz-Test (source_quote) ────────────────────────────────────────────

def test_add_befund_persists_source_quote(isolated_data):
    _make_test_patient()
    add_befund(
        "P-0001",
        AddBefundArgs(datum="2026-04-15", art="TTE", text="LV-EF 45%", source_quote="LV-EF visuell 45%"),
    )
    p = storage.load_patient("P-0001")
    assert p.befunde[0].source_quote == "LV-EF visuell 45%"


def test_update_anamnese_ignores_source_quote(isolated_data):
    _make_test_patient()
    update_anamnese(
        "P-0001",
        UpdateAnamneseArgs(text="Aufnahme bei dekomp. HI", source_quote="zitat-wird-ignoriert"),
    )
    p = storage.load_patient("P-0001")
    assert p.anamnese == "Aufnahme bei dekomp. HI"


# ── delete_entry-Tests ────────────────────────────────────────────────────────

def test_delete_entry_across_lists(isolated_data):
    _make_test_patient()
    ther_id = add_therapie(
        "P-0001",
        AddTherapieArgs(
            kategorie="operativ",
            bezeichnung="CABG 3-fach",
            beginn="2026-04-15",
            ende="2026-04-15",
            indikation=None,
            source_quote="OP-Bericht",
        ),
    )["id"]
    ther2_id = add_therapie(
        "P-0001",
        AddTherapieArgs(
            kategorie="antimikrobiell",
            bezeichnung="Pip/Taz",
            beginn="2026-04-15",
            ende=None,
            indikation="V.a. Pneumonie",
            source_quote="Antibiose laut Visite",
        ),
    )["id"]
    verl_id = add_verlaufseintrag(
        "P-0001",
        AddVerlaufseintragArgs(datum="2026-04-15", text="Tagesstatus stabil", source_quote="Visite"),
    )["id"]

    for entry_id in (ther_id, ther2_id, verl_id):
        result = delete_entry("P-0001", DeleteEntryArgs(id=entry_id, source_quote="korrektur"))
        assert result["ok"] is True, f"delete für {entry_id} fehlgeschlagen: {result}"

    p = storage.load_patient("P-0001")
    assert p.therapien == []
    assert p.verlaufseintraege == []


def test_delete_entry_unknown_id_errors(isolated_data):
    _make_test_patient()
    result = delete_entry("P-0001", DeleteEntryArgs(id="01ABCDEFGHJKMNPQRSTVWXYZ12", source_quote="x"))
    assert result["ok"] is False
    assert "id=" in result["error"]


# ── Therapie-Kategorie-Validierung ────────────────────────────────────────────

@pytest.mark.parametrize("kategorie", [
    "operativ", "MCS", "RRT", "respiratorisch",
    "interventionell", "antimikrobiell", "medikamentös", "bedside", "sonstiges",
])
def test_add_therapie_accepts_all_categories(kategorie, isolated_data):
    _make_test_patient()
    result = add_therapie(
        "P-0001",
        AddTherapieArgs(
            kategorie=kategorie,
            bezeichnung=f"Test-{kategorie}",
            beginn="2026-04-15",
            ende=None,
            indikation="Test-Indikation",
            source_quote="test-zitat",
        ),
    )
    assert result["ok"] is True, f"{kategorie}: {result}"
    p = storage.load_patient("P-0001")
    assert p.therapien[-1].kategorie == kategorie


def test_add_therapie_rejects_invalid_category(isolated_data):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AddTherapieArgs(
            kategorie="quatsch",
            bezeichnung="Test",
            beginn="2026-04-15",
            ende=None,
            indikation="Test",
            source_quote="test",
        )


# ── Neue Therapie-Tests: Event-Pattern und laufende Therapie ─────────────────

def test_add_therapie_mcs_event_pattern(isolated_data):
    """MCS-Kategorie mit beginn=ende (einmaliges Event-Pattern, z.B. Impella-Anlage)."""
    _make_test_patient()
    result = add_therapie(
        "P-0001",
        AddTherapieArgs(
            kategorie="MCS",
            bezeichnung="Impella 5.5 via A. axillaris",
            beginn="2026-04-04",
            ende="2026-04-04",
            indikation="Postkardiotomie-Schock",
            source_quote="Impella 5.5 via A. axillaris rechts am 04.04.",
        ),
    )
    assert result["ok"] is True
    p = storage.load_patient("P-0001")
    t = p.therapien[-1]
    assert t.kategorie == "MCS"
    assert str(t.beginn) == "2026-04-04"
    assert str(t.ende) == "2026-04-04"


def test_add_therapie_antimikrobiell_running(isolated_data):
    """Antimikrobiell mit ende=null (laufende Therapie)."""
    _make_test_patient()
    result = add_therapie(
        "P-0001",
        AddTherapieArgs(
            kategorie="antimikrobiell",
            bezeichnung="Meropenem",
            beginn="2026-04-14",
            ende=None,
            indikation="Nosokomiale Pneumonie",
            source_quote="Meropenem seit 14.04., noch laufend",
        ),
    )
    assert result["ok"] is True
    p = storage.load_patient("P-0001")
    t = p.therapien[-1]
    assert t.kategorie == "antimikrobiell"
    assert str(t.beginn) == "2026-04-14"
    assert t.ende is None


def test_add_therapie_bedside_event_pattern(isolated_data):
    """`bedside`-Kategorie für Bedside-Eingriffe (PAK-Anlage, Bronchoskopie etc.) als Einzelevent."""
    _make_test_patient()
    result = add_therapie(
        "P-0001",
        AddTherapieArgs(
            kategorie="bedside",
            bezeichnung="Bronchoskopie",
            beginn="2026-04-23",
            ende="2026-04-23",
            indikation="erhöhte Sekretlast",
            source_quote="Bronchoskopie 23.04. bei erhöhter Sekretlast",
        ),
    )
    assert result["ok"] is True
    p = storage.load_patient("P-0001")
    t = p.therapien[-1]
    assert t.kategorie == "bedside"
    assert str(t.beginn) == "2026-04-23"
    assert str(t.ende) == "2026-04-23"


def test_add_therapie_indikation_optional(isolated_data):
    """indikation darf null sein."""
    _make_test_patient()
    result = add_therapie(
        "P-0001",
        AddTherapieArgs(
            kategorie="operativ",
            bezeichnung="CABG 3-fach",
            beginn="2026-04-04",
            ende="2026-04-04",
            indikation=None,
            source_quote="CABG am 04.04.",
        ),
    )
    assert result["ok"] is True
    p = storage.load_patient("P-0001")
    assert p.therapien[-1].indikation is None


# ── Status-Tool-Removal ───────────────────────────────────────────────────────

def test_update_status_not_in_tool_schemas():
    """update_status darf nicht in TOOL_SCHEMAS stehen — Status ist UI-only."""
    from tools.patient_tools import TOOL_SCHEMAS
    names = [t["function"]["name"] for t in TOOL_SCHEMAS]
    assert "update_status" not in names, (
        "update_status muss aus TOOL_SCHEMAS entfernt sein — Status wird nur über UI-Toggle geändert."
    )


def test_extraction_block1_has_no_update_status_call():
    """extraction_block1.md darf keine update_status-Aufrufe enthalten."""
    from pathlib import Path
    text = (Path(__file__).parent.parent / "prompts" / "extraction_block1.md").read_text(encoding="utf-8")
    assert "update_status(aktiv" not in text, (
        "extraction_block1.md enthält noch einen update_status-Aufruf — muss entfernt werden."
    )
