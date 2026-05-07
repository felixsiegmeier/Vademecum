from pydantic import BaseModel, field_validator

from workflows.brief.verlauf import validate_curate_variant as _validate_curate_variant


class CollectOutput(BaseModel):
    substance: str
    curate_variant: str

    @field_validator("curate_variant")
    @classmethod
    def _check_curate_variant(cls, v: str) -> str:
        return _validate_curate_variant(v)
