from pathlib import Path

_CURATE_PROMPTS_DIR = Path(__file__).parent / "03_curate" / "prompts"


def validate_curate_variant(v: str) -> str:
    """Prüft ob curate_variant einer existierenden Curate-Prompt-Datei entspricht."""
    available = [p.stem for p in _CURATE_PROMPTS_DIR.glob("*.md") if p.stem != "shared"]
    if v not in available:
        raise ValueError(f"curate_variant '{v}' unbekannt; verfügbar: {available}")
    return v
