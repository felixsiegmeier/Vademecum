from pydantic import BaseModel


class DiagnosenOutput(BaseModel):
    behandlung: list[str] = []
    verlauf: list[str] = []
    vorbekannt: list[str] = []
