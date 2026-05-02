import pytest

import storage
from agent_tools import (
    TOOL_FUNCTIONS,
    TOOL_SCHEMAS,
    add_befund,
    add_prozedur,
    add_therapie,
    add_verlaufseintrag,
    delete_entry,
    generate_ulid,
)
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
    # 7 add + 6 update + 1 delete = 14
    assert len(TOOL_SCHEMAS) == 14
    assert len(TOOL_FUNCTIONS) == 14


# ── Funktion-Akzeptiert-source_quote-Tests ────────────────────────────────────

_MINIMAL_ARGS: dict[str, dict] = {
    "add_behandlungsdiagnose": {"text": "Test-Diagnose", "datum": None},
    "add_verlaufsdiagnose": {"text": "Test-Verlaufsdiagnose", "datum": "2026-04-15"},
    "add_vorbekannte_diagnose": {"text": "Test-vorbekannt"},
    "add_prozedur": {"datum": "2026-04-15", "text": "Test-Prozedur"},
    "add_befund": {"datum": "2026-04-15", "art": "TTE", "text": "Test-Befund"},
    "add_therapie": {
        "kategorie": "antimikrobiell",
        "bezeichnung": "Test-AB",
        "beginn": "2026-04-15",
        "ende": None,
        "indikation": "V.a. Pneumonie",
    },
    "add_verlaufseintrag": {"datum": "2026-04-15", "text": "Test-Verlauf"},
    "update_anamnese": {"text": "Test-Anamnese"},
    "update_therapieziel": {"text": "Test-Therapieziel"},
    "update_status": {"aktiv": True},
    "update_bettplatz": {"bettplatz": "ITS-1 / Bett 3"},
    "update_verlegungsziel": {"verlegungsziel": "IMC"},
    "update_stammdaten": {"feld": "name", "wert": "Test Name"},
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
    args = _MINIMAL_ARGS[tool_name]
    result = fn(patient_id="P-0001", **args, source_quote="test-zitat")
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
        patient_id="P-0001",
        datum="2026-04-15",
        art="TTE",
        text="LV-EF 45%",
        source_quote="LV-EF visuell 45%",
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
    add_befund(patient_id="P-0001", datum="2026-04-15", art="TTE", text="A", source_quote="q1")
    add_befund(patient_id="P-0001", datum="2026-04-16", art="CT", text="B", source_quote="q2")
    p = storage.load_patient("P-0001")
    assert p.befunde[0].id != p.befunde[1].id


# ── Persistenz-Test (source_quote) ────────────────────────────────────────────

def test_add_befund_persists_source_quote(isolated_data):
    _make_test_patient()
    add_befund(
        patient_id="P-0001",
        datum="2026-04-15",
        art="TTE",
        text="LV-EF 45%",
        source_quote="LV-EF visuell 45%",
    )
    p = storage.load_patient("P-0001")
    assert p.befunde[0].source_quote == "LV-EF visuell 45%"


def test_update_anamnese_ignores_source_quote(isolated_data):
    _make_test_patient()
    from agent_tools import update_anamnese
    update_anamnese(
        patient_id="P-0001",
        text="Aufnahme bei dekomp. HI",
        source_quote="zitat-wird-ignoriert",
    )
    p = storage.load_patient("P-0001")
    assert p.anamnese == "Aufnahme bei dekomp. HI"


# ── delete_entry-Tests ────────────────────────────────────────────────────────

def test_delete_entry_across_lists(isolated_data):
    _make_test_patient()
    proz_id = add_prozedur(
        patient_id="P-0001", datum="2026-04-15", text="CABG 3-fach", source_quote="OP-Bericht"
    )["id"]
    ther_id = add_therapie(
        patient_id="P-0001",
        kategorie="antimikrobiell",
        bezeichnung="Pip/Taz",
        beginn="2026-04-15",
        indikation="V.a. Pneumonie",
        source_quote="Antibiose laut Visite",
    )["id"]
    verl_id = add_verlaufseintrag(
        patient_id="P-0001", datum="2026-04-15", text="Tagesstatus stabil", source_quote="Visite"
    )["id"]

    for entry_id in (proz_id, ther_id, verl_id):
        result = delete_entry(patient_id="P-0001", id=entry_id, source_quote="korrektur")
        assert result["ok"] is True, f"delete für {entry_id} fehlgeschlagen: {result}"

    p = storage.load_patient("P-0001")
    assert p.prozeduren == []
    assert p.therapien == []
    assert p.verlaufseintraege == []


def test_delete_entry_unknown_id_errors(isolated_data):
    _make_test_patient()
    result = delete_entry(patient_id="P-0001", id="01ABCDEFGHJKMNPQRSTVWXYZ12", source_quote="x")
    assert result["ok"] is False
    assert "id=" in result["error"]


# ── Therapie-Kategorie-Validierung ────────────────────────────────────────────

@pytest.mark.parametrize("kategorie", [
    "antimikrobiell", "operativ", "medikamentös", "konservativ", "sonstiges",
])
def test_add_therapie_accepts_all_categories(kategorie, isolated_data):
    _make_test_patient()
    result = add_therapie(
        patient_id="P-0001",
        kategorie=kategorie,
        bezeichnung=f"Test-{kategorie}",
        beginn="2026-04-15",
        indikation="Test-Indikation",
        source_quote="test-zitat",
    )
    assert result["ok"] is True, f"{kategorie}: {result}"
    p = storage.load_patient("P-0001")
    assert p.therapien[-1].kategorie == kategorie


def test_add_therapie_rejects_invalid_category(isolated_data):
    _make_test_patient()
    result = add_therapie(
        patient_id="P-0001",
        kategorie="quatsch",
        bezeichnung="Test",
        beginn="2026-04-15",
        indikation="Test",
        source_quote="test",
    )
    assert result["ok"] is False
