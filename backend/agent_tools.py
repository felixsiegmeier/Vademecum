import copy
from typing import Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from models.patient import (
    Befund,
    Diagnose,
    Therapie,
    VerlaufsEintrag,
)
from storage import load_patient, save_patient
from utils.ulid import generate_ulid


# ── Listen-Felder (für delete_entry) ─────────────────────────────────────────

_LIST_FIELDS = (
    "behandlungsdiagnosen",
    "verlaufsdiagnosen",
    "vorbekannte_diagnosen",
    "befunde",
    "therapien",
    "verlaufseintraege",
)

_SOURCE_QUOTE_DESC = (
    "Wörtliches Zitat aus der Quelle (Dokument-Stelle oder User-Aussage), "
    "das diesen Vorschlag belegt. Kein Paraphrasieren."
)


# ── Pydantic-Args-Modelle ─────────────────────────────────────────────────────
# extra="forbid" → additionalProperties: false im generierten JSON-Schema.
# Alle Felder landen via _to_strict_schema() in required (OpenAI strict mode).

class AddBehandlungsdiagnoseArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(description="Klinisch knappe Diagnose, z.B. 'Z.n. 3-fach ACVB'.")
    datum: Optional[str] = Field(None, description="Datum des Auftretens (YYYY-MM-DD) oder null wenn unbekannt.")
    source_quote: str = Field(description=_SOURCE_QUOTE_DESC)


class AddVerlaufsdiagnoseArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(description="Klinisch knappe Diagnose, z.B. 'Pneumonie links'.")
    datum: str = Field(description="Datum des Auftretens (YYYY-MM-DD).")
    source_quote: str = Field(description=_SOURCE_QUOTE_DESC)


class AddVorbekanntesDiagnoseArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(description="Klinisch knappe Diagnose.")
    source_quote: str = Field(description=_SOURCE_QUOTE_DESC)


class AddBefundArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    datum: str = Field(description="Datum des Befunds (YYYY-MM-DD).")
    art: str = Field(description="Art der Untersuchung, z.B. 'TTE', 'CT-Thorax'.")
    text: str = Field(description="Befundtext, klinisch knapp.")
    source_quote: str = Field(description=_SOURCE_QUOTE_DESC)


class AddTherapieArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kategorie: Literal[
        "operativ", "MCS", "RRT", "respiratorisch",
        "interventionell", "antimikrobiell", "medikamentös",
        "bedside", "sonstiges",
    ] = Field(description="Klinische Kategorie des Eingriffs oder der Therapie.")
    bezeichnung: str = Field(description="Name/Beschreibung, z.B. 'CABG 3-fach', 'Impella 5.5', 'Meropenem'.")
    beginn: str = Field(description="Startdatum (YYYY-MM-DD). Bei Einmalereignis = ende.")
    ende: Optional[str] = Field(None, description="Enddatum (YYYY-MM-DD) oder null falls noch laufend.")
    indikation: Optional[str] = Field(None, description="Klinische Indikation, eine Zeile. null wenn aus Kontext offensichtlich.")
    source_quote: str = Field(description=_SOURCE_QUOTE_DESC)


class AddVerlaufseintragArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    datum: str = Field(description="Datum des Eintrags (YYYY-MM-DD).")
    text: str = Field(description="Verlaufstext, ärztlich-knapp, mehrere Sätze möglich.")
    source_quote: str = Field(description=_SOURCE_QUOTE_DESC)


class UpdateAnamneseArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(description="Anamnese-Fließtext, 2–4 Sätze.")
    source_quote: str = Field(description=_SOURCE_QUOTE_DESC)


class UpdateTherapiezielArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(description="Freitext zum Therapieziel und Patientenwillen.")
    source_quote: str = Field(description=_SOURCE_QUOTE_DESC)


class UpdateStatusArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aktiv: bool = Field(description="true = aktiv und sichtbar; false = inaktiv und ausgeblendet.")
    source_quote: str = Field(description=_SOURCE_QUOTE_DESC)


class UpdateBettplatzArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bettplatz: str = Field(description="Bettplatz-Bezeichnung.")
    source_quote: str = Field(description=_SOURCE_QUOTE_DESC)


class UpdateVerlegungszielArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verlegungsziel: str = Field(description="Zielstation oder Zieleinrichtung.")
    source_quote: str = Field(description=_SOURCE_QUOTE_DESC)


class UpdateStammdatenArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feld: Literal["name", "geburtsdatum", "geschlecht", "aufnahmedatum", "aufnahme_quelle"] = Field(
        description="Zu änderndes Stammdaten-Feld."
    )
    wert: str = Field(
        description="Neuer Wert. Datums-Felder als ISO YYYY-MM-DD. Geschlecht: 'm'|'w'|'d'. Aufnahmequelle: 'elektiv'|'notfall'|'extern'."
    )
    source_quote: str = Field(description=_SOURCE_QUOTE_DESC)


class DeleteEntryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(description="ULID des zu löschenden Eintrags (26 Zeichen).")
    source_quote: str = Field(description=_SOURCE_QUOTE_DESC)


# ── Strict-Schema-Generierung ─────────────────────────────────────────────────

def _normalize_prop_inplace(prop: dict) -> None:
    """Normalisiert eine Property für OpenAI strict mode."""
    prop.pop("title", None)
    prop.pop("default", None)

    if "anyOf" in prop:
        types: list[str] = []
        extra: dict = {}
        for sub in prop.pop("anyOf"):
            t = sub.get("type")
            if t == "null":
                types.append("null")
            elif t:
                types.append(t)
                extra.update({k: v for k, v in sub.items() if k != "type"})
            elif "enum" in sub:
                extra["enum"] = sub["enum"]
        non_null = [t for t in types if t != "null"]
        has_null = "null" in types
        if non_null and has_null:
            prop["type"] = [non_null[0], "null"]
        elif non_null:
            prop["type"] = non_null[0]
        prop.update(extra)

    if "properties" in prop:
        _apply_strict_inplace(prop)


def _apply_strict_inplace(schema: dict) -> None:
    """Setzt OpenAI-strict-mode-Invarianten in-place."""
    schema.pop("title", None)
    if "properties" in schema:
        schema.setdefault("type", "object")
        schema["additionalProperties"] = False
        schema["required"] = list(schema["properties"].keys())
        for prop in schema["properties"].values():
            _normalize_prop_inplace(prop)
    for sub in schema.get("$defs", {}).values():
        _apply_strict_inplace(sub)


def _to_strict_schema(model: type[BaseModel]) -> dict:
    """Pydantic model → OpenAI strict-mode parameters dict."""
    schema = copy.deepcopy(model.model_json_schema())
    _apply_strict_inplace(schema)
    return schema


# ── _wrap ─────────────────────────────────────────────────────────────────────

def _wrap(name: str, description: str, args_model: type[BaseModel]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "strict": True,
            "parameters": _to_strict_schema(args_model),
        },
    }


# ── Tool-Funktionen ───────────────────────────────────────────────────────────

def _diagnose(text: str, datum: str | None, source_quote: str) -> Diagnose:
    return Diagnose(id=generate_ulid(), text=text, datum=datum, source_quote=source_quote)


def add_behandlungsdiagnose(patient_id: str, args: AddBehandlungsdiagnoseArgs) -> dict:
    try:
        patient = load_patient(patient_id)
        eintrag = _diagnose(args.text, args.datum, args.source_quote)
        patient.behandlungsdiagnosen.append(eintrag)
        save_patient(patient)
        date_info = f" ({args.datum})" if args.datum else ""
        return {"ok": True, "id": eintrag.id, "summary": f"Behandlungsdiagnose '{args.text}'{date_info} ergänzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def add_verlaufsdiagnose(patient_id: str, args: AddVerlaufsdiagnoseArgs) -> dict:
    try:
        patient = load_patient(patient_id)
        eintrag = _diagnose(args.text, args.datum, args.source_quote)
        patient.verlaufsdiagnosen.append(eintrag)
        save_patient(patient)
        return {"ok": True, "id": eintrag.id, "summary": f"Verlaufsdiagnose '{args.text}' ({args.datum}) ergänzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def add_vorbekannte_diagnose(patient_id: str, args: AddVorbekanntesDiagnoseArgs) -> dict:
    try:
        patient = load_patient(patient_id)
        eintrag = _diagnose(args.text, None, args.source_quote)
        patient.vorbekannte_diagnosen.append(eintrag)
        save_patient(patient)
        return {"ok": True, "id": eintrag.id, "summary": f"Vorbekannte Diagnose '{args.text}' ergänzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def add_befund(patient_id: str, args: AddBefundArgs) -> dict:
    # Befund-Modell hat kein art-Feld → art wird als Präfix in text eingebettet
    try:
        patient = load_patient(patient_id)
        combined_text = f"{args.art}: {args.text}"
        eintrag = Befund(id=generate_ulid(), datum=args.datum, text=combined_text, source_quote=args.source_quote)
        patient.befunde.append(eintrag)
        save_patient(patient)
        return {"ok": True, "id": eintrag.id, "summary": f"Befund ({args.art}, {args.datum}) ergänzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def add_therapie(patient_id: str, args: AddTherapieArgs) -> dict:
    try:
        patient = load_patient(patient_id)
        eintrag = Therapie(
            id=generate_ulid(),
            kategorie=args.kategorie,  # type: ignore[arg-type]
            bezeichnung=args.bezeichnung,
            beginn=args.beginn,
            ende=args.ende,
            indikation=args.indikation,
            source_quote=args.source_quote,
        )
        patient.therapien.append(eintrag)
        save_patient(patient)
        return {"ok": True, "id": eintrag.id, "summary": f"Therapie '{args.bezeichnung}' ({args.kategorie}) ab {args.beginn} ergänzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def add_verlaufseintrag(patient_id: str, args: AddVerlaufseintragArgs) -> dict:
    try:
        patient = load_patient(patient_id)
        eintrag = VerlaufsEintrag(id=generate_ulid(), datum=args.datum, text=args.text, source_quote=args.source_quote)
        patient.verlaufseintraege.append(eintrag)
        save_patient(patient)
        return {"ok": True, "id": eintrag.id, "summary": f"Verlaufseintrag ({args.datum}) ergänzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def update_anamnese(patient_id: str, args: UpdateAnamneseArgs) -> dict:
    try:
        patient = load_patient(patient_id)
        patient.anamnese = args.text
        save_patient(patient)
        return {"ok": True, "summary": "Anamnese aktualisiert."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def update_therapieziel(patient_id: str, args: UpdateTherapiezielArgs) -> dict:
    try:
        patient = load_patient(patient_id)
        patient.therapieziel = args.text
        save_patient(patient)
        return {"ok": True, "summary": "Therapieziel/Patientenwille aktualisiert."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def update_status(patient_id: str, args: UpdateStatusArgs) -> dict:
    try:
        patient = load_patient(patient_id)
        patient.stammdaten.aktiv = args.aktiv
        save_patient(patient)
        label = "aktiv" if args.aktiv else "inaktiv"
        return {"ok": True, "summary": f"Patient auf '{label}' gesetzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def update_bettplatz(patient_id: str, args: UpdateBettplatzArgs) -> dict:
    try:
        patient = load_patient(patient_id)
        patient.stammdaten.bettplatz = args.bettplatz
        save_patient(patient)
        return {"ok": True, "summary": f"Bettplatz auf '{args.bettplatz}' gesetzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def update_verlegungsziel(patient_id: str, args: UpdateVerlegungszielArgs) -> dict:
    try:
        patient = load_patient(patient_id)
        patient.stammdaten.verlegungsziel = args.verlegungsziel
        save_patient(patient)
        return {"ok": True, "summary": f"Verlegungsziel auf '{args.verlegungsziel}' gesetzt."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def update_stammdaten(patient_id: str, args: UpdateStammdatenArgs) -> dict:
    from datetime import date as _date
    try:
        if args.feld == "geschlecht" and args.wert not in ("m", "w", "d"):
            return {"ok": False, "error": f"Ungültiges Geschlecht: '{args.wert}'. Erwartet 'm', 'w' oder 'd'."}
        if args.feld == "aufnahme_quelle" and args.wert not in ("elektiv", "notfall", "extern"):
            return {"ok": False, "error": f"Ungültige Aufnahmequelle: '{args.wert}'. Erwartet 'elektiv', 'notfall' oder 'extern'."}
        if args.feld == "name" and not args.wert.strip():
            return {"ok": False, "error": "Name darf nicht leer sein."}

        parsed_value: object = args.wert
        if args.feld in ("geburtsdatum", "aufnahmedatum"):
            try:
                parsed_value = _date.fromisoformat(args.wert)
            except ValueError:
                return {"ok": False, "error": f"Ungültiges Datum: '{args.wert}'. Erwartet ISO YYYY-MM-DD."}

        patient = load_patient(patient_id)
        setattr(patient.stammdaten, args.feld, parsed_value)
        save_patient(patient)
        return {"ok": True, "summary": f"Stammdaten-Feld '{args.feld}' auf '{args.wert}' geändert."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def delete_entry(patient_id: str, args: DeleteEntryArgs) -> dict:
    try:
        patient = load_patient(patient_id)
        for field in _LIST_FIELDS:
            items = getattr(patient, field)
            for i, item in enumerate(items):
                if item.id == args.id:
                    del items[i]
                    save_patient(patient)
                    return {"ok": True, "summary": f"Eintrag {args.id} aus '{field}' gelöscht."}
        return {"ok": False, "error": f"Keine Liste enthält Eintrag mit id={args.id}."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ── Tool-Schemas (LLM-sichtbar, 12 Tools — update_status bewusst ausgeschlossen) ──

ADD_BEHANDLUNGSDIAGNOSE_SCHEMA = _wrap(
    "add_behandlungsdiagnose",
    (
        "Fügt eine Behandlungsdiagnose hinzu. Behandlungsdiagnosen sind die aktuellen "
        "Hauptprobleme dieses Aufenthalts (Aufnahmegrund, zentrale Akutprobleme). "
        "Beispiele: 'Z.n. bAKE', 'Postkardiotomie-Schock', 'ARDS'."
    ),
    AddBehandlungsdiagnoseArgs,
)

ADD_VERLAUFSDIAGNOSE_SCHEMA = _wrap(
    "add_verlaufsdiagnose",
    (
        "Fügt eine Verlaufsdiagnose hinzu. Verlaufsdiagnosen sind Probleme, "
        "die in diesem Aufenthalt neu aufgetreten oder sich entwickelt haben "
        "(Pneumonie, AKI, postoperatives Delir). NICHT für vorbekannte Diagnosen."
    ),
    AddVerlaufsdiagnoseArgs,
)

ADD_VORBEKANNTE_DIAGNOSE_SCHEMA = _wrap(
    "add_vorbekannte_diagnose",
    (
        "Fügt eine vorbekannte Diagnose aus der Anamnese hinzu. "
        "Nur für Erkrankungen, die VOR diesem Aufenthalt bestanden. "
        "Beispiele: 'Arterielle Hypertonie', 'T2DM', 'Z.n. Apoplex 2019'."
    ),
    AddVorbekanntesDiagnoseArgs,
)

ADD_BEFUND_SCHEMA = _wrap(
    "add_befund",
    (
        "Fügt einen diagnostischen Befund hinzu (TTE, TEE, CT, Rö-Thx, Labor-Spezial). "
        "art = Untersuchungsart, z.B. 'TTE', 'CT-Thorax'."
    ),
    AddBefundArgs,
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
    AddTherapieArgs,
)

ADD_VERLAUFSEINTRAG_SCHEMA = _wrap(
    "add_verlaufseintrag",
    (
        "Fügt einen klinischen Verlaufseintrag hinzu. Pro Tag genau ein Eintrag, "
        "narrativer Volltext mit Tagesstatus, Labortendenz, Beatmung, Hämodynamik, "
        "Eskalationen, Gespräche etc. — alles zusammenhängend in EINEM Text."
    ),
    AddVerlaufseintragArgs,
)

UPDATE_ANAMNESE_SCHEMA = _wrap(
    "update_anamnese",
    (
        "Setzt oder ersetzt die Anamnese. Fließtext mit Aufnahmegrund, "
        "Vorgeschichte, ggf. Ausgangssituation. Ersetzt komplett (kein Append)."
    ),
    UpdateAnamneseArgs,
)

UPDATE_THERAPIEZIEL_SCHEMA = _wrap(
    "update_therapieziel",
    (
        "Setzt oder ersetzt Therapieziel/Patientenwille als Freitext. "
        "Beispiel: 'Volle Therapie nach Patientenwille, DNR nicht eingerichtet'."
    ),
    UpdateTherapiezielArgs,
)

UPDATE_BETTPLATZ_SCHEMA = _wrap(
    "update_bettplatz",
    "Setzt den aktuellen Bettplatz, z.B. 'ITS-1 / Bett 3'.",
    UpdateBettplatzArgs,
)

UPDATE_VERLEGUNGSZIEL_SCHEMA = _wrap(
    "update_verlegungsziel",
    "Setzt das geplante Verlegungsziel, z.B. 'IMC', 'Normalstation', 'externes KH'.",
    UpdateVerlegungszielArgs,
)

UPDATE_STAMMDATEN_SCHEMA = _wrap(
    "update_stammdaten",
    (
        "Aktualisiert ein einzelnes Feld der Stammdaten. Nur bei expliziten "
        "Korrekturen verwenden. Bettplatz/Verlegungsziel/Status haben eigene Tools."
    ),
    UpdateStammdatenArgs,
)

DELETE_ENTRY_SCHEMA = _wrap(
    "delete_entry",
    (
        "Löscht einen Listen-Eintrag (Diagnose, Befund, Therapie, Verlaufseintrag) "
        "anhand der ULID. Backend findet die richtige Liste anhand der ID automatisch."
    ),
    DeleteEntryArgs,
)


# ── Exports ───────────────────────────────────────────────────────────────────

# 12 LLM-sichtbare Schemas — update_status bewusst nicht enthalten (F6).
TOOL_SCHEMAS: list[dict] = [
    ADD_BEHANDLUNGSDIAGNOSE_SCHEMA,
    ADD_VERLAUFSDIAGNOSE_SCHEMA,
    ADD_VORBEKANNTE_DIAGNOSE_SCHEMA,
    ADD_BEFUND_SCHEMA,
    ADD_THERAPIE_SCHEMA,
    ADD_VERLAUFSEINTRAG_SCHEMA,
    UPDATE_ANAMNESE_SCHEMA,
    UPDATE_THERAPIEZIEL_SCHEMA,
    UPDATE_BETTPLATZ_SCHEMA,
    UPDATE_VERLEGUNGSZIEL_SCHEMA,
    UPDATE_STAMMDATEN_SCHEMA,
    DELETE_ENTRY_SCHEMA,
]

# 13 Dispatch-Mappings — update_status inkludiert (wird über UI aufgerufen).
TOOL_ARGS: dict[str, type[BaseModel]] = {
    "add_behandlungsdiagnose": AddBehandlungsdiagnoseArgs,
    "add_verlaufsdiagnose": AddVerlaufsdiagnoseArgs,
    "add_vorbekannte_diagnose": AddVorbekanntesDiagnoseArgs,
    "add_befund": AddBefundArgs,
    "add_therapie": AddTherapieArgs,
    "add_verlaufseintrag": AddVerlaufseintragArgs,
    "update_anamnese": UpdateAnamneseArgs,
    "update_therapieziel": UpdateTherapiezielArgs,
    "update_status": UpdateStatusArgs,
    "update_bettplatz": UpdateBettplatzArgs,
    "update_verlegungsziel": UpdateVerlegungszielArgs,
    "update_stammdaten": UpdateStammdatenArgs,
    "delete_entry": DeleteEntryArgs,
}

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
