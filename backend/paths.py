import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # PyInstaller bundle: code/assets live in _MEIPASS, user data next to exe
    BACKEND_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    USER_DATA_DIR = Path(sys.executable).parent / "data"
else:
    BACKEND_DIR = Path(__file__).parent
    USER_DATA_DIR = BACKEND_DIR / "data"

FRONTEND_DIST_DIR = BACKEND_DIR / "frontend_dist"
