import os
from pathlib import Path

from models.chat import ChatHistory

_CHAT_DIR = Path(__file__).parent.parent / "data" / "chat"


def _path(patient_id: str) -> Path:
    return _CHAT_DIR / f"{patient_id}.json"


def load_chat(patient_id: str) -> ChatHistory:
    path = _path(patient_id)
    if not path.exists():
        return ChatHistory()
    with path.open(encoding="utf-8") as f:
        return ChatHistory.model_validate_json(f.read())


def save_chat(patient_id: str, history: ChatHistory) -> None:
    _CHAT_DIR.mkdir(parents=True, exist_ok=True)
    path = _path(patient_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(history.model_dump_json(), encoding="utf-8")
    os.replace(tmp, path)


def delete_chat(patient_id: str) -> None:
    path = _path(patient_id)
    if path.exists():
        path.unlink()
