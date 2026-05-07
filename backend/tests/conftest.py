import pytest
import brief_storage
import learning_storage
import storage

@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Leitet alle Storage-Pfade in ein tmp-Verzeichnis um."""
    patients = tmp_path / "patienten"
    meilensteine = tmp_path / "meilensteine"
    briefe = tmp_path / "briefe"
    lernlog_base = tmp_path / "workflows"
    snapshots = tmp_path / "learning_snapshots"
    briefs = tmp_path / "briefs"
    patients.mkdir()
    meilensteine.mkdir()
    briefe.mkdir()
    lernlog_base.mkdir()
    snapshots.mkdir()
    briefs.mkdir()
    monkeypatch.setattr(storage, "PATIENTS_DIR", patients)
    monkeypatch.setattr(storage, "MEILENSTEINE_DIR", meilensteine)
    monkeypatch.setattr(storage, "BRIEFE_DIR", briefe)
    monkeypatch.setattr(learning_storage, "LERNLOG_BASE", lernlog_base)
    monkeypatch.setattr(learning_storage, "SNAPSHOTS_DIR", snapshots)
    monkeypatch.setattr(brief_storage, "BRIEFS_DIR", briefs)
    return tmp_path