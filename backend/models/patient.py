from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


# ── List-Items mit stabiler ID ────────────────────────────────────────────────
# Alle List-Items tragen eine global eindeutige ULID, die der Server beim
# Apply setzt. Das LLM sieht/setzt keine IDs — sie werden im Backend generiert.

class Diagnose(BaseModel):
    """Gemeinsames Modell für Behandlungs-, Verlaufs- und Vorbekannte Diagnosen.

    `datum` ist optional, weil vorbekannte Diagnosen typischerweise kein
    konkretes Datum haben.
    """
    id: str
    text: str
    datum: Optional[date] = None
    source_quote: str


class Befund(BaseModel):
    id: str
    datum: date
    text: str
    source_quote: str


class Therapie(BaseModel):
    """Eingriffe und Therapien. kategorie unterscheidet 9 klinische Typen."""
    id: str
    kategorie: Literal[
        "operativ", "MCS", "RRT", "respiratorisch",
        "interventionell", "antimikrobiell", "medikamentös",
        "bedside", "sonstiges"
    ]
    bezeichnung: str
    beginn: date
    ende: Optional[date] = None
    indikation: Optional[str] = None
    source_quote: str


class VerlaufsEintrag(BaseModel):
    """Pro Tag genau ein Eintrag. Narrativer Volltext, append-only."""
    id: str
    datum: date
    text: str
    source_quote: str


# ── Singleton-Felder ──────────────────────────────────────────────────────────

class Stammdaten(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    geburtsdatum: Optional[date] = None
    geschlecht: Optional[str] = None
    bettplatz: Optional[str] = None
    aufnahmedatum: date
    aufnahme_quelle: Optional[str] = None
    verlegungsziel: Optional[str] = None
    aktiv: bool = True


class Patient(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stammdaten: Stammdaten
    anamnese: str = ""
    therapieziel: str = ""

    behandlungsdiagnosen: list[Diagnose] = []
    verlaufsdiagnosen: list[Diagnose] = []
    vorbekannte_diagnosen: list[Diagnose] = []
    befunde: list[Befund] = []
    therapien: list[Therapie] = []
    verlaufseintraege: list[VerlaufsEintrag] = []


class PatientSummary(BaseModel):
    id: str
    name: str
    aktiv: bool
    bettplatz: Optional[str] = None
    aufnahmedatum: date
