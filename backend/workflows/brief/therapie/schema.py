from pydantic import BaseModel


class TherapieOutput(BaseModel):
    initial_op: str = ""
    antimikrobiell: list[str] = []
    weitere: list[str] = []
