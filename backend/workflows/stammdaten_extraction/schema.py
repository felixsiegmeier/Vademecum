from typing import Literal, Optional

from pydantic import BaseModel


class StammdatenExtractResult(BaseModel):
    name: Optional[str] = None
    geburtsdatum: Optional[str] = None          # YYYY-MM-DD
    geschlecht: Optional[Literal["m", "w", "d"]] = None
    bettplatz: Optional[str] = None
    aufnahmedatum: Optional[str] = None         # YYYY-MM-DD
    aufnahme_quelle: Optional[Literal["elektiv", "notfall", "extern"]] = None
