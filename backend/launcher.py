"""Windows-Launcher: API-Key-Dialog + Uvicorn-Start + Browser öffnen."""

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _get_or_ask_api_key() -> str:
    exe_dir = _exe_dir()
    env_file = exe_dir / ".env"

    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    return key

    import tkinter as tk
    from tkinter import simpledialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    key = simpledialog.askstring(
        "Arztbrief-App — Ersteinrichtung",
        "Bitte geben Sie Ihren OpenAI API-Key ein:\n(beginnt mit sk-...)",
        parent=root,
    )
    root.destroy()

    if not key or not key.strip():
        sys.exit(0)

    key = key.strip()
    env_file.write_text(f"OPENAI_API_KEY={key}\n", encoding="utf-8")
    return key


def _run_server() -> None:
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, log_level="error")


def main() -> None:
    # PyInstaller: bundle-Verzeichnis zum sys.path hinzufügen
    if getattr(sys, "frozen", False):
        bundle_dir = str(getattr(sys, "_MEIPASS", _exe_dir()))
        if bundle_dir not in sys.path:
            sys.path.insert(0, bundle_dir)

    api_key = _get_or_ask_api_key()
    os.environ["OPENAI_API_KEY"] = api_key

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    # Kurz warten bis FastAPI hochgefahren ist
    time.sleep(2)
    webbrowser.open("http://localhost:8000")

    server_thread.join()


if __name__ == "__main__":
    main()
