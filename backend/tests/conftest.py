import pytest
import storage

@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Leitet alle Storage-Pfade in ein tmp-Verzeichnis um."""
    patients = tmp_path / "patients"
    meilensteine = tmp_path / "meilensteine"
    briefe = tmp_path / "briefe"
    patients.mkdir()
    meilensteine.mkdir()
    briefe.mkdir()
    monkeypatch.setattr(storage, "PATIENTS_DIR", patients)
    monkeypatch.setattr(storage, "MEILENSTEINE_DIR", meilensteine)
    monkeypatch.setattr(storage, "BRIEFE_DIR", briefe)
    return tmp_path