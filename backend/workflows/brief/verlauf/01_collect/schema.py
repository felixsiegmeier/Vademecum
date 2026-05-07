from pathlib import Path

from pydantic import BaseModel, field_validator

_CURATE_PROMPTS_DIR = Path(__file__).parent.parent / "03_curate" / "prompts"


class CollectOutput(BaseModel):
    substance: str
    curate_variant: str

    @field_validator("curate_variant")
    @classmethod
    def validate_curate_variant(cls, v: str) -> str:
        available = [p.stem for p in _CURATE_PROMPTS_DIR.glob("*.md") if p.stem != "shared"]
        if v not in available:
            raise ValueError(f"curate_variant '{v}' unbekannt; verfügbar: {available}")
        return v
