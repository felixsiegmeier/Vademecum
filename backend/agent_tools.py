import os
import time
from typing import Callable

from models.patient import (
    Befund,
    Diagnose,
    Therapie,
    VerlaufsEintrag,
)
from storage import load_patient, save_patient


# ── ULID ──────────────────────────────────────────────────────────────────────
# Crockford-Base32 (26 Zeichen). 48 Bit Zeitstempel + 80 Bit Zufall = 128 Bit.
# Ausreichend kollisionsarm ohne externe Dependency.

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_ulid() -> str:
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    randomness = int.from_bytes(os.urandom(10), "big")
    n = (timestamp_ms << 80) | randomness
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[n & 0x1F])
        n >>= 5
    return "".join(reversed(chars))


# ── Listen-Felder (für delete_entry) ─────────────────────────────────────────
# Reihenfolge irrelevant — wir suchen über alle Listen, bis wir die ID finden.

_LIST_FIELDS = (
    "behandlungsdiagnosen",
    "verlaufsdiagnosen",
    "vorbekannte_diagnosen",
    "befunde",
    "therapien",
    "verlaufseintraege",
)


# ── Add-Tools ────────────────────────────────────────────────────────────────
# Jede Add-Funktion: load → ULID generieren → Item bauen → an Liste anhängen → save.

def _diagnose(text: str, datum: str | None, source_quote: str) -> Diagnose:
    return Diagnose(id=generate_ulid(), text=text, datum=datum, source_quote=source_quote)


def add_behandlungsdiagnose(patient_id: str, text: str, datum: str | None = None, source_quote: str = "") -> dict:
    try:
        patient = load_patient(patient_id)
        eintrag = _diagnose(text, datum, source_quote)
        patient.behandlungsdiagnosen.append(eintrag)
        save_patient(patient)
        date_info = f" ({datum})" if datum else ""
        return {"ok": True, "id": eintrag.id, "summary": f"Behandlungsdiagnose '{text}'{date_info} ergänzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def add_verlaufsdiagnose(patient_id: str, text: str, datum: str, source_quote: str = "") -> dict:
    try:
        patient = load_patient(patient_id)
        eintrag = _diagnose(text, datum, source_quote)
        patient.verlaufsdiagnosen.append(eintrag)
        save_patient(patient)
        return {"ok": True, "id": eintrag.id, "summary": f"Verlaufsdiagnose '{text}' ({datum}) ergänzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def add_vorbekannte_diagnose(patient_id: str, text: str, source_quote: str = "") -> dict:
    try:
        patient = load_patient(patient_id)
        eintrag = _diagnose(text, None, source_quote)
        patient.vorbekannte_diagnosen.append(eintrag)
        save_patient(patient)
        return {"ok": True, "id": eintrag.id, "summary": f"Vorbekannte Diagnose '{text}' ergänzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def add_befund(patient_id: str, datum: str, art: str, text: str, source_quote: str = "") -> dict:
    # Befund-Modell hat kein art-Feld → art wird als Präfix in text eingebettet
    try:
        patient = load_patient(patient_id)
        combined_text = f"{art}: {text}"
        eintrag = Befund(id=generate_ulid(), datum=datum, text=combined_text, source_quote=source_quote)
        patient.befunde.append(eintrag)
        save_patient(patient)
        return {"ok": True, "id": eintrag.id, "summary": f"Befund ({art}, {datum}) ergänzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def add_therapie(
    patient_id: str,
    kategorie: str,
    bezeichnung: str,
    beginn: str,
    indikation: str | None = None,
    ende: str | None = None,
    source_quote: str = "",
) -> dict:
    try:
        patient = load_patient(patient_id)
        eintrag = Therapie(
            id=generate_ulid(),
            kategorie=kategorie,  # type: ignore[arg-type]
            bezeichnung=bezeichnung,
            beginn=beginn,
            ende=ende,
            indikation=indikation,
            source_quote=source_quote,
        )
        patient.therapien.append(eintrag)
        save_patient(patient)
        return {"ok": True, "id": eintrag.id, "summary": f"Therapie '{bezeichnung}' ({kategorie}) ab {beginn} ergänzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def add_verlaufseintrag(patient_id: str, datum: str, text: str, source_quote: str = "") -> dict:
    try:
        patient = load_patient(patient_id)
        eintrag = VerlaufsEintrag(id=generate_ulid(), datum=datum, text=text, source_quote=source_quote)
        patient.verlaufseintraege.append(eintrag)
        save_patient(patient)
        return {"ok": True, "id": eintrag.id, "summary": f"Verlaufseintrag ({datum}) ergänzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ── Update-Tools (Singletons) ────────────────────────────────────────────────
# Update überschreibt komplett — kein partial-update. source_quote wird in der
# V1.5-Singleton-Struktur nicht persistiert (wird vom Tool ignoriert).

def update_anamnese(patient_id: str, text: str, source_quote: str = "") -> dict:
    try:
        patient = load_patient(patient_id)
        patient.anamnese = text
        save_patient(patient)
        return {"ok": True, "summary": "Anamnese aktualisiert."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def update_therapieziel(patient_id: str, text: str, source_quote: str = "") -> dict:
    try:
        patient = load_patient(patient_id)
        patient.therapieziel = text
        save_patient(patient)
        return {"ok": True, "summary": "Therapieziel/Patientenwille aktualisiert."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def update_status(patient_id: str, aktiv: bool, source_quote: str = "") -> dict:
    try:
        patient = load_patient(patient_id)
        patient.stammdaten.aktiv = aktiv
        save_patient(patient)
        label = "aktiv" if aktiv else "inaktiv"
        return {"ok": True, "summary": f"Patient auf '{label}' gesetzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def update_bettplatz(patient_id: str, bettplatz: str, source_quote: str = "") -> dict:
    try:
        patient = load_patient(patient_id)
        patient.stammdaten.bettplatz = bettplatz
        save_patient(patient)
        return {"ok": True, "summary": f"Bettplatz auf '{bettplatz}' gesetzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def update_verlegungsziel(patient_id: str, verlegungsziel: str, source_quote: str = "") -> dict:
    try:
        patient = load_patient(patient_id)
        patient.stammdaten.verlegungsziel = verlegungsziel
        save_patient(patient)
        return {"ok": True, "summary": f"Verlegungsziel auf '{verlegungsziel}' gesetzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def update_stammdaten(patient_id: str, feld: str, wert: str, source_quote: str = "") -> dict:
    from datetime import date as _date
    try:
        if feld == "geschlecht" and wert not in ("m", "w", "d"):
            return {"ok": False, "error": f"Ungültiges Geschlecht: '{wert}'. Erwartet 'm', 'w' oder 'd'."}
        if feld == "aufnahme_quelle" and wert not in ("elektiv", "notfall", "extern"):
            return {"ok": False, "error": f"Ungültige Aufnahmequelle: '{wert}'. Erwartet 'elektiv', 'notfall' oder 'extern'."}
        if feld == "name" and not wert.strip():
            return {"ok": False, "error": "Name darf nicht leer sein."}

        parsed_value: object = wert
        if feld in ("geburtsdatum", "aufnahmedatum"):
            try:
                parsed_value = _date.fromisoformat(wert)
            except ValueError:
                return {"ok": False, "error": f"Ungültiges Datum: '{wert}'. Erwartet ISO YYYY-MM-DD."}

        patient = load_patient(patient_id)
        setattr(patient.stammdaten, feld, parsed_value)
        save_patient(patient)
        return {"ok": True, "summary": f"Stammdaten-Feld '{feld}' auf '{wert}' geändert."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ── Delete-Tool ──────────────────────────────────────────────────────────────
# Generisch über alle Listen. ULID ist global eindeutig, also reicht die ID
# als Identifier — kein Listen-Hint nötig.

def delete_entry(patient_id: str, id: str, source_quote: str = "") -> dict:
    try:
        patient = load_patient(patient_id)
        for field in _LIST_FIELDS:
            items = getattr(patient, field)
            for i, item in enumerate(items):
                if item.id == id:
                    del items[i]
                    save_patient(patient)
                    return {"ok": True, "summary": f"Eintrag {id} aus '{field}' gelöscht."}
        return {"ok": False, "error": f"Keine Liste enthält Eintrag mit id={id}."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ── Tool-Schemas (OpenAI strict mode) ────────────────────────────────────────
# Strict mode: alle properties in `required`, additionalProperties: false.
# Optionale Pydantic-Felder (z.B. Therapie.ende, Behandlungsdiagnose.datum)
# werden als ["string", "null"] typisiert und stehen trotzdem in `required`.

_SOURCE_QUOTE_PROPERTY = {
    "type": "string",
    "description": (
        "Wörtliches Zitat aus der Quelle (Dokument-Stelle oder User-Aussage), "
        "das diesen Vorschlag belegt. Kein Paraphrasieren."
    ),
}


def _wrap(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": properties,
                "required": required,
            },
        },
    }


ADD_BEHANDLUNGSDIAGNOSE_SCHEMA = _wrap(
    "add_behandlungsdiagnose",
    (
        "Fügt eine Behandlungsdiagnose hinzu. Behandlungsdiagnosen sind die aktuellen "
        "Hauptprobleme dieses Aufenthalts (Aufnahmegrund, zentrale Akutprobleme). "
        "Beispiele: 'Z.n. bAKE', 'Postkardiotomie-Schock', 'ARDS'."
    ),
    {
        "text": {"type": "string", "description": "Klinisch knappe Diagnose, z.B. 'Z.n. 3-fach ACVB'."},
        "datum": {
            "type": ["string", "null"],
            "format": "date",
            "description": "Datum des Auftretens (YYYY-MM-DD) oder null wenn unbekannt.",
        },
        "source_quote": _SOURCE_QUOTE_PROPERTY,
    },
    ["text", "datum", "source_quote"],
)

ADD_VERLAUFSDIAGNOSE_SCHEMA = _wrap(
    "add_verlaufsdiagnose",
    (
        "Fügt eine Verlaufsdiagnose hinzu. Verlaufsdiagnosen sind Probleme, "
        "die in diesem Aufenthalt neu aufgetreten oder sich entwickelt haben "
        "(Pneumonie, AKI, postoperatives Delir). NICHT für vorbekannte Diagnosen."
    ),
    {
        "text": {"type": "string", "description": "Klinisch knappe Diagnose, z.B. 'Pneumonie links'."},
        "datum": {"type": "string", "format": "date", "description": "Datum des Auftretens (YYYY-MM-DD)."},
        "source_quote": _SOURCE_QUOTE_PROPERTY,
    },
    ["text", "datum", "source_quote"],
)

ADD_VORBEKANNTE_DIAGNOSE_SCHEMA = _wrap(
    "add_vorbekannte_diagnose",
    (
        "Fügt eine vorbekannte Diagnose aus der Anamnese hinzu. "
        "Nur für Erkrankungen, die VOR diesem Aufenthalt bestanden. "
        "Beispiele: 'Arterielle Hypertonie', 'T2DM', 'Z.n. Apoplex 2019'."
    ),
    {
        "text": {"type": "string", "description": "Klinisch knappe Diagnose."},
        "source_quote": _SOURCE_QUOTE_PROPERTY,
    },
    ["text", "source_quote"],
)

ADD_BEFUND_SCHEMA = _wrap(
    "add_befund",
    (
        "Fügt einen diagnostischen Befund hinzu (TTE, TEE, CT, Rö-Thx, Labor-Spezial). "
        "art = Untersuchungsart, z.B. 'TTE', 'CT-Thorax'."
    ),
    {
        "datum": {"type": "string", "format": "date", "description": "Datum des Befunds (YYYY-MM-DD)."},
        "art": {"type": "string", "description": "Art der Untersuchung, z.B. 'TTE', 'CT-Thorax'."},
        "text": {"type": "string", "description": "Befundtext, klinisch knapp."},
        "source_quote": _SOURCE_QUOTE_PROPERTY,
    },
    ["datum", "art", "text", "source_quote"],
)

ADD_THERAPIE_SCHEMA = _wrap(
    "add_therapie",
    (
        "Fügt einen Eingriff oder eine Therapie hinzu. "
        "kategorie ist eines der 9 Werte: operativ, MCS, RRT, respiratorisch, "
        "interventionell, antimikrobiell, medikamentös, bedside, sonstiges. "
        "Einmaliges Event (z.B. CABG): beginn = ende = Datum. "
        "Laufend: ende = null."
    ),
    {
        "kategorie": {
            "type": "string",
            "enum": [
                "operativ", "MCS", "RRT", "respiratorisch",
                "interventionell", "antimikrobiell", "medikamentös",
                "bedside", "sonstiges",
            ],
            "description": "Klinische Kategorie des Eingriffs oder der Therapie.",
        },
        "bezeichnung": {
            "type": "string",
            "description": "Name/Beschreibung, z.B. 'CABG 3-fach', 'Impella 5.5', 'Meropenem'.",
        },
        "beginn": {"type": "string", "format": "date", "description": "Startdatum (YYYY-MM-DD). Bei Einmalereignis = ende."},
        "ende": {
            "type": ["string", "null"],
            "format": "date",
            "description": "Enddatum (YYYY-MM-DD) oder null falls noch laufend. Bei Einmalereignis = beginn.",
        },
        "indikation": {
            "type": ["string", "null"],
            "description": "Klinische Indikation, eine Zeile. null wenn aus Kontext offensichtlich.",
        },
        "source_quote": _SOURCE_QUOTE_PROPERTY,
    },
    ["kategorie", "bezeichnung", "beginn", "ende", "indikation", "source_quote"],
)

ADD_VERLAUFSEINTRAG_SCHEMA = _wrap(
    "add_verlaufseintrag",
    (
        "Fügt einen klinischen Verlaufseintrag hinzu. Pro Tag genau ein Eintrag, "
        "narrativer Volltext mit Tagesstatus, Labortendenz, Beatmung, Hämodynamik, "
        "Eskalationen, Gespräche etc. — alles zusammenhängend in EINEM Text."
    ),
    {
        "datum": {"type": "string", "format": "date", "description": "Datum des Eintrags (YYYY-MM-DD)."},
        "text": {"type": "string", "description": "Verlaufstext, ärztlich-knapp, mehrere Sätze möglich."},
        "source_quote": _SOURCE_QUOTE_PROPERTY,
    },
    ["datum", "text", "source_quote"],
)

UPDATE_ANAMNESE_SCHEMA = _wrap(
    "update_anamnese",
    (
        "Setzt oder ersetzt die Anamnese. Fließtext mit Aufnahmegrund, "
        "Vorgeschichte, ggf. Ausgangssituation. Ersetzt komplett (kein Append)."
    ),
    {
        "text": {"type": "string", "description": "Anamnese-Fließtext, 2–4 Sätze."},
        "source_quote": _SOURCE_QUOTE_PROPERTY,
    },
    ["text", "source_quote"],
)

UPDATE_THERAPIEZIEL_SCHEMA = _wrap(
    "update_therapieziel",
    (
        "Setzt oder ersetzt Therapieziel/Patientenwille als Freitext. "
        "Beispiel: 'Volle Therapie nach Patientenwille, DNR nicht eingerichtet'."
    ),
    {
        "text": {"type": "string", "description": "Freitext zum Therapieziel und Patientenwillen."},
        "source_quote": _SOURCE_QUOTE_PROPERTY,
    },
    ["text", "source_quote"],
)

UPDATE_STATUS_SCHEMA = _wrap(
    "update_status",
    "Setzt Patient auf aktiv (true) oder inaktiv (false). Inaktive Patienten sind in der Sidebar default ausgeblendet.",
    {
        "aktiv": {"type": "boolean", "description": "true = aktiv und sichtbar; false = inaktiv und ausgeblendet."},
        "source_quote": _SOURCE_QUOTE_PROPERTY,
    },
    ["aktiv", "source_quote"],
)

UPDATE_BETTPLATZ_SCHEMA = _wrap(
    "update_bettplatz",
    "Setzt den aktuellen Bettplatz, z.B. 'ITS-1 / Bett 3'.",
    {
        "bettplatz": {"type": "string", "description": "Bettplatz-Bezeichnung."},
        "source_quote": _SOURCE_QUOTE_PROPERTY,
    },
    ["bettplatz", "source_quote"],
)

UPDATE_VERLEGUNGSZIEL_SCHEMA = _wrap(
    "update_verlegungsziel",
    "Setzt das geplante Verlegungsziel, z.B. 'IMC', 'Normalstation', 'externes KH'.",
    {
        "verlegungsziel": {"type": "string", "description": "Zielstation oder Zieleinrichtung."},
        "source_quote": _SOURCE_QUOTE_PROPERTY,
    },
    ["verlegungsziel", "source_quote"],
)

UPDATE_STAMMDATEN_SCHEMA = _wrap(
    "update_stammdaten",
    (
        "Aktualisiert ein einzelnes Feld der Stammdaten. Nur bei expliziten "
        "Korrekturen verwenden. Bettplatz/Verlegungsziel/Status haben eigene Tools."
    ),
    {
        "feld": {
            "type": "string",
            "enum": ["name", "geburtsdatum", "geschlecht", "aufnahmedatum", "aufnahme_quelle"],
            "description": "Zu änderndes Stammdaten-Feld.",
        },
        "wert": {
            "type": "string",
            "description": (
                "Neuer Wert. Datums-Felder als ISO YYYY-MM-DD. "
                "Geschlecht: 'm'|'w'|'d'. Aufnahmequelle: 'elektiv'|'notfall'|'extern'."
            ),
        },
        "source_quote": _SOURCE_QUOTE_PROPERTY,
    },
    ["feld", "wert", "source_quote"],
)

DELETE_ENTRY_SCHEMA = _wrap(
    "delete_entry",
    (
        "Löscht einen Listen-Eintrag (Diagnose, Befund, Therapie, Verlaufseintrag) "
        "anhand der ULID. Backend findet die richtige Liste anhand der ID automatisch."
    ),
    {
        "id": {"type": "string", "description": "ULID des zu löschenden Eintrags (26 Zeichen)."},
        "source_quote": _SOURCE_QUOTE_PROPERTY,
    },
    ["id", "source_quote"],
)


# ── Exports ───────────────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    ADD_BEHANDLUNGSDIAGNOSE_SCHEMA,
    ADD_VERLAUFSDIAGNOSE_SCHEMA,
    ADD_VORBEKANNTE_DIAGNOSE_SCHEMA,
    ADD_BEFUND_SCHEMA,
    ADD_THERAPIE_SCHEMA,
    ADD_VERLAUFSEINTRAG_SCHEMA,
    UPDATE_ANAMNESE_SCHEMA,
    UPDATE_THERAPIEZIEL_SCHEMA,
    UPDATE_STATUS_SCHEMA,
    UPDATE_BETTPLATZ_SCHEMA,
    UPDATE_VERLEGUNGSZIEL_SCHEMA,
    UPDATE_STAMMDATEN_SCHEMA,
    DELETE_ENTRY_SCHEMA,
]

TOOL_FUNCTIONS: dict[str, Callable] = {
    "add_behandlungsdiagnose": add_behandlungsdiagnose,
    "add_verlaufsdiagnose": add_verlaufsdiagnose,
    "add_vorbekannte_diagnose": add_vorbekannte_diagnose,
    "add_befund": add_befund,
    "add_therapie": add_therapie,
    "add_verlaufseintrag": add_verlaufseintrag,
    "update_anamnese": update_anamnese,
    "update_therapieziel": update_therapieziel,
    "update_status": update_status,
    "update_bettplatz": update_bettplatz,
    "update_verlegungsziel": update_verlegungsziel,
    "update_stammdaten": update_stammdaten,
    "delete_entry": delete_entry,
}
