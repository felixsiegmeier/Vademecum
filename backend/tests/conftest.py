import pytest
import storage.patients as _patients_store
from storage import brief_storage, learning_storage

@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Leitet alle Storage-Pfade in ein tmp-Verzeichnis um."""
    patients = tmp_path / "patienten"
    meilensteine = tmp_path / "meilensteine"
    lernlog_base = tmp_path / "workflows"
    snapshots = tmp_path / "learning_snapshots"
    briefs = tmp_path / "briefs"
    patients.mkdir()
    meilensteine.mkdir()
    lernlog_base.mkdir()
    snapshots.mkdir()
    briefs.mkdir()
    monkeypatch.setattr(_patients_store, "PATIENTS_DIR", patients)
    monkeypatch.setattr(_patients_store, "MEILENSTEINE_DIR", meilensteine)
    monkeypatch.setattr(learning_storage, "LERNLOG_BASE", lernlog_base)
    monkeypatch.setattr(learning_storage, "SNAPSHOTS_DIR", snapshots)
    monkeypatch.setattr(brief_storage, "BRIEFS_DIR", briefs)
    return tmp_path
