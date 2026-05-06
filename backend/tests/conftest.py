import pytest
import brief_storage
import learning_storage
import storage

@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Leitet alle Storage-Pfade in ein tmp-Verzeichnis um."""
    patients = tmp_path / "patients"
    meilensteine = tmp_path / "meilensteine"
    briefe = tmp_path / "briefe"
    learnings = tmp_path / "learnings"
    briefs = tmp_path / "briefs"
    patients.mkdir()
    meilensteine.mkdir()
    briefe.mkdir()
    learnings.mkdir()
    briefs.mkdir()
    monkeypatch.setattr(storage, "PATIENTS_DIR", patients)
    monkeypatch.setattr(storage, "MEILENSTEINE_DIR", meilensteine)
    monkeypatch.setattr(storage, "BRIEFE_DIR", briefe)
    monkeypatch.setattr(learning_storage, "LEARNINGS_DIR", learnings)
    monkeypatch.setattr(brief_storage, "BRIEFS_DIR", briefs)
    return tmp_path