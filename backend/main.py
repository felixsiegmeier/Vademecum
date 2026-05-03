import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, RateLimitError
from pydantic import BaseModel
from agent_tools import TOOL_FUNCTIONS
from agent_document_extraction import extract_proposals
from agent_extraction_core import Proposal
from agent_patient_chat import CHAT_2PASS_CUTOFF, run_single_pass_chat
from agent_stammdaten_extraction import StammdatenExtractResult, extract_stammdaten
from llm_client import LLMClient
from models.patient import Patient, PatientSummary, Stammdaten
from storage import (
    brief_input_hash,
    delete_patient,
    empty_brief_data,
    list_patient_ids,
    load_brief,
    load_meilenstein,
    load_patient,
    next_patient_id,
    patient_yaml_hash,
    save_brief,
    delete_brief,
    save_meilenstein,
    delete_meilenstein,
    save_patient,
    update_brief_field,
    update_meilenstein_content,
    BRIEF_FIELDS
)

load_dotenv()

# Erlaubte MIME-Typen für alle Upload-Endpoints
ALLOWED_UPLOAD_MIMES: frozenset[str] = frozenset({
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/tiff",
    "image/bmp",
})

app = FastAPI(title="arztbrief-app")
# Ein globaler LLM-Client für alle Requests (hält die HTTP-Session offen)
llm = LLMClient()

# Erlaubt Requests vom Vite-Dev-Server (localhost:5173) und späteren Deployments
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Lazy-Loader für System-Prompts ────────────────────────────────────────────
# Prompts liegen als .txt-Dateien auf Disk — erst beim ersten Aufruf gelesen,
# danach im Modul-Cache gehalten, damit kein Disk-I/O pro Request entsteht.

_MEILENSTEIN_SYSTEM_PROMPT: str | None = None


def _get_meilenstein_system_prompt() -> str:
    global _MEILENSTEIN_SYSTEM_PROMPT
    if _MEILENSTEIN_SYSTEM_PROMPT is None:
        prompt_path = Path(__file__).parent / "prompts" / "meilenstein_system.txt"
        _MEILENSTEIN_SYSTEM_PROMPT = prompt_path.read_text(encoding="utf-8")
    return _MEILENSTEIN_SYSTEM_PROMPT


_BRIEF_SYSTEM_PROMPT: str | None = None

_BRIEF_FIELD_LABELS = {
    "diagnosen": "Diagnosen",
    "anamnese": "Anamnese",
    "operationen_prozeduren": "Operationen und Prozeduren",
    "konservative_therapien": "Konservative Therapien",
    "antimikrobielle_therapie": "Antimikrobielle Therapie",
    "verlauf": "Verlauf",
}


def _get_brief_system_prompt() -> str:
    global _BRIEF_SYSTEM_PROMPT
    if _BRIEF_SYSTEM_PROMPT is None:
        prompt_path = Path(__file__).parent / "prompts" / "brief_system.txt"
        _BRIEF_SYSTEM_PROMPT = prompt_path.read_text(encoding="utf-8")
    return _BRIEF_SYSTEM_PROMPT


# ── Request/Response-Modelle ──────────────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


class PatientChatRequest(BaseModel):
    messages: list[dict[str, Any]]


class CreateStammdatenRequest(BaseModel):
    name: str
    geburtsdatum: date
    geschlecht: Literal["m", "w", "d"]
    bettplatz: str
    aufnahmedatum: date
    aufnahme_quelle: Optional[Literal["elektiv", "notfall", "extern"]] = None
    verlegungsziel: Optional[str] = None


class CreatePatientRequest(BaseModel):
    stammdaten: CreateStammdatenRequest


class ApplyToolsRequest(BaseModel):
    calls: list[dict]


class ApplyProposalsRequest(BaseModel):
    proposals: list[Proposal]
    force: bool = False


class AktivRequest(BaseModel):
    aktiv: bool


class MeilensteinUpdateRequest(BaseModel):
    content: str


class BriefFieldUpdateRequest(BaseModel):
    content: str


class BriefRegenRequest(BaseModel):
    custom_prompt: Optional[str] = None


# ── Patienten-CRUD ────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/patients")
def get_patients():
    """Gibt eine schlanke Liste aller Patienten zurück (nur für die Sidebar)."""
    patients = [load_patient(pid) for pid in list_patient_ids()]
    summaries = [
        PatientSummary(
            id=p.stammdaten.id,
            name=p.stammdaten.name,
            aktiv=p.stammdaten.aktiv,
            bettplatz=p.stammdaten.bettplatz,
            aufnahmedatum=p.stammdaten.aufnahmedatum,
        )
        for p in patients
    ]
    return JSONResponse(
        content=[s.model_dump(mode="json") for s in summaries],
        media_type="application/json; charset=utf-8",
    )


@app.get("/api/patients/{patient_id}")
def get_patient(patient_id: str):
    """Gibt den vollständigen Patient-Datensatz zurück (für PatientLanding)."""
    try:
        patient = load_patient(patient_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return JSONResponse(
        content=patient.model_dump(mode="json"),
        media_type="application/json; charset=utf-8",
    )


@app.post("/api/patients")
def create_patient(req: CreatePatientRequest):
    """Legt einen neuen Patienten an und gibt die generierte ID zurück."""
    patient_id = next_patient_id()
    s = req.stammdaten
    patient = Patient(
        stammdaten=Stammdaten(
            id=patient_id,
            name=s.name,
            geburtsdatum=s.geburtsdatum,
            geschlecht=s.geschlecht,
            bettplatz=s.bettplatz,
            aufnahmedatum=s.aufnahmedatum,
            aufnahme_quelle=s.aufnahme_quelle,
            verlegungsziel=s.verlegungsziel,
            aktiv=True,
        ),
    )
    save_patient(patient)
    return JSONResponse(
        content={"patient_id": patient_id},
        media_type="application/json; charset=utf-8",
    )


@app.delete("/api/patients/{patient_id}")
def delete_patient_endpoint(patient_id: str):
    """Löscht Patient + alle zugehörigen Dateien (YAML, Meilenstein, Brief)."""
    try:
        load_patient(patient_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Patient {patient_id} nicht gefunden")
    delete_patient(patient_id)
    return JSONResponse(content={"ok": True})


@app.patch("/api/patients/{patient_id}/aktiv")
def set_aktiv(patient_id: str, req: AktivRequest):
    """Setzt den aktiv/inaktiv-Status (steuert Sidebar-Sichtbarkeit)."""
    try:
        patient = load_patient(patient_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Patient {patient_id} nicht gefunden")
    patient.stammdaten.aktiv = req.aktiv
    save_patient(patient)
    return JSONResponse(content={"ok": True, "aktiv": req.aktiv})


# ── Meilenstein ───────────────────────────────────────────────────────────────
# Der Meilenstein ist eine vom LLM generierte Markdown-Übersicht des Patientenstatus.
# Er wird separat gespeichert (.md + .meta.json) und kann vom Arzt bearbeitet werden.
# is_stale = True, wenn das YAML nach der letzten Generierung geändert wurde.

@app.get("/api/patients/{patient_id}/meilenstein")
def get_meilenstein(patient_id: str):
    try:
        load_patient(patient_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Patient {patient_id} nicht gefunden")

    result = load_meilenstein(patient_id)
    if result is None:
        raise HTTPException(404, "Kein Meilenstein vorhanden")

    md_content, meta = result
    # Hash des aktuellen YAML vergleichen mit dem Hash zum Zeitpunkt der Generierung
    current_hash = patient_yaml_hash(patient_id)
    is_stale = meta.get("yaml_hash", "") != current_hash

    return JSONResponse(content={
        "content": md_content,
        "generated_at": meta.get("generated_at"),
        "is_stale": is_stale,
    })


@app.post("/api/patients/{patient_id}/meilenstein/generate")
async def generate_meilenstein(patient_id: str):
    """LLM generiert Meilenstein aus dem aktuellen Patient-YAML."""
    try:
        patient = load_patient(patient_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Patient {patient_id} nicht gefunden")

    # Patient-Daten als YAML serialisieren — das ist die einzige Quelle für das LLM
    patient_yaml = yaml.safe_dump(
        patient.model_dump(exclude_none=True, mode="json"),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=100,
    )
    today_str = date.today().strftime("%d.%m.%Y")
    system_prompt = _get_meilenstein_system_prompt()
    user_msg = (
        f"Generiere den Meilenstein für folgenden Patienten. "
        f"Heutiges Datum (letzte Aktualisierung): {today_str}\n\n"
        f"YAML:\n{patient_yaml}"
    )

    try:
        response = await llm.chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
            max_tokens=4096,
        )
    except RateLimitError:
        raise HTTPException(429, "LLM Rate-Limit erreicht. Bitte kurz warten.")
    except APIConnectionError as e:
        raise HTTPException(503, f"LLM nicht erreichbar: {e}")
    except APIStatusError as e:
        raise HTTPException(502, f"LLM API Fehler {e.status_code}: {e.message}")

    md_content = (response.choices[0].message.content or "").strip()
    # Hash speichern, damit später geprüft werden kann, ob Daten sich geändert haben
    yaml_hash = patient_yaml_hash(patient_id)
    generated_at = datetime.now(timezone.utc).isoformat()
    meta = {"yaml_hash": yaml_hash, "generated_at": generated_at}
    save_meilenstein(patient_id, md_content, meta)

    return JSONResponse(content={
        "content": md_content,
        "generated_at": generated_at,
        "is_stale": False,
    })

@app.put("/api/patients/{patient_id}/meilenstein")
def update_meilenstein(patient_id: str, req: MeilensteinUpdateRequest):
    """Speichert manuelle Bearbeitungen des Meilensteins (ohne Neuberechnung des Hashes)."""
    try:
        load_patient(patient_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Patient {patient_id} nicht gefunden")
    update_meilenstein_content(patient_id, req.content)
    return JSONResponse(content={"ok": True})

@app.delete("/api/patients/{patient_id}/meilenstein")
def delete_meilenstein_endpoint(patient_id: str):
    meilenstein = load_meilenstein(patient_id)
    if meilenstein is None:
        raise HTTPException(404, "Kein Meilenstein vorhanden")
    delete_meilenstein(patient_id)
    return JSONResponse(content={"ok": True})


# ── Brief ─────────────────────────────────────────────────────────────────────
# Der Brief ist der Arztbrief — aufgeteilt in 6 Abschnitte (Felder).
# Jedes Feld kann einzeln regeneriert werden, ohne die anderen zu überschreiben.
# Staleness wird per Hash auf YAML + Meilenstein erkannt (brief_input_hash).

@app.get("/api/patients/{patient_id}/brief")
def get_brief(patient_id: str):
    try:
        load_patient(patient_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Patient {patient_id} nicht gefunden")

    brief = load_brief(patient_id)
    if brief is None:
        raise HTTPException(404, "Kein Brief vorhanden")

    # Für jedes Feld prüfen, ob die Quelldaten sich seit der Generierung geändert haben
    current_hash = brief_input_hash(patient_id)
    is_stale = {}
    for field in BRIEF_FIELDS:
        stored_hash = brief["meta"]["input_hash_at_generation"].get(field)
        is_stale[field] = stored_hash is not None and stored_hash != current_hash

    return JSONResponse(content={"data": brief, "is_stale": is_stale})


@app.post("/api/patients/{patient_id}/brief/generate")
async def generate_brief(patient_id: str):
    """Generiert alle 6 Brief-Abschnitte auf einmal. LLM antwortet als JSON-Objekt."""
    try:
        patient = load_patient(patient_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Patient {patient_id} nicht gefunden")

    patient_yaml = yaml.safe_dump(
        patient.model_dump(exclude_none=True, mode="json"),
        allow_unicode=True, sort_keys=False, default_flow_style=False, width=100,
    )
    # Meilenstein als zusätzliche Quelle — enthält bereits vom Arzt reviewte Zusammenfassung
    meilenstein = load_meilenstein(patient_id)
    meilenstein_md = meilenstein[0] if meilenstein else ""

    system_prompt = _get_brief_system_prompt()
    user_msg = (
        f"QUELLE — Patient-YAML:\n```\n{patient_yaml}\n```\n\n"
        f"QUELLE — Meilenstein (User-reviewed Übersicht):\n```\n{meilenstein_md}\n```"
    )

    try:
        response = await llm.chat_completion(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}],
            response_format={"type": "json_object"},
            max_tokens=8192,
            temperature=0,
            parallel_tool_calls=False,
        )
    except RateLimitError:
        raise HTTPException(429, "LLM Rate-Limit erreicht. Bitte kurz warten.")
    except APIConnectionError as e:
        raise HTTPException(503, f"LLM nicht erreichbar: {e}")
    except APIStatusError as e:
        raise HTTPException(502, f"LLM API Fehler {e.status_code}: {e.message}")

    raw = (response.choices[0].message.content or "").strip()
    try:
        generated = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(502, f"Modell-Antwort kein valides JSON: {raw[:500]}")

    now = datetime.now(timezone.utc).isoformat()
    current_hash = brief_input_hash(patient_id)
    brief = load_brief(patient_id) or empty_brief_data()

    # Nur Felder übernehmen, die das LLM auch zurückgegeben hat; Metadaten immer aktualisieren
    for field in BRIEF_FIELDS:
        if field in generated:
            brief[field] = generated[field]
        field_hash = hashlib.sha256(brief[field].encode("utf-8")).hexdigest()
        brief["meta"]["generated_at"][field] = now
        brief["meta"]["field_hash_at_generation"][field] = field_hash
        brief["meta"]["input_hash_at_generation"][field] = current_hash

    save_brief(patient_id, brief)
    return JSONResponse(content=brief)


@app.post("/api/patients/{patient_id}/brief/generate/{field}")
async def regenerate_brief_field(patient_id: str, field: str, req: BriefRegenRequest):
    """Regeneriert einen einzelnen Brief-Abschnitt, optional mit Nutzer-Anweisung."""
    if field not in BRIEF_FIELDS:
        raise HTTPException(400, f"Unbekanntes Feld: {field}")
    try:
        patient = load_patient(patient_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Patient {patient_id} nicht gefunden")

    brief = load_brief(patient_id)
    if brief is None:
        raise HTTPException(404, "Brief nicht vorhanden — bitte erst initial generieren")

    patient_yaml = yaml.safe_dump(
        patient.model_dump(exclude_none=True, mode="json"),
        allow_unicode=True, sort_keys=False, default_flow_style=False, width=100,
    )
    meilenstein = load_meilenstein(patient_id)
    meilenstein_md = meilenstein[0] if meilenstein else ""

    label = _BRIEF_FIELD_LABELS[field]
    # Anderen Abschnitte als Kontext mitgeben, damit das LLM keine Inhalte doppelt schreibt
    other_fields_text = "\n\n".join(
        f"[{_BRIEF_FIELD_LABELS[f]}]\n{brief[f]}"
        for f in BRIEF_FIELDS
        if f != field and brief[f]
    )

    user_msg = (
        f"QUELLE — Patient-YAML:\n```\n{patient_yaml}\n```\n\n"
        f"QUELLE — Meilenstein (User-reviewed Übersicht):\n```\n{meilenstein_md}\n```\n\n"
        f'ANFORDERUNG: Generiere ausschließlich den Abschnitt "{label}" neu.\n\n'
        f"Bisheriger Stand:\n```\n{brief[field]}\n```\n\n"
        f"Andere bereits erstellte Abschnitte (Kontext für DRY, NICHT regenerieren, NICHT wiederholen):\n{other_fields_text}"
    )
    if req.custom_prompt:
        user_msg += (
            f"\n\nNUTZER-ANWEISUNG (Vorrang vor Standard-Stilregeln, "
            f"sofern Format-Verbote eingehalten):\n{req.custom_prompt}"
        )

    system_prompt = _get_brief_system_prompt()

    try:
        response = await llm.chat_completion(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}],
            max_tokens=4096,
            temperature=0,
            parallel_tool_calls=False,
        )
    except RateLimitError:
        raise HTTPException(429, "LLM Rate-Limit erreicht. Bitte kurz warten.")
    except APIConnectionError as e:
        raise HTTPException(503, f"LLM nicht erreichbar: {e}")
    except APIStatusError as e:
        raise HTTPException(502, f"LLM API Fehler {e.status_code}: {e.message}")

    new_content = (response.choices[0].message.content or "").strip()
    now = datetime.now(timezone.utc).isoformat()
    current_hash = brief_input_hash(patient_id)

    brief[field] = new_content
    brief["meta"]["generated_at"][field] = now
    brief["meta"]["field_hash_at_generation"][field] = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
    brief["meta"]["input_hash_at_generation"][field] = current_hash

    save_brief(patient_id, brief)
    return JSONResponse(content=brief)


@app.put("/api/patients/{patient_id}/brief/{field}")
def update_brief_field_endpoint(patient_id: str, field: str, req: BriefFieldUpdateRequest):
    """Speichert manuelle Bearbeitungen eines Brief-Felds (Autosave vom Frontend)."""
    if field not in BRIEF_FIELDS:
        raise HTTPException(400, f"Unbekanntes Feld: {field}")
    try:
        load_patient(patient_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Patient {patient_id} nicht gefunden")
    update_brief_field(patient_id, field, req.content)
    return JSONResponse(content={"ok": True})


@app.delete("/api/patients/{patient_id}/brief")
def delete_brief_endpoint(patient_id: str):
    brief = load_brief(patient_id)
    if brief is None:
        raise HTTPException(404, "Kein Brief vorhanden")
    delete_brief(patient_id)
    return JSONResponse(content={"ok": True})


# ── Allgemeiner Chat (kein Patient-Kontext) ───────────────────────────────────

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Einfacher Chat ohne Patient-Kontext — für den allgemeinen Assistenten-Modus."""
    messages = [m.model_dump() for m in request.messages]

    # Server-Sent Events: jedes Text-Token wird sofort ans Frontend gestreamt
    async def event_stream():
        try:
            async for chunk in llm.stream_chat(messages):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except RateLimitError:
            yield "data: [ERROR] Rate-Limit erreicht. Bitte kurz warten.\n\n"
        except APIStatusError as e:
            yield f"data: [ERROR] LLM API Fehler {e.status_code}\n\n"
        except Exception as e:
            yield f"data: [ERROR] {e}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Patienten-Chat mit 2-Pass-Extraktion ─────────────────────────────────────

@app.post("/api/patients/{patient_id}/chat")
async def patient_chat(patient_id: str, req: PatientChatRequest):
    """
    Arzt chattet über einen Patienten.

    Kurze Inputs (≤ CHAT_2PASS_CUTOFF Zeichen): Single-Pass — LLM entscheidet
    selbst ob Tool-Call (→ proposals) oder Text-Antwort (→ reply).

    Lange Inputs (> CHAT_2PASS_CUTOFF): 2-Pass-Pipeline wie Upload-Endpoint.
    Typisch für eingefügte Akte-Texte. Gibt nur proposals + auto_skipped zurück.
    """
    try:
        patient = load_patient(patient_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Patient {patient_id} nicht gefunden")

    user_text = ""
    for m in reversed(req.messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, str):
                user_text = content
            break
    if not user_text:
        raise HTTPException(400, "Keine Benutzernachricht gefunden")

    try:
        if len(user_text) > CHAT_2PASS_CUTOFF:
            # Langer Input → 2-Pass-Pipeline (wie Upload)
            proposals = await extract_proposals(llm, patient, user_text, content_type="text")
            if not proposals:
                return JSONResponse(
                    content={
                        "proposals": [],
                        "auto_skipped": True,
                        "message": "Keine Änderungen vorgeschlagen.",
                        "reply": None,
                    },
                    media_type="application/json; charset=utf-8",
                )
            return JSONResponse(
                content={
                    "proposals": [p.model_dump() for p in proposals],
                    "auto_skipped": False,
                    "reply": None,
                },
                media_type="application/json; charset=utf-8",
            )
        else:
            # Kurzer Input → Single-Pass (Tool-Call oder Text-Antwort)
            proposals, reply = await run_single_pass_chat(llm, patient, user_text, date.today())
            if reply:
                return JSONResponse(
                    content={
                        "proposals": [],
                        "auto_skipped": False,
                        "reply": reply,
                    },
                    media_type="application/json; charset=utf-8",
                )
            if proposals:
                return JSONResponse(
                    content={
                        "proposals": [p.model_dump() for p in proposals],
                        "auto_skipped": False,
                        "reply": None,
                    },
                    media_type="application/json; charset=utf-8",
                )
            return JSONResponse(
                content={
                    "proposals": [],
                    "auto_skipped": True,
                    "message": "Keine Änderungen vorgeschlagen.",
                    "reply": None,
                },
                media_type="application/json; charset=utf-8",
            )
    except RateLimitError:
        raise HTTPException(429, "LLM Rate-Limit erreicht. Bitte kurz warten und erneut versuchen.")
    except APIConnectionError as e:
        raise HTTPException(503, f"LLM nicht erreichbar: {e}")
    except APIStatusError as e:
        raise HTTPException(502, f"LLM API Fehler {e.status_code}: {e.message}")


# ── Dokument-Upload / Extraktion ──────────────────────────────────────────────

_PDF_MIMES = frozenset({"application/pdf"})


@app.post("/api/uploads")
async def upload_document(
    file: UploadFile = File(...),
    patient_id: str | None = Form(None),
):
    """
    2-Pass-basierter Upload-Endpoint.
    Analysiert ein Dokument und gibt Proposals zurück — führt sie NICHT aus.
    patient_id optional: Patientenstand wird als Kongruenz-Kontext mitgegeben.
    Auto-Skip wenn 0 Proposals.
    """
    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in ALLOWED_UPLOAD_MIMES:
        raise HTTPException(400, f"Nicht unterstützter Dateityp: {mime_type}")

    file_bytes = await file.read()

    patient = None
    if patient_id:
        try:
            patient = load_patient(patient_id)
        except FileNotFoundError:
            raise HTTPException(404, f"Patient {patient_id} nicht gefunden")

    if mime_type in _PDF_MIMES:
        content_type: Literal["pdf", "image", "text"] = "pdf"
    else:
        content_type = "image"

    try:
        proposals = await extract_proposals(
            llm, patient, file_bytes, content_type, image_mime_type=mime_type
        )
    except RateLimitError:
        raise HTTPException(429, "LLM Rate-Limit erreicht. Bitte kurz warten.")
    except APIConnectionError as e:
        raise HTTPException(503, f"LLM nicht erreichbar: {e}")
    except APIStatusError as e:
        raise HTTPException(502, f"LLM API Fehler {e.status_code}: {e.message}")

    if not proposals:
        return JSONResponse(
            content={
                "proposals": [],
                "auto_skipped": True,
                "message": "Keine Änderungen vorgeschlagen.",
                "patient_id": patient_id,
            },
            media_type="application/json; charset=utf-8",
        )

    return JSONResponse(
        content={
            "proposals": [p.model_dump() for p in proposals],
            "auto_skipped": False,
            "patient_id": patient_id,
        },
        media_type="application/json; charset=utf-8",
    )



@app.post("/api/extract-stammdaten")
async def extract_stammdaten_endpoint(file: UploadFile = File(...)):
    """
    Single-Pass LLM-Extraktion der Patientenstammdaten aus einem Dokument.
    Alle Felder sind nullable — nicht erkannte Felder kommen als null.
    Kein Error bei Nicht-Patientendokumenten, nur leeres Ergebnis.
    """
    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in ALLOWED_UPLOAD_MIMES:
        raise HTTPException(400, f"Nicht unterstützter Dateityp: {mime_type}")

    file_bytes = await file.read()

    try:
        result = await extract_stammdaten(llm, file_bytes, mime_type)
    except RateLimitError:
        raise HTTPException(429, "LLM Rate-Limit erreicht. Bitte kurz warten.")
    except APIConnectionError as e:
        raise HTTPException(503, f"LLM nicht erreichbar: {e}")
    except APIStatusError as e:
        raise HTTPException(502, f"LLM API Fehler {e.status_code}: {e.message}")

    return JSONResponse(
        content=result.model_dump(mode="json"),
        media_type="application/json; charset=utf-8",
    )


@app.post("/api/patients/{patient_id}/apply-tools")
async def apply_tools(patient_id: str, req: ApplyToolsRequest):
    """
    Führt eine Liste von Tool-Calls direkt aus — ohne LLM-Beteiligung.
    Wird aufgerufen, wenn der Arzt Upload-Proposals bestätigt.
    Gibt pro Call das Ergebnis zurück (ok + summary oder error).
    """
    try:
        load_patient(patient_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Patient {patient_id} nicht gefunden")

    results = []
    for call in req.calls:
        tool = call.get("tool")
        args = call.get("args", {})

        if tool not in TOOL_FUNCTIONS:
            results.append({"tool": tool, "ok": False, "error": f"Unknown tool: {tool}"})
            continue

        fn = TOOL_FUNCTIONS[tool]
        try:
            result = fn(patient_id, **args)
            results.append({"tool": tool, **result})
        except TypeError as e:
            results.append({"tool": tool, "ok": False, "error": f"Argument error: {e}"})
        except Exception as e:
            results.append({"tool": tool, "ok": False, "error": str(e)})

    return JSONResponse(
        content={"results": results},
        media_type="application/json; charset=utf-8",
    )


_IDENTITY_FIELDS: frozenset[str] = frozenset({"name", "geburtsdatum", "geschlecht"})


def _detect_mismatch(patient: Patient, proposals: list[Proposal]) -> list[dict]:
    """Checks update_stammdaten proposals against current patient identity fields.

    Returns a list of {feld, current, proposed} for fields where the current
    value is non-empty and differs from the proposed value. Empty list = no conflict.
    When multiple proposals target the same field, the last one wins.
    """
    proposed: dict[str, object] = {}
    for p in proposals:
        if (
            p.type == "update_singleton"
            and p.call is not None
            and p.call.tool == "update_stammdaten"
        ):
            feld = p.call.args.get("feld")
            if feld in _IDENTITY_FIELDS:
                proposed[str(feld)] = p.call.args.get("wert")

    if not proposed:
        return []

    conflicts = []
    for feld, proposed_raw in proposed.items():
        current_raw = getattr(patient.stammdaten, feld, None)
        if current_raw is None:
            continue
        current_str = str(current_raw)
        if not current_str:
            continue
        proposed_str = str(proposed_raw) if proposed_raw is not None else ""
        if current_str != proposed_str:
            conflicts.append({"feld": feld, "current": current_str, "proposed": proposed_str})

    return conflicts


def _run_tool(patient_id: str, tool: str, args: dict) -> dict:
    """Führt ein einzelnes Tool aus und gibt das Ergebnis zurück."""
    fn = TOOL_FUNCTIONS.get(tool)
    if fn is None:
        return {"ok": False, "error": f"Unknown tool: {tool}"}
    try:
        return fn(patient_id, **args)
    except TypeError as e:
        return {"ok": False, "error": f"Argument error: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _to_apply_result(proposal_type: str, run_result: dict, summary_override: str | None = None) -> dict:
    """Normalisiert das Tool-Ergebnis auf das ApplyResult-Schema (immer `summary`, nie `error`)."""
    out: dict[str, Any] = {"type": proposal_type, "ok": run_result.get("ok", False)}
    if "id" in run_result:
        out["id"] = run_result["id"]
    out["summary"] = summary_override or run_result.get("summary") or run_result.get("error", "")
    return out


# delete_entry meldet eine fehlende ULID mit dieser Fehlermeldung — bei "update"
# behandeln wir das als Erfolg (gewünschter Endzustand: alter weg, neuer da).
_DELETE_ID_NOT_FOUND_MARKER = "Keine Liste enthält Eintrag mit id="


@app.post("/api/patients/{patient_id}/apply-proposals")
async def apply_proposals_endpoint(patient_id: str, req: ApplyProposalsRequest):
    """
    Führt eine Liste von Proposals aus — versteht Update-Gruppen (delete + add).

    Bei type="update" wird ZUERST `add_call` ausgeführt, danach `delete_call`.
    Schlägt add fehl → kein delete (Datenverlust ausgeschlossen).
    Schlägt delete fehl, weil die ID schon weg ist → wird als Erfolg gewertet.
    Schlägt delete aus anderen Gründen fehl → ok=false mit Hinweis auf manuelle Prüfung.
    """
    try:
        patient_snapshot = load_patient(patient_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Patient {patient_id} nicht gefunden")

    if not req.force:
        conflicts = _detect_mismatch(patient_snapshot, req.proposals)
        if conflicts:
            return JSONResponse(
                status_code=409,
                content={"mismatch_warning": True, "conflicting_fields": conflicts},
                media_type="application/json; charset=utf-8",
            )

    results = []
    for proposal in req.proposals:
        if proposal.type == "update":
            if proposal.delete_call is None or proposal.add_call is None:
                results.append({
                    "type": "update",
                    "ok": False,
                    "summary": "Fehlende delete_call oder add_call",
                })
                continue
            add_result = _run_tool(patient_id, proposal.add_call.tool, proposal.add_call.args)
            if not add_result.get("ok"):
                results.append(_to_apply_result("update", add_result))
                continue
            del_result = _run_tool(patient_id, proposal.delete_call.tool, proposal.delete_call.args)
            if del_result.get("ok"):
                results.append(_to_apply_result("update", add_result))
                continue
            err = del_result.get("error", "") or ""
            if _DELETE_ID_NOT_FOUND_MARKER in err:
                results.append(_to_apply_result("update", add_result))
            else:
                id_suffix = (proposal.delete_call.args.get("id") or "")[-6:]
                results.append(_to_apply_result(
                    "update",
                    {"ok": False, "id": add_result.get("id")},
                    summary_override=(
                        f"Update teilweise — Eintrag {id_suffix} konnte nicht entfernt werden, "
                        f"manuell prüfen."
                    ),
                ))
        else:
            if proposal.call is None:
                results.append({"type": proposal.type, "ok": False, "summary": "Fehlende call"})
                continue
            run_result = _run_tool(patient_id, proposal.call.tool, proposal.call.args)
            results.append(_to_apply_result(proposal.type, run_result))

    return JSONResponse(
        content={"results": results},
        media_type="application/json; charset=utf-8",
    )
