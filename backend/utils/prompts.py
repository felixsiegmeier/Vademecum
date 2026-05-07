"""Prompt-Lade-Utility: Frontmatter-Stripping und Validierung.

Cacht per aufgelöstem Pfad (modul-global). In Tests keine Konflikte,
da tmp_path eindeutige Pfade liefert.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

_PROMPT_CACHE: dict[Path, str] = {}


class PromptFrontmatter(BaseModel):
    model_config = ConfigDict(extra="allow")

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

    - Erwartet <name>.md mit YAML-Frontmatter.
    - Validiert Pflichtfelder und strippt Frontmatter.
    - Cacht pro aufgelöstem Pfad.
    """
    stem = name.rsplit(".", 1)[0] if "." in name else name
    resolved = prompts_dir / f"{stem}.md"

    if resolved in _PROMPT_CACHE:
        return _PROMPT_CACHE[resolved]

    raw = resolved.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise ValueError(f"Prompt '{resolved}' hat kein Frontmatter")
    result = _parse_and_validate(raw)

    _PROMPT_CACHE[resolved] = result
    return result
