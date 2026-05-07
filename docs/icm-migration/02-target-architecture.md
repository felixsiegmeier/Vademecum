# 02 — Ziel-Architektur: arztbrief-app nach ICM-Migration

ICM = Interpretable Context Methodology — filesystem-zentrierte Pipeline-Design-Philosophie.

---

## Vokabular (bindend für diese Codebasis)

| Begriff | Definition |
|---------|-----------|
| **Workflow** | Nutzer-ausgelöste Aufgabe von Anfang bis Ende (z.B. "Arztbrief generieren") |
| **Stage** | Nummerierter Schritt innerhalb eines Workflows (deterministisch oder LLM) |
| **Skill** | Einzelner LLM-Prompt + Schema, wiederverwendbar über Workflows hinweg |
| **Task** | Deterministischer Schritt ohne LLM (Daten laden, rendern, validieren) |
| **Tool** | Python-Funktion mit Pydantic-Args, die das Patientenmodell mutiert |
| **Agent** | **Darf nicht im Ziel-Code erscheinen.** Jedes Vorkommen ist ein Refactoring-Kandidat. |

---

## Sprach-Regel (M3)

Hybride Namenskonvention: technische Strukturen auf Englisch, Domain-Konzepte auf Deutsch.

| Ebene | Sprache | Beispiele |
|-------|---------|-----------|
| Tech-Strukturen (Top-Level) | Englisch | `data/`, `workflows/`, `skills/`, `tests/`, `utils/` |
| Domain-Daten-Container | Deutsch | `data/briefe/`, `data/patienten/`, `data/lernlog/`, `data/learning_snapshots/` |
| Domain-Begriffe innerhalb Workflows | Deutsch | `workflows/brief/diagnosen/`, `verlauf/`, `anamnese/` |
| API-Routen | Englisch-Topologie + deutsche Domain-Begriffe | `/api/brief/{id}/diagnosen`, `/api/patienten/{id}` |
| Code-Identifier | Englisch-Verben + deutsche Domain-Substantive | `def generate_diagnosen()`, `class DiagnosenOutput`, `def render_verlauf()` |

Konkrete Umbenennungen (umzusetzen in Schritt 0.3):
- `data/briefs/` → `data/briefe/` (bereits in `data/briefe/` vorhanden, `data/briefs/` ist redundant)
- `data/patients/` → `data/patienten/`

---

## README-Pflicht (M1)

Jeder neu angelegte Folder bekommt eine `README.md` (3–10 Zeilen: was passiert hier, welche Dateien erwartet, Verweis auf AGENTS.md). Gilt für:
- alle Workflow-, Section-, Compound-Stage-, Sub-Stage-Folder
- `skills/learning/`
- `data/learning_snapshots/`
- alle `lernlog/`-Ordner (dort ist README.md ohnehin Pflicht als committed Whitelist-Begleiter)

---

## Ziel-Verzeichnisbaum

```
backend/
├── main.py                          # FastAPI-App (unverändert als HTTP-Schicht)
├── llm_client.py                    # LLM-Factory + gecachte Clients (erweitert, s. unten)
├── models/
│   └── patient.py                   # Unverändert
├── storage.py                       # Nur Patienten/Meilenstein/Hash — Brief-Alt-Teil entfernt¹
├── brief_storage.py                 # Unverändert (Neu-Brief-Persistenz)
├── learning_storage.py              # Aktualisiert: zwei Pfad-Funktionen; utils/ulid.py importieren
│
├── utils/
│   ├── ulid.py                      # Zentrale ULID-Implementierung (kein Duplikat)
│   ├── prompts.py                   # Frontmatter-Parsing, _get_prompt(), Validierung
│   └── auth_context.py              # Multi-User-Middleware: user_id-Auflösung
│
├── tools/
│   └── patient_tools.py             # Umbenennung von agent_tools.py
│
├── skills/                          # Nur cross-cutting Skills (in ≥ 2 Workflows nutzbar)
│   └── learning/
│       ├── __init__.py              # exportiert from_edits() und rebuild()
│       ├── README.md
│       ├── extract.py               # extract_rule_candidates
│       ├── conflict.py              # detect_conflict
│       ├── rebuild.py               # rebuild_rule_candidate
│       ├── schemas.py               # RuleExtractionOutput, ConflictOutput, RebuildOutput
│       └── prompts/
│           ├── rule_extraction.md
│           ├── conflict_detection.md
│           └── rule_rebuild.md
│
├── workflows/
│   ├── brief/
│   │   ├── orchestrator.py          # WF-3: generate_brief, generate_section, polish, learn_from_edits
│   │   ├── README.md
│   │   ├── diagnosen/
│   │   │   ├── prompt.md
│   │   │   ├── schema.py            # DiagnosenOutput
│   │   │   ├── skill.py             # async def run(llm, patient, ...) → str
│   │   │   ├── README.md
│   │   │   └── lernlog/
│   │   │       ├── .gitignore       # Whitelist
│   │   │       ├── README.md
│   │   │       ├── example.yml
│   │   │       └── default.yml      # gitignored
│   │   ├── anamnese/
│   │   │   ├── prompt.md
│   │   │   ├── skill.py             # Plain-Text-Skill, kein schema.py
│   │   │   ├── README.md
│   │   │   └── lernlog/
│   │   ├── therapie/
│   │   │   ├── prompt.md
│   │   │   ├── schema.py            # TherapieOutput
│   │   │   ├── skill.py
│   │   │   ├── README.md
│   │   │   └── lernlog/
│   │   ├── befunde/
│   │   │   ├── prompt.md
│   │   │   ├── skill.py             # kein lernlog/ — befunde nicht lernfähig (s. unten)
│   │   │   └── README.md
│   │   └── verlauf/                 # COMPOUND STAGE
│   │       ├── orchestrator.py      # ruft die 3 Passes der Reihe nach
│   │       ├── README.md
│   │       ├── lernlog/             # auf Compound-Level, nicht in Sub-Stages
│   │       │   ├── .gitignore
│   │       │   ├── README.md
│   │       │   ├── example.yml
│   │       │   └── default.yml      # gitignored
│   │       ├── 01_collect/
│   │       │   ├── prompt.md
│   │       │   ├── skill.py
│   │       │   └── README.md
│   │       ├── 02_audit/
│   │       │   ├── prompt.md
│   │       │   ├── skill.py
│   │       │   └── README.md
│   │       └── 03_curate/
│   │           ├── prompts/
│   │           │   ├── shared.md              # gemeinsamer Basis-Block
│   │           │   ├── minimal.md             # Frontmatter: description
│   │           │   ├── kompakt.md             # Frontmatter: description
│   │           │   └── ausfuehrlich.md        # Frontmatter: description
│   │           ├── schema.py                  # CollectOutput mit curate_variant-Validator
│   │           ├── skill.py                   # lädt Variante dynamisch; ?adressat überschreibt
│   │           └── README.md
│   ├── document_extraction/
│   │   ├── orchestrator.py          # WF-1: extract_proposals(_streaming)
│   │   ├── tool_loop.py             # Multi-Turn-Loop (aus agent_extraction_core.py)
│   │   └── README.md
│   ├── meilenstein/
│   │   ├── orchestrator.py          # WF-2: generate_meilenstein (dünne Hülle um Skill)
│   │   └── README.md
│   ├── patient_chat/
│   │   ├── orchestrator.py          # WF-4: chat (routing + single-pass + 2-pass)
│   │   ├── prompt.md                # Chat-System-Prompt (aus agent_patient_chat.py extrahiert)
│   │   └── README.md
│   └── stammdaten_extraction/
│       ├── orchestrator.py          # WF-5: extract_stammdaten (dünne Hülle)
│       ├── schema.py                # StammdatenExtractResult
│       └── README.md
│
├── data/                            # gitignored (datenschutzsensitiv)
│   ├── patienten/                   # Patient-YMLs (umbenannt von patients/)
│   ├── meilensteine/
│   ├── briefe/                      # Brief-Snapshots (umbenannt von briefs/)
│   ├── chat/
│   ├── lernlog/                     # Aggregierte Lernlog-Einträge
│   ├── audit/
│   └── learning_snapshots/          # NEU: Patient-Snapshots (vorher: data/learnings/*/last/)
│       ├── README.md
│       ├── brief/
│       │   └── <P-NNNN>.yml         # { diagnosen: "...", anamnese: "...", ... }
│       └── meilenstein/
│           └── <P-NNNN>.yml         # { content: "..." }
│
└── tests/                           # Unverändert (Pfad-Anpassungen, keine Test-Logik-Änderung)
    └── conftest.py

¹ storage.py: BRIEF_FIELDS / save_brief / load_brief / delete_brief entfernen sobald Alt-System abgeschaltet (Schritt 5.1, nach Phase 1 vorgezogen)
```

---

## utils/prompts.py — Frontmatter-Validierung (F2, M2)

Alle `.txt`-Prompts werden in `.md` umbenannt und erhalten YAML-Frontmatter. `utils/prompts.py` ist die zentrale Lade- und Validierungs-Schicht. `_get_prompt()` lebt fortan hier, nicht in den einzelnen Agents.

### Pflichtfelder (Pydantic-Schema)

```python
# utils/prompts.py
from pydantic import BaseModel
from typing import Literal

class PromptFrontmatter(BaseModel):
    id: str
    version: str           # ISO-Datum: "2026-05-07"; mehrere Änderungen: "2026-05-07-2"
    model: str             # bindend — Orchestrator liest dieses Feld zur Client-Auflösung
    role: Literal["user", "system"]
    inputs: list[str]      # alle {platzhalter} im Prompt-Body
    description: str = ""  # optional, aber empfohlen
```

`_get_prompt()` validiert das Frontmatter beim ersten Laden. `ValidationError` → Exception (kein Silent-Fallback).

### Beispiel-Frontmatter

```yaml
---
id: brief.diagnosen
version: 2026-05-07
model: gemini-3-flash-lite-preview
role: user
inputs: [patient_yaml, gelernte_regeln, extra_context]
description: "Extrahiert Diagnosen aus Patient-YAML als strukturiertes JSON."
---
```

### Optionale Felder

```yaml
schema_path: workflows/brief/diagnosen/schema.py   # bei JSON-Mode-Skills
response_format: json_object                        # bei JSON-Mode-Skills
temperature: 0
max_tokens: 1024
workflow: brief                                     # Zugehörigkeit (Dokumentation)
stage: 1                                            # Reihenfolge im Workflow
```

### Konventionen

- `id` entspricht dem Datei-Stem (ohne `.md`), mit Workflow-Prefix (z.B. `brief.diagnosen`).
- `version` ist ein ISO-Datum (`2026-05-07`). Bei mehreren Änderungen am selben Tag: Postfix `-2`, `-3` usw.
- `model` ist bindend: der Orchestrator liest dieses Feld, holt den passenden Client von der `llm_client.py`-Factory und übergibt ihn an den Skill.
- `inputs` listet alle `{platzhalter}` im Prompt-Body auf.
- Curate-Varianten-Prompts (`minimal.md`, `kompakt.md`, `ausfuehrlich.md`) haben ein `description`-Feld — dieses wird zur Laufzeit für den `{{ available_variants }}`-Platzhalter in Pass-1 gerendert.

---

## llm_client.py — Factory-Muster (F3)

Der Lazy-Singleton `_lite()` in `agent_brief.py` wird ersetzt durch eine Factory in `llm_client.py` mit Cache per `(provider, model)`.

```python
# llm_client.py (Erweiterung)

_client_cache: dict[tuple[str, str], LLMClient] = {}

def get_client(model: str, provider: str | None = None) -> LLMClient:
    """Gibt einen gecachten LLMClient für (provider, model) zurück.
    provider=None → Default aus LLM_BACKEND Env-Variable.
    """
    key = (provider or _default_provider(), model)
    if key not in _client_cache:
        _client_cache[key] = LLMClient(model=model, provider=provider)
    return _client_cache[key]
```

**Fluss:**
1. Orchestrator liest `model`-Feld aus Frontmatter des Skill-Prompts.
2. Orchestrator ruft `llm_client.get_client(model)` auf.
3. Gecachter Client wird an `skill.run(llm, ...)` übergeben.
4. `main.py` ruft beim App-Start einmal `llm_client.validate_connection()` (oder äquivalent) auf — keine explizite Client-Initialisierung.

---

## Curate-Varianten-Konzept (F4.2)

`SUBSTANZ_TIEFE` (Regex-Signal) und Adressaten-Profile werden zu einem einheitlichen `curate_variant`-Konzept zusammengeführt. Das Konzept ist user-erweiterbar.

### Verzeichnis-Struktur

```
workflows/brief/verlauf/03_curate/prompts/
  shared.md          # gemeinsamer Basis-Block (Jinja-Platzhalter {{ available_variants }})
  minimal.md         # Frontmatter: description: "Kurz, 3-5 Sätze"
  kompakt.md         # Frontmatter: description: "Ausgewogen, 8-12 Sätze"
  ausfuehrlich.md    # Frontmatter: description: "Vollständig, alle Details"
```

Weitere `.md`-Dateien in diesem Ordner werden automatisch als Varianten erkannt (user-erweiterbar).

### Pass-1-Output-Schema (CollectOutput)

```python
# workflows/brief/verlauf/03_curate/schema.py

from pathlib import Path
from pydantic import BaseModel, field_validator

CURATE_PROMPTS_DIR = Path(__file__).parent / "prompts"

class CollectOutput(BaseModel):
    substance: str
    curate_variant: str

    @field_validator("curate_variant")
    @classmethod
    def must_match_available(cls, v: str) -> str:
        available = [p.stem for p in CURATE_PROMPTS_DIR.glob("*.md")
                     if p.stem != "shared"]
        if v not in available:
            raise ValueError(f"Unbekannte Variante '{v}'; verfügbar: {available}")
        return v
```

### Varianten-Override via Query-Parameter

`?adressat=minimal` erzwingt eine bestimmte Variante (statt LLM-Wahl in Pass 1). Parametername bleibt `adressat` für API-Kompatibilität, intern wird er als `curate_variant` behandelt.

### Was entfällt

- `_extract_substanz_tiefe()` (Regex) → weg
- `_load_curate_prompt()` → weg (Logik in `03_curate/skill.py`)
- `prompts/adressaten/normalstation_intern.md` → wird in Schritt 4.2 integriert oder umgestrukturiert

---

## utils/auth_context.py — Multi-User-Middleware (F15)

```python
# utils/auth_context.py

from fastapi import Request

async def get_user_id(request: Request) -> str:
    """Löst user_id auf. MULTI_USER=false → immer 'default'."""
    import os
    if os.getenv("MULTI_USER", "false").lower() != "true":
        return "default"
    # MULTI_USER=true: aus Session/JWT lesen (Implementierung TBD)
    return request.state.user_id
```

`.env`-Flag `MULTI_USER=true|false` (Default: `false`):
- `false`: injiziert immer `user_id="default"` — kein Multi-User-Overhead
- `true`: liest `user_id` aus Session/JWT (Implementierung in `auth_context.py`)

`user_id` wird als expliziter Parameter durch alle Skill-, Storage- und Orchestrator-Signaturen durchgereicht. Skills und Storage bleiben in beiden Modi identisch — nur die Middleware ändert sich.

---

## Streaming-Transport-Übersicht (F11)

Die Transport-Inkonsistenz zwischen den Endpoints ist bewusst und wird im ICM-Refactoring nicht geändert.

| Endpoint | Transport | Begründung |
|----------|-----------|------------|
| `POST /api/patients/{id}/meilenstein/generate` | SSE (`text/event-stream`) | Etabliertes Pattern, Frontend-Code stabil |
| `POST /api/uploads` | NDJSON (`application/x-ndjson`, chunked) | POST-Body + Tool-Calling-Loop; SSE nicht sinnvoll bei POST |
| `POST /api/patients/{id}/chat` (1-Pass) | Synchron JSON | Kurze Antwort, kein Streaming nötig |
| `POST /api/patients/{id}/chat` (2-Pass) | NDJSON (wie Uploads) | Fällt auf document_extraction-Loop zurück |

**Designentscheidung:** Harmonisierung auf einen Transport würde Breaking Frontend-Änderungen erfordern und ist kein ICM-Ziel. Dokumentiert als bewusste Entscheidung in `backend/AGENTS.md`.

---

## `update_status` — Sicherheitskommentar (F6)

`update_status` ist in `TOOL_FUNCTIONS` (ausführbar via UI), aber **nicht** in `TOOL_SCHEMAS` (LLM sieht es nicht). Das ist eine bewusste Sicherheitsentscheidung: Das LLM soll den Patientenstatus (`aktiv`) nie eigenständig setzen können — das ist eine reine User-Entscheidung (entlassene Patienten manuell deaktivieren).

Dokumentiert explizit in `backend/AGENTS.md` mit dem Kommentar:
```python
# SICHERHEIT: update_status bewusst nicht in TOOL_SCHEMAS.
# Das LLM darf den aktiv-Status eines Patienten nie eigenständig ändern.
# Nur über UI erreichbar.
```

---

## `befunde` — Lernlog-Ausnahme (F5)

`befunde` ist explizit aus `BRIEF_SECTIONS_WITH_LEARNING` ausgeschlossen. Das ist eine fachliche Entscheidung: Befunde-Formatierung ist eine reine SAP-Text-Übernahme ohne generalisierbares Lernpotenzial. Kein API-Endpoint `/api/learn/brief/befunde/*`. Dokumentiert in `backend/AGENTS.md`.

---

## AGENTS.md-Skeleton (Root-Level)

Diese Datei ist die primäre Konventions-Dokumentation für Claude Code und andere KI-Assistenten, die am Repo arbeiten.

```markdown
# AGENTS.md

## Projektkontext
Kardiologische ICU-Dokumentationshilfe (DHZC Berlin).
Vokabular: Workflow, Stage, Skill, Task, Tool. Das Wort "Agent" erscheint nicht in neuem Code.

## Backend-Konventionen

### Workflows (`backend/workflows/`)
- Ein `orchestrator.py` pro Workflow-Ordner.
- Bei Compound-Stages (z.B. `verlauf`): eigene `orchestrator.py` im Compound-Stage-Ordner.
- Stages sind nummeriert und sequenziell (kein paralleles Stage-Spawning).
- Orchestratoren importieren Skills, keine anderen Orchestratoren.
- Kein YAML-Runner, kein generisches Orchestrierungs-Framework.
- `main.py` ruft immer den Orchestrator, nie einzelne Skills direkt — auch nicht für Lern-Endpunkte.
- Lernen ist eine Methode des Orchestrators (`brief.learn_from_edits(...)`), die intern an
  `skills.learning.from_edits(...)` delegiert.

### Skills (workflow-spezifisch vs. cross-cutting)
- **Workflow-spezifischer Skill** → `workflows/<wf>/<section>/skill.py`.
- **Cross-cutting Skill** (in ≥ 2 Workflows nutzbar) → `skills/<name>/`.
- Faustregel: Starte unter `workflows/`, promote zu `skills/` erst bei tatsächlicher zweiter Verwendung.
- Aktuell qualifiziert sich nur "Lernen" als cross-cutting: `skills/learning/`.
- Jeder Skill hat eine `run(llm, ...)` Funktion (immer `async`).
- Skills geben immer einen primitiven Typ zurück (str, dict, Pydantic-Modell).
- Skills haben keine Seiteneffekte (kein Storage-Zugriff).
- Frontmatter wird von `_get_prompt()` gestripped — Skills sehen nur den Body.

### Tools (`backend/tools/patient_tools.py`)
- Jede Tool-Funktion: `load_patient → mutate → save_patient`.
- Pydantic-Args-Modell pro Tool; JSON-Schema aus `model_json_schema()` generieren.
- ULID-Generierung immer via `utils.ulid.generate_ulid()`.

### Prompts (in den jeweiligen Section-Ordnern)
- Dateiformat: Markdown mit YAML-Frontmatter.
- `_get_prompt()` bevorzugt `.md` über `.txt` (Backwards-Compat).
- Platzhalter-Format: `{snake_case}`.
- Kein Prompt als Python-String — alle Prompts als Dateien.

### Schemas (`schema.py` im jeweiligen Section-Folder)
- Pydantic-Modelle für LLM-JSON-Mode-Outputs.
- Import ist immer relativ: `from .schema import DiagnosenOutput`.
- Renderer (`_render_diagnosen`, `_render_therapie`) leben im jeweiligen `skill.py` — keine geteilten Helpers (`workflows/_helpers.py` existiert nicht).
- Regex-Parsing von LLM-Output ist verboten. Immer `model_validate_json(raw)`.

### Lernlog
- **Patient-Snapshots:** `data/learning_snapshots/<workflow>/<P-NNNN>.yml` (gitignored).
- **User-Regelmengen:** `workflows/<wf>/<section>/lernlog/<user>.yml` (gitignored via Whitelist).
- Whitelist-`.gitignore` in jedem `lernlog/`-Ordner committed.
- Bei Compound-Stages: Lernlog auf Compound-Level, nicht in Sub-Stages.
- `learning_storage.py` hat zwei separate Pfad-Funktionen:
  `_snapshot_path(workflow, pid)` und `_rules_path(workflow, section, user)`.

### Tests
- Alle Tests via `pytest`.
- `isolated_data`-Fixture für alle Storage-Tests.
- Prompt-Inhalts-Asserts schützen vor versehentlichem Löschen von Schlüssel-Klauseln.

## Verbotene Muster
- `import agent_*` — alte Dateinamen nicht in neuem Code verwenden.
- Prompts als Python-String-Templates (`string.Template`, `f-string`).
- Tool-Calling-Loop ohne `max_iterations` und `max_total_tokens`.
- Direktes Schreiben in `data/` ohne atomares `tmp + os.replace`.
- `update_status` darf kein Tool-Schema erhalten (Sicherheitsentscheidung: LLM soll Patientenstatus nie deaktivieren).
- Regex- oder String-Split-Parsing von LLM-Freitext-Output — immer Pydantic.
- `skill.md` als Dateiname — Skills sind immer `skill.py` (Python-Module, keine Markdown-Beschreibungen).
- Orchestratoren in Section-Foldern — `orchestrator.py` existiert nur auf Workflow- oder Compound-Stage-Ebene.
```

---

## Tool-Konventionen

### Signatur-Schema

```python
# tools/patient_tools.py
from pydantic import BaseModel, Field
from typing import Optional

class AddBehandlungsdiagnoseArgs(BaseModel):
    patient_id: str
    text: str
    datum: Optional[str] = None
    source_quote: str

def add_behandlungsdiagnose(args: AddBehandlungsdiagnoseArgs) -> dict:
    patient = storage.load_patient(args.patient_id)
    # mutate
    storage.save_patient(patient)
    return {"ok": True, "id": new_id}
```

Das JSON-Schema für die LLM-API wird aus `AddBehandlungsdiagnoseArgs.model_json_schema()` generiert, nicht handgepflegt. `TOOL_SCHEMAS` bleibt als Registry, ihre Inhalte werden aber aus den Pydantic-Modellen abgeleitet.

### OpenAI-Strict-Mode-Schemas

- Alle Tool-Schemas in `TOOL_SCHEMAS` (Liste von dicts), generiert via `model_json_schema()`.
- `_wrap(name, description, properties, required)` erzeugt strict=True-Schema.
- `TOOL_FUNCTIONS: dict[str, Callable]` für Dispatch.
- `update_status` bleibt in `TOOL_FUNCTIONS`, nicht in `TOOL_SCHEMAS`.

### ULID

```python
from utils.ulid import generate_ulid
new_id = generate_ulid()
```

---

## Workflow-Orchestrator-Konventionen

### Struktur

```python
# workflows/brief/orchestrator.py

"""Brief-Workflow: 4 parallele Skills + 3-stufiger Verlauf-Pass."""

from workflows.brief.diagnosen import skill as diagnosen_skill
from workflows.brief.anamnese import skill as anamnese_skill
from workflows.brief.therapie import skill as therapie_skill
from workflows.brief import verlauf  # Compound-Stage-Orchestrator
import skills.learning as learning

async def generate_brief(patient: Patient, extra_context: str = "", ...) -> dict:
    """Stage 1-4 parallel, Stage 5-7 sequenziell."""
    # Stage 1: Diagnosen
    # Stage 2: Anamnese
    # Stage 3: Therapie
    # Stage 4: Befunde-Formatierung
    # Stage 5-7: Verlauf (delegiert an verlauf/orchestrator.py)
    ...

async def learn_from_edits(section: str, patient_id: str, original: str, edited: str, user_id: str = "default") -> dict:
    """Delegiert an skills.learning.from_edits(...)."""
    return await learning.from_edits(workflow="brief", section=section,
                                     patient_id=patient_id, original=original,
                                     edited=edited, user_id=user_id)
```

### Import-Konvention

```python
from workflows.brief import orchestrator as brief
# main.py ruft:
await brief.generate_brief(patient, ...)
await brief.learn_from_edits(section, ...)
```

### Slim-Orchestrator-Prinzip

- Orchestratoren enthalten **keine** Prompt-Texte.
- Orchestratoren enthalten **keine** LLM-Calls direkt — nur Skill-Aufrufe.
- Orchestratoren können deterministisch Daten aufbereiten (z.B. `_to_yaml`, `_inject_extra_context`).
- Orchestratoren persistieren das Ergebnis (via `learning_storage.save_snapshot`, `brief_storage.update_section`).
- `main.py` ruft immer den Orchestrator, nie einzelne Skills direkt.

---

## Skill-Konventionen

### Struktur

```python
# workflows/brief/diagnosen/skill.py

"""Skill: generate_diagnosen — JSON-Mode → Markdown."""

from llm_client import LLMClient
from models.patient import Patient
from .schema import DiagnosenOutput

PROMPT_FILE = "prompt.md"

async def run(
    llm: LLMClient,
    patient: Patient,
    rules_block: str = "",
    extra_context: str = "",
) -> str:
    """Gibt gerendertes Markdown zurück."""
    prompt = _build_prompt(PROMPT_FILE, patient, rules_block, extra_context)
    resp = await llm.chat_completion(
        [{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0, max_tokens=1024,
    )
    raw = resp.choices[0].message.content or "{}"
    parsed = DiagnosenOutput.model_validate_json(raw)
    return _render_diagnosen(parsed)
```

**Wichtig:** `from .schema import DiagnosenOutput` ist ein relativer Import, weil `schema.py` im selben Section-Folder lebt — nicht `from schemas.diagnosen_output`.

**Invarianten:**
- Jeder Skill hat eine `PROMPT_FILE`-Konstante (Dateiname relativ zum Skill-Ordner).
- Jeder Skill hat eine `run(llm, ...)` Funktion.
- JSON-Mode-Skills validieren LLM-Output immer gegen ein Pydantic-Modell aus `schema.py`. Kein Silent-Fallback. `ValidationError` → Exception an Caller.
- Skills werfen Exceptions bei LLM-Fehler — Orchestrator fängt und handhabt sie.

---

## Lernlog-Konventionen (Ziel)

### Zwei Datenarten

Das Lernlog ist architektonisch in zwei Datenarten getrennt:

#### Datenart 1 — Patient-Snapshots

```
data/learning_snapshots/           # gitignored, datenschutzsensitiv
  brief/
    <P-NNNN>.yml                   # { diagnosen: "...", anamnese: "...", ... }
  meilenstein/
    <P-NNNN>.yml                   # { content: "..." }
```

- Kein `user_id`-Segment: Patienten sind nicht user-separiert.
- Format: `.yml` mit allen Sektionen in einer Datei pro Patient.
- Migriert aus: `data/learnings/default/<workflow>/*/last/<pid>.txt`.

#### Datenart 2 — User-Regelmengen

```
workflows/brief/diagnosen/lernlog/
  .gitignore          # Whitelist (committed): *, !.gitignore, !README.md, !example.yml
  README.md           # erklärt Format (committed)
  example.yml         # anonymisiertes Beispiel (committed)
  default.yml         # Felix' eigene Regeln (gitignored)
```

- Eine Datei pro User pro Sektion. Filename = user_id (z.B. `default.yml`).
- Bei Compound-Stages (Verlauf): Lernlog auf Compound-Level (`workflows/brief/verlauf/lernlog/`).
- Whitelist-`.gitignore`-Inhalt (für jeden `lernlog/`-Ordner):
  ```
  *
  !.gitignore
  !README.md
  !example.yml
  ```

### `learning_storage.py`-Pfad-Funktionen

```python
def _snapshot_path(workflow: str, pid: str) -> Path:
    return DATA_DIR / "learning_snapshots" / workflow / f"{pid}.yml"

def _rules_path(workflow: str, section: str, user: str) -> Path:
    return WORKFLOWS_DIR / workflow / section / "lernlog" / f"{user}.yml"
```

### Lernfähige Sektionen (unverändertes Constraint)

- `BRIEF_SECTIONS_WITH_LEARNING = {"diagnosen", "anamnese", "therapie", "verlauf"}` — `befunde` bleibt ausgeschlossen.
- Regeln werden **nur in Pass 3 (curate)** injiziert, nie in Pass 1 (collect) oder Pass 2 (audit).

---

## Ausschlüsse (was sich NICHT ändert)

Diese Komponenten werden in der ICM-Migration **nicht** angefasst:

| Komponente | Begründung |
|-----------|-----------|
| `main.py` HTTP-Schicht | Nur Import-Pfade anpassen, keine Logik-Änderung |
| `llm_client.py` | Erweitert um Factory-Muster (s. oben), sonst stabil |
| `models/patient.py` | Schema-Version 0.4 bleibt |
| `storage.py` (Patient/Meilenstein-Teil) | Kritische Infrastruktur, kein Umbau ohne separaten Plan |
| `brief_storage.py` | Neu-Brief-System ist bereits ICM-kompatibel |
| `learning_storage.py` | Aktualisiert nur für neue Pfad-Funktionen und ULID-Import |
| Prompt-Inhalte | Nur Frontmatter hinzufügen — keine inhaltlichen Änderungen |
| Frontend | Vollständig außerhalb ICM-Scope |
| Test-Logik | Tests werden **nicht** umgebaut — nur Pfad-Anpassungen bei Umbenennungen |
| Alt-Brief-System (`/api/patients/{id}/brief/*`) | Wird in Schritt 5.1 (nach Phase 1 vorgezogen) vollständig entfernt. Kein Compat-Layer. |
