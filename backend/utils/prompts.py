"""Prompt-Lade-Utility: Frontmatter-Stripping und Validierung.

Cacht per aufgelöstem Pfad (modul-global). In Tests keine Konflikte,
da tmp_path eindeutige Pfade liefert.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator

_PROMPT_CACHE: dict[Path, str] = {}


class PromptFrontmatter(BaseModel):
    id: str
    version: str        # ISO-Datum: "2026-05-07" oder "2026-05-07-2"
    model: str          # bindend — Orchestrator liest Modell aus Frontmatter
    role: str
    inputs: list[str]

    @field_validator("version", mode="before")
    @classmethod
    def coerce_version(cls, v: object) -> str:
        # YAML parst unquotierte Datumsangaben als datetime.date → in str umwandeln.
        return str(v)


def _parse_and_validate(raw: str) -> str:
    """Parst Frontmatter, validiert Pflichtfelder, gibt Body zurück."""
    _, fm_block, body = raw.split("---", 2)
    fm = yaml.safe_load(fm_block) or {}
    PromptFrontmatter.model_validate(fm)
    return body.lstrip("\n")


def get_prompt(name: str, prompts_dir: Path) -> str:
    """Lädt Prompt-Text aus prompts_dir.

    - Bevorzugt <stem>.md über <stem>.txt (Backwards-Compat).
    - Wenn Frontmatter vorhanden (Datei beginnt mit ---): validiert und strippt es.
    - Kein Frontmatter → Raw-Text unverändert.
    - Cacht pro aufgelöstem Pfad.
    """
    stem = name.rsplit(".", 1)[0] if "." in name else name
    md_path = prompts_dir / f"{stem}.md"
    resolved = md_path if md_path.exists() else (prompts_dir / name)

    if resolved in _PROMPT_CACHE:
        return _PROMPT_CACHE[resolved]

    raw = resolved.read_text(encoding="utf-8")
    result = _parse_and_validate(raw) if raw.startswith("---") else raw

    _PROMPT_CACHE[resolved] = result
    return result
