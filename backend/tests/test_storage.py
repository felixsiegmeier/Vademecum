from models.patient import Patient
import storage
from storage import brief_storage

# ---- Patienten-Tests: Speichern, Laden, Hash, Löschen --------------------------------------------------

def _make_minimal_patient():
    return Patient(
        stammdaten={
            "id": "P-TEST",
            "name": "Test, Patient",
            "aufnahmedatum": "2026-04-28",
        },
    )

def test_save_load_roundtrip(isolated_data):
    p = _make_minimal_patient()
    storage.save_patient(p)
    loaded = storage.load_patient("P-TEST")
    assert loaded.stammdaten.name == "Test, Patient"
    assert loaded.stammdaten.aktiv is True

def test_anamnese_field_persists(isolated_data):
    p = _make_minimal_patient()
    p.anamnese = "Test-Anamnese mit Umlauten: äöüß"
    storage.save_patient(p)
    loaded = storage.load_patient("P-TEST")
    assert loaded.anamnese == "Test-Anamnese mit Umlauten: äöüß"

def test_yaml_hash_stable(isolated_data):
    p = _make_minimal_patient()
    storage.save_patient(p)
    h1 = storage.patient_yaml_hash("P-TEST")
    h2 = storage.patient_yaml_hash("P-TEST")
    assert h1 == h2

def test_yaml_hash_changes_on_edit(isolated_data):
    p = _make_minimal_patient()
    storage.save_patient(p)
    h1 = storage.patient_yaml_hash("P-TEST")
    p.anamnese = "Neue Anamnese"
    storage.save_patient(p)
    h2 = storage.patient_yaml_hash("P-TEST")
    assert h1 != h2

def test_delete_patient_removes_yaml(isolated_data):
    p = _make_minimal_patient()
    storage.save_patient(p)
    assert (isolated_data / "patienten" / "P-TEST.yml").exists()
    storage.delete_patient("P-TEST")
    assert not (isolated_data / "patienten" / "P-TEST.yml").exists()

# ---- Meilensteine und Briefe löschen --------------------------------------------

def test_delete_patient_removes_meilensteine(isolated_data):
    p = _make_minimal_patient()
    storage.save_patient(p)
    (isolated_data / "meilensteine" / "P-TEST.md").write_text("Test Meilenstein")
    (isolated_data / "meilensteine" / "P-TEST.meta.json").write_text("{}")
    assert (isolated_data / "meilensteine" / "P-TEST.md").exists()
    storage.delete_patient("P-TEST")
    assert not (isolated_data / "meilensteine" / "P-TEST.md").exists()
    assert not (isolated_data / "meilensteine" / "P-TEST.meta.json").exists()

def test_delete_patient_removes_brief(isolated_data):
    p = _make_minimal_patient()
    storage.save_patient(p)
    brief_storage.save_brief("P-TEST", {"diagnosen": "Inhalt"})
    assert (isolated_data / "briefs" / "P-TEST.yml").exists()
    storage.delete_patient("P-TEST")
    assert not (isolated_data / "briefs" / "P-TEST.yml").exists()

def test_delete_meilenstein_removes_files(isolated_data):
    p = _make_minimal_patient()
    storage.save_patient(p)
    storage.save_meilenstein("P-TEST", "Test-Inhalt", {"yaml_hash": "abc", "generated_at": "2026-04-28"})
    assert (isolated_data / "meilensteine" / "P-TEST.md").exists()
    assert (isolated_data / "meilensteine" / "P-TEST.meta.json").exists()
    storage.delete_meilenstein("P-TEST")
    assert not (isolated_data / "meilensteine" / "P-TEST.md").exists()
    assert not (isolated_data / "meilensteine" / "P-TEST.meta.json").exists()

def test_delete_brief_removes_file(isolated_data):
    p = _make_minimal_patient()
    storage.save_patient(p)
    brief_storage.save_brief("P-TEST", {"diagnosen": "Inhalt"})
    assert (isolated_data / "briefs" / "P-TEST.yml").exists()
    brief_storage.delete_brief("P-TEST")
    assert not (isolated_data / "briefs" / "P-TEST.yml").exists()