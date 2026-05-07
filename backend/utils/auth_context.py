"""Multi-User-Middleware: user_id-Auflösung.

MULTI_USER=false (default): gibt immer "default" zurück.
MULTI_USER=true: liest user_id aus dem Authorization-Header (Bearer-Token).

Vorbereitung für F15 — aktuell Single-User-App.
"""

import os


MULTI_USER = os.getenv("MULTI_USER", "false").lower() == "true"


def get_user_id(authorization: str | None = None) -> str:
    if not MULTI_USER:
        return "default"
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip() or "default"
    return "default"
