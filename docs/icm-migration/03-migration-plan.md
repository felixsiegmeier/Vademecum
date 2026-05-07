# 03 — Migrationsplan: arztbrief-app → ICM

Nummerierte Schritte mit Aufwand, Abhängigkeiten, Rollback und Test-Anforderungen.
Kein Schritt ändert Produktionsverhalten — alle Schritte sind rein strukturelle Refactorings
oder additive Ergänzungen, sofern nicht anders angegeben.

**Grundsatz:** Jeder Schritt ist einzeln commit-bar und hinterlässt den Test-Stand grün.

---

> **Hinweis: Schritt 4.1 (R-2-Bug-Fix) bereits erledigt**
> Der R-2-Bug-Fix (`brief_verlauf_curate.txt`-Referenz in `main.py`) wurde auf einem separaten Branch off `main` gefixt und gemerged, bevor der ICM-Branch begann. Wenn du diesen Plan abarbeitest, ist Schritt 4.1 bereits erledigt — überspringen.

---

## Pre-Decisions

### Architektur und Grundsätze

- **Kein Thin-Wrapper-Pattern.** Jeder Umzug stellt `main.py` direkt um.
  Begründung: Single-User-App, keine externen Konsumenten.
  Aufwand-Schätzungen in Phase 2 entsprechend reduziert (~30%).
- **JSON-Mode-Skills validieren LLM-Output immer gegen ein Pydantic-Modell
  aus `schema.py`.** Kein Silent-Fallback. `ValidationError` → Exception an Caller.
- **Regex-Parsing von LLM-Output ist verboten.** (F14) — Immer `model_validate_json(raw)`. Gilt auch für alle bestehenden ad-hoc-`json.loads(raw)`-Patterns ohne Pydantic-Validation.
- **Tool-Calling-Loops haben immer sowohl `max_iterations` als auch
  `max_total_tokens`.** Beide hartcodiert im Loop-Modul, nicht aus Env.

### Fragen-Entscheidungen (aus 04-decisions.md)

- **F1 [IRREVERSIBEL]:** Alt-Brief-System vollständig entfernen. Kein Compat-Layer. Schritt 5.1 nach Phase 1 vorziehen.
- **F2 [REVERSIBEL]:** Frontmatter-Validierung via Pydantic-Schema in `utils/prompts.py`. Pflichtfelder: `id`, `version`, `model`, `role`, `inputs`. `model` ist bindend. Versionsformat: ISO-Datum (`2026-05-07`), Postfix `-2` bei mehreren Änderungen am selben Tag.
- **F3 [SEMI-REVERSIBEL]:** `llm` als Parameter in jedem Skill. Singleton `_lite()` entfernen. Factory in `llm_client.py` mit Cache per `(provider, model)`. Orchestrator liest `model` aus Frontmatter, holt Client von Factory.
- **F4 [REVERSIBEL]:** Adressaten-Profile gelten nur für Verlauf. Werden zu einheitlichem `curate_variant`-Konzept mit F4.2 zusammengeführt. `adressat`-Query-Parameter exponiert im API-Endpoint.
- **F4.2:** `SUBSTANZ_TIEFE` + Adressat → `curate_variant`. Pydantic-Validator prüft gegen verfügbare `.md`-Dateien in `03_curate/prompts/`. `_extract_substanz_tiefe()` (Regex) entfällt. Siehe Schritt 2.3e.
- **F5 [SEMI-REVERSIBEL]:** `befunde` bleibt nicht-lernfähig. Fachliche Entscheidung. Dokumentiert in `backend/AGENTS.md`.
- **F6 [REVERSIBEL]:** `update_status` bleibt LLM-unsichtbar. Sicherheitsentscheidung. Dokumentiert in `backend/AGENTS.md` mit explizitem Kommentar.
- **F7 [REVERSIBEL]:** `MAX_ITERATIONS_BLOCK_1=8`, `MAX_ITERATIONS_BLOCK_2=5` als fixe Code-Konstanten. Kein Env-Override. Test-Pins bleiben.
- **F8 [SEMI-REVERSIBEL]:** Chat-System-Prompt als `workflows/patient_chat/prompt.md` mit Jinja-Platzhaltern `{{ patient_yaml }}` und `{{ today }}`. Test pinnt strukturelle Invarianten (3–5 Assertions), kein Wort-für-Wort-Vergleich.
- **F9 [SEMI-REVERSIBEL]:** Keine geteilten Helpers. Renderer-Funktionen leben in der jeweiligen `skill.py`. Kein `workflows/brief/_helpers.py`.
- **F10 [REVERSIBEL]:** Beide AGENTS.md-Ebenen: Root (repo-weite Konventionen) + `backend/AGENTS.md` (Python-spezifisch, Pattern, Sicherheits-Doku).
- **F11 [IRREVERSIBEL bei Harmonisierung]:** Streaming-Transport nicht anfassen. Dokumentiert in `backend/AGENTS.md`.
- **F13 [SEMI-REVERSIBEL]:** Schema-Reihenfolge: 1. Stammdaten → 2. Diagnosen+Therapie parallel → 3. Verlauf-Sub-Schemas → 4. Learning-Schemas.
- **F14 [SEMI-REVERSIBEL]:** Pydantic-Validierung überall. Alle Fundstellen in §12 von `01-analysis.md` dokumentiert.
- **F15 [SEMI-REVERSIBEL]:** `user_id` als expliziter Parameter überall. `.env`-Flag `MULTI_USER=true|false`. Middleware in `utils/auth_context.py`. Siehe Schritt 0.5 (NEU).

### Meta-Entscheidungen

- **M1:** Jeder neu angelegte Folder bekommt eine `README.md` (3–10 Zeilen).
- **M2:** Alle `.txt`-Prompts → `.md` mit YAML-Frontmatter. Schritt 1.4b.
- **M3:** Hybrid-Sprach-Regel. `data/briefs/` → `data/briefe/`, `data/patients/` → `data/patienten/`. Schritt 0.3.

---

## Phase 0: Voraussetzungen (kein Code)

### Schritt 0.1 — Alt-Brief-System-Entscheidung (ERLEDIGT)

**Entscheidung:** Das Alt-System wird vollständig entfernt (F1). Kein Compat-Layer. Schritt 5.1 wird nach Phase 1 vorgezogen.

---

### Schritt 0.2 — AGENTS.md anlegen (Root + backend/)

**Ziel:** Beide AGENTS.md-Ebenen anlegen.

- Neu: `/AGENTS.md` — repo-weite Konventionen (Sprach-Regel M3, Branch-Naming, Commit-Konventionen, Top-Level-Topologie)
- Neu: `backend/AGENTS.md` — Python-spezifisch (ICM-Konventionen, Pattern, Pydantic-Regel, Frontmatter, Lernlog-Mechanik, Sicherheits-Doku für `update_status` und `befunde`, Streaming-Transport-Entscheidung F11)

**Aufwand:** 1–2h

**Abhängigkeiten:** keine (kann jederzeit)

---

### Schritt 0.3 — Sprach-Vereinheitlichung (M3)

**Ziel:** Englische Ordnernamen mit deutschem Domain-Inhalt umbenennen.

**Umbenennungen:**
- `data/briefs/` → `data/briefe/` (bereits `data/briefe/` vorhanden — `data/briefs/` ist veraltet)
- `data/patients/` → `data/patienten/`
- Storage-Code und Tests entsprechend anpassen

**Prüfe außerdem:** `data/` auf weitere englische Namen mit deutschem Inhalt (`*briefs*`, `*patients*`, `*chat*`). `data/chat/` und `data/meilensteine/` sind bereits gemischt — Felix entscheidet ob `chat` bleibt oder zu `data/gespraeche/` wird.

**Aufwand:** S (1–2h)

**Abhängigkeiten:** keine

**Tests:** Alle Storage-Tests grün nach Pfad-Anpassung

---

### Schritt 0.4 — data/-Audit und Bereinigung

**Vorgehen in vier Sub-Schritten:**

#### 0.4a — Inventar
Tabelle in `docs/icm-migration/05-data-audit.md` (s. dort).

#### 0.4b — User-Approval
Nichts löschen bevor Felix die Inventar-Tabelle abgenickt hat.

#### 0.4c — Snapshot vor Wipe
```bash
git tag pre-icm-data-wipe-2026-05-07
tar czf data.backup.tar.gz backend/data/
# data.backup.tar.gz in .gitignore eintragen
```

#### 0.4d — Neu-Befüllung nach Wipe
```
data/
├── briefe/                    # Brief-Snapshots, gitignored
├── patienten/                 # Patient-YMLs, gitignored
├── lernlog/                   # Aggregierte Lernlog-Einträge, gitignored
└── learning_snapshots/        # Pro-Patient-YML-Snapshots, gitignored
    └── brief/
        └── <P-NNNN>.yml
```

**Aufwand:** S (1–2h für Script + Verifikation)

**Abhängigkeiten:** Schritt 0.3 (Pfad-Umbenennung) → Schritt 0.4 ist Voraussetzung für Phase 1 (Lernlog-Migration 1.6 baut auf neuen Pfaden auf).

**Wichtig:** Nichts ohne explizite Bestätigung von Felix löschen.

---

### Schritt 0.5 — Multi-User-Vorbereitung (F15)

**Ziel:** `utils/auth_context.py` + `MULTI_USER`-Flag in `.env`.

**Dateien:**
- Neu: `backend/utils/auth_context.py` — FastAPI-Middleware mit `get_user_id(request)`
- `.env.example`: `MULTI_USER=false` eintragen

**Aufwand:** S (1h)

**Abhängigkeiten:** Schritt 1.2 (`utils/`-Verzeichnis)

**Tests:** Unit-Test für `get_user_id` mit `MULTI_USER=false` (gibt immer `"default"`)

---

## Phase 1: Strukturelle Vorarbeiten (keine Logik-Änderung)

### Schritt 1.1 — ULID-Extraktion

**Ziel:** Duplizierte `_generate_ulid()`-Implementierung in eine einzige Datei auslagern.

**Dateien:**
- Neu: `backend/utils/__init__.py` (leer)
- Neu: `backend/utils/ulid.py` — enthält `generate_ulid()` (aus `agent_tools.py` kopiert)
- Änderung: `agent_tools.py` — `_generate_ulid()` durch `from utils.ulid import generate_ulid` ersetzen
- Änderung: `learning_storage.py` — analog

**Aufwand:** 1–2h

**Abhängigkeiten:** keine

**Rollback:** `utils/ulid.py` löschen, lokale Implementierungen wiederherstellen

**Tests nach dem Schritt:**
- Alle bestehenden Tests grün (keine Test-Änderung nötig)
- Optional: Smoke-Test `test_ulid_no_duplicate_generation` hinzufügen

---

### Schritt 1.2 — `utils/` Verzeichnis vollständig anlegen

**Ziel:** `utils/`-Verzeichnis als Heimat für zukünftige geteilte Hilfsfunktionen.

**Dateien:**
- `backend/utils/__init__.py` — (leer, Schritt 1.1 hat es bereits angelegt)

**Aufwand:** <15min (kommt mit Schritt 1.1)

---

### Schritt 1.3 — Pydantic-Output-Schemas anlegen (je im Section-Folder)

**Ziel:** Output-Schemas für alle vier JSON-Mode-Skills anlegen. Schemas landen im jeweiligen Section-Folder, nicht in einem zentralen `schemas/`-Verzeichnis.

**Dateien:**
- Neu: `backend/workflows/brief/diagnosen/schema.py` — enthält `DiagnosenOutput`
- Neu: `backend/workflows/brief/therapie/schema.py` — enthält `TherapieOutput`
- Neu: `backend/workflows/stammdaten_extraction/schema.py` — enthält `StammdatenExtractResult` (aus `agent_stammdaten_extraction.py` verschieben)
- Neu: `backend/skills/learning/schemas.py` — enthält `RuleExtractionOutput`, `ConflictOutput`, `RebuildOutput` (aus `agent_meilenstein_learning.py` verschieben)
- Änderung: `agent_stammdaten_extraction.py` — Import aus dem neuen Pfad
- Änderung: `main.py` — Import-Pfade anpassen

**Hinweis:** Die Ordner `workflows/brief/diagnosen/` usw. werden in Phase 2 angelegt. Für jetzt reicht es, die Schema-Dateien in temporären Zielpfaden anzulegen und die alten Module umzustellen.

**Aufwand:** 1–2h

**Abhängigkeiten:** keine

**Rollback:** Schemas zurück in die ursprünglichen Module

**Tests nach dem Schritt:** Alle grün (nur Import-Pfad-Änderung)

---

### Schritt 1.4 — Prompt-Infrastruktur (utils/prompts.py)

Schritt 1.4 ist in zwei Sub-Schritte aufgeteilt.

#### 1.4a — `utils/prompts.py` anlegen (Frontmatter-Stripping + Validierung)

**Ziel:** `_get_prompt()` aus `agent_brief.py` in `utils/prompts.py` auslagern. Frontmatter-Stripping und Pydantic-Validierung hinzufügen.

**Dateien:**
- Neu: `backend/utils/prompts.py` — `_get_prompt()`, `PromptFrontmatter(BaseModel)`, Validierung
- Änderung: `agent_brief.py` — importiert `_get_prompt` aus `utils.prompts`
- Änderung: `agent_meilenstein_learning.py` — analog

```python
# utils/prompts.py
def _get_prompt(name: str) -> str:
    raw = ...  # bestehende Lade-Logik
    if raw.startswith("---"):
        _, _, body = raw.split("---", 2)
        _validate_frontmatter(raw)   # wirft ValidationError bei fehlendem Pflichtfeld
        return body.lstrip("\n")
    return raw
```

**Test:** `test_get_prompt_strips_frontmatter` + `test_get_prompt_validates_frontmatter` hinzufügen.

**Aufwand:** 1h

#### 1.4b — Prompt-Format-Migration `.txt` → `.md` mit Frontmatter (M2)

**Ziel:** Alle 19 `.txt`-Prompt-Dateien in `backend/prompts/` umbenennen und mit YAML-Frontmatter versehen.

**Schritte:**
- Jede `.txt`-Datei → `.md` umbenennen
- YAML-Frontmatter-Block (Pflichtfelder: `id`, `version`, `model`, `role`, `inputs`) voranstellen
- `_get_prompt()` bevorzugt ohnehin `.md` über `.txt` (bereits implementiert) — kein weiterer Code-Change nötig

**Aufwand:** S (2h für alle 19 Dateien)

**Abhängigkeiten:** Schritt 1.4a (Stripping muss vor dem ersten `.md`-Prompt in Produktion sein)

**Tests:** Alle bestehenden Prompt-Lade-Tests grün

---

### Schritt 1.5 — Pydantic-Args für alle Tools

**Ziel:** Alle 13 Tools in `agent_tools.py` auf Pydantic-Args-Modelle umstellen.
JSON-Schemas werden aus `model_json_schema()` generiert statt handgepflegt.

**Dateien:**
- Änderung: `agent_tools.py` — je ein `<ToolName>Args(BaseModel)` pro Tool-Funktion;
  Signatur von `def add_behandlungsdiagnose(patient_id, text, ...)` → `def add_behandlungsdiagnose(args: AddBehandlungsdiagnoseArgs)`.
- `TOOL_SCHEMAS` bleibt als Registry, Inhalte werden aus `model_json_schema()` abgeleitet.

**Aufwand:** M (4–6h)

**Abhängigkeiten:** keine

**Rollback:** Plain-Python-Args zurück

**Tests nach dem Schritt:**
- `test_agent_tools.py` — Schema-Strict-Mode, alle 13 Tool-Funktionen grün
- Kein Breaking Change für LLM (JSON-Schema-Output ist äquivalent)

---

### Schritt 1.6 — Lernlog-Migration

#### 1.6a — Snapshots nach `data/learning_snapshots/`

**Ziel:** Bestehende `.txt`-Dateien aus `data/learnings/default/*/last/<pid>.txt` in strukturierte `.yml`-Dateien unter `data/learning_snapshots/<workflow>/<P-NNNN>.yml` migrieren.

**Format-Transformation:**
```
Vorher:  data/learnings/default/brief/diagnosen/last/P-0001.txt  (ein Feld)
         data/learnings/default/brief/anamnese/last/P-0001.txt   (ein Feld)
         ...
Nachher: data/learning_snapshots/brief/P-0001.yml               (alle Felder in einer Datei)
         # { diagnosen: "...", anamnese: "...", therapie: "...", verlauf: "..." }
```

**Schritte:**
- `learning_storage.py` um `_snapshot_path(workflow, pid)` erweitern
- Migrations-Script: liest alle bestehenden `.txt`-Dateien, konsolidiert pro Patient in `.yml`
- `data/learning_snapshots/` zu `.gitignore` hinzufügen

**Aufwand:** M (2–3h für Pfade + Script + Tests)

#### 1.6b — Regelmengen nach `workflows/<wf>/<section>/lernlog/`

**Ziel:** Bestehende `rules.yml`-Dateien aus `data/learnings/default/<workflow>/<section>/rules.yml` nach `workflows/<wf>/<section>/lernlog/default.yml` migrieren.

**Schritte:**
- `learning_storage.py` um `_rules_path(workflow, section, user)` erweitern
- `lernlog/`-Ordner in den Section-Folders anlegen
- Whitelist-`.gitignore` in jeden `lernlog/`-Ordner committed (Inhalt: `*\n!.gitignore\n!README.md\n!example.yml`)
- Migrations-Script: kopiert `rules.yml` → `default.yml` in den neuen Pfad
- `README.md` + `example.yml` für jeden `lernlog/`-Ordner anlegen (committed)

**Aufwand:** M-L (2–3h zusätzlich für alle lernlog/-Ordner + `.gitignore`-Dateien + Tests)

**Gesamt-Aufwand Schritt 1.6:** M-L (4–6h für Skript + Pfad-Funktionen + Tests)

**Abhängigkeiten:** Schritt 1.3 (Schemas), `workflows/`-Struktur muss für 1.6b angelegt sein (oder zumindest die `lernlog/`-Ordner)

**Tests nach dem Schritt:**
- `test_learning_storage.py` — `_snapshot_path`, `_rules_path`, Roundtrip
- Migrations-Script mit Test-Daten verifizieren

---

### Schritt 1.7 — Tool-Loop-Observability

**Ziel:** Token-Budget-Abbruch und Pro-Iteration-Logging für Tool-Calling-Loops.

**Änderungen:**
- `agent_extraction_core.py` (später `workflows/document_extraction/tool_loop.py`):
  - Cumulativer Token-Counter pro Pass
  - Abbruch bei Überschreitung von `MAX_TOTAL_TOKENS_BLOCK_1` / `MAX_TOTAL_TOKENS_BLOCK_2` (hartcodiert)
  - Pro-Iteration-Logging: Tool-Name, Args (gekürzt), Response (gekürzt), `thinking_budget`

**Aufwand:** M (3–4h)

**Abhängigkeiten:** keine (kann vor oder nach Schritt 2.4 gemacht werden)

**Test:** Loop mit absurd niedrigem Token-Budget bricht sauber ab (neuer Test)

---

## Phase 2: Skills und Prompts in Section-Ordner verschieben

Phase 2 gliedert sich nach Workflow und Section. Jede Section ist einzeln commit-bar.
Kein Thin-Wrapper-Pattern — `main.py` wird bei jedem Umzug sofort umgestellt.

### Schritt 2.1 — `agent_tools.py` → `tools/patient_tools.py`

**Ziel:** Wort "agent" aus Dateinamen entfernen.

**Dateien:**
- Neu: `backend/tools/__init__.py`
- Neu: `backend/tools/patient_tools.py` (Inhalt aus `agent_tools.py`)
- `agent_tools.py` entfernen
- Änderung: `main.py` — Import von `tools.patient_tools`
- Änderung: alle Tests — Import-Pfad anpassen

**Aufwand:** 1–2h (ohne Thin-Wrapper)

**Abhängigkeiten:** Phase 1 abgeschlossen (ULID-Import aus `utils.ulid`, Pydantic-Args aus Schritt 1.5)

**Rollback:** `agent_tools.py` wiederherstellen, Import zurückstellen

**Tests nach dem Schritt:**
- `test_agent_tools.py` Import-Pfade anpassen, alle Tests grün

---

### Schritt 2.2 — `skills/learning/` anlegen, Learning-Skills verschieben

**Ziel:** `agent_meilenstein_learning.py` (3 Skills) → `skills/learning/` (cross-cutting Struktur).

**Dateien:**
- Neu: `backend/skills/__init__.py`
- Neu: `backend/skills/learning/__init__.py` — exportiert `from_edits()` und `rebuild()`
- Neu: `backend/skills/learning/extract.py` — enthält `extract_rule_candidates`
- Neu: `backend/skills/learning/conflict.py` — enthält `detect_conflict`
- Neu: `backend/skills/learning/rebuild.py` — enthält `rebuild_rule_candidate`
- Neu: `backend/skills/learning/schemas.py` — aus Schritt 1.3 verschoben (falls noch nicht geschehen)
- Neu: `backend/skills/learning/prompts/` — Learning-Prompts hierher verschieben:
  - `rule_extraction.md` (aus `prompts/learning_rule_extraction.txt`)
  - `conflict_detection.md` (aus `prompts/learning_conflict_detection.txt`)
  - `rule_rebuild.md` (aus `prompts/learning_rule_rebuild.txt`)
  - Frontmatter zu jedem Prompt hinzufügen
- `agent_meilenstein_learning.py` entfernen
- Änderung: `main.py` — Import von `skills.learning`

**Aufwand:** 2–3h (ohne Thin-Wrapper)

**Abhängigkeiten:** `skills/`-Verzeichnis, Schritt 1.4a (Frontmatter-Stripping)

**Tests:** `test_meilenstein_learning.py` Import-Pfade anpassen

---

### Schritt 2.3 — `workflows/brief/` anlegen, Brief-Skills und Prompts verschieben

Gegliedert nach Sektion. Jede Sektion ist einzeln commit-bar.

#### 2.3a — `workflows/brief/diagnosen/`

**Dateien:**
- Neu: `backend/workflows/__init__.py`
- Neu: `backend/workflows/brief/__init__.py`
- Neu: `backend/workflows/brief/diagnosen/` (Ordner)
- Neu: `backend/workflows/brief/diagnosen/skill.py` — `generate_diagnosen`-Logik aus `agent_brief.py`
- Neu: `backend/workflows/brief/diagnosen/schema.py` — `DiagnosenOutput` (aus Schritt 1.3)
- Neu: `backend/workflows/brief/diagnosen/prompt.md` — aus `prompts/brief_diagnosen.txt`, umbenennen + Frontmatter
- Neu: `backend/workflows/brief/diagnosen/lernlog/` — `.gitignore`, `README.md`, `example.yml`
- Änderung: `agent_brief.py` — `generate_diagnosen` durch Import aus `skill.py` ersetzen

**Aufwand:** 1–2h

#### 2.3b — `workflows/brief/anamnese/`

Analog zu 2.3a. Kein `schema.py` (Plain-Text-Skill).

**Aufwand:** 1h

#### 2.3c — `workflows/brief/therapie/`

Analog zu 2.3a. Enthält `schema.py` mit `TherapieOutput`.

**Aufwand:** 1–2h

#### 2.3d — `workflows/brief/befunde/`

Analog, ohne `lernlog/` (Befunde nicht lernfähig).

**Aufwand:** 1h

#### 2.3e — `workflows/brief/verlauf/` (Compound Stage)

**Dateien:**
- Neu: `backend/workflows/brief/verlauf/orchestrator.py` — ruft die 3 Passes sequenziell; akzeptiert `curate_variant`-Override via `adressat`-Query-Parameter
- Neu: `backend/workflows/brief/verlauf/lernlog/` — `.gitignore`, `README.md`, `example.yml`
- Neu: `backend/workflows/brief/verlauf/01_collect/prompt.md` + `skill.py` — gibt `CollectOutput(substance, curate_variant)` zurück
- Neu: `backend/workflows/brief/verlauf/02_audit/prompt.md` + `skill.py`
- Neu: `backend/workflows/brief/verlauf/03_curate/prompts/` — `shared.md`, `minimal.md`, `kompakt.md`, `ausfuehrlich.md`
- Neu: `backend/workflows/brief/verlauf/03_curate/schema.py` — `CollectOutput` mit `curate_variant`-Validator (prüft gegen Dateinamen in `prompts/`)
- Neu: `backend/workflows/brief/verlauf/03_curate/skill.py` — lädt Variante dynamisch aus `CollectOutput.curate_variant`
- Prompts aus `prompts/brief_verlauf_*.txt` hierher verschieben + Frontmatter (Adressaten-Profil wird in Varianten integriert)
- `_extract_substanz_tiefe()` (Regex) entfernen, `_load_curate_prompt()` entfernen
- Änderung: `agent_brief.py` — `generate_verlauf` durch Import aus `verlauf/orchestrator.py` ersetzen

**Aufwand:** 4–5h (Compound-Stage mit 3 Sub-Stages + curate_variant-Konzept)

---

### Schritt 2.4 — `agent_brief.py` → `workflows/brief/orchestrator.py`

**Ziel:** `agent_brief.py` ist nach 2.3a–2.3e leer bis auf den Orchestrierungs-Rahmen.
Diesen in `workflows/brief/orchestrator.py` verschieben.

**Inhalt des Orchestrators:**
- `generate_brief(patient, extra_context, adressat)` — Stages 1–7 sequenziell
- `generate_section(section, patient, extra_context, adressat)` — Einzelsektion
- `polish_section(section, current_text, extra_context, patient)` — Lektor
- `learn_from_edits(section, patient_id, original, edited, user_id)` — delegiert an `skills.learning`

**Dateien:**
- Neu: `backend/workflows/brief/orchestrator.py`
- `agent_brief.py` entfernen
- Änderung: `main.py` — `from workflows.brief import orchestrator as brief`

**Aufwand:** 1–2h (Hauptarbeit ist in 2.3a–2.3e passiert)

**Tests:** `test_brief.py` Imports auf `workflows.brief.orchestrator`

---

### Schritt 2.5 — `agent_extraction_core.py` → `workflows/document_extraction/tool_loop.py`

**Ziel:** Multi-Turn-Loop-Code aus "agent"-Namespace heraus.

**Aufwand:** 1–2h (nur Verschieben, keine Logik-Änderung)

**Abhängigkeiten:** Schritt 1.7 (Token-Observability) empfohlen vor diesem Schritt

**Rollback:** Import zurückstellen

**Tests:** `test_agent_document_extraction.py` Import-Pfad anpassen (inkl. `_HEARTBEAT_INTERVAL`-Import)

---

## Phase 3: Restliche Workflow-Orchestratoren anlegen

Da Skills jetzt in den Workflow-Ordnern leben (Phase 2), sind diese Orchestratoren
überwiegend Thin-Hüllen — deutlich weniger Arbeit als ursprünglich geplant.

### Schritt 3.1 — `workflows/document_extraction/orchestrator.py`

**Ziel:** `agent_document_extraction.py` → Orchestrator.

**Inhalt:**
- `extract_proposals(llm, patient, content, content_type, extra_context)`
- `extract_proposals_streaming(...)` (async generator)

**Aufwand:** 1–2h

**Abhängigkeiten:** Schritt 2.5

**Tests:** `test_agent_document_extraction.py`

---

### Schritt 3.2 — `workflows/patient_chat/orchestrator.py`

**Ziel:** `agent_patient_chat.py` → Orchestrator. **Kritischer Sub-Schritt:** Chat-System-Prompt als Datei auslagern.

**Sub-Schritt 3.2a — Chat-Prompt als Datei:**
- Hardcodierten `string.Template`-Prompt aus `agent_patient_chat.py` extrahieren
- Als `workflows/patient_chat/system_prompt.md` speichern (mit Frontmatter)
- `build_system_prompt()` nutzt `_get_prompt("patient_chat_system")`
- **Dies ist das einzige inhaltlich relevante Refactoring** (alle anderen sind rein strukturell)

**Aufwand:** 2–3h (3.2a allein schon 1–2h wegen Prompt-Komplexität und Test-Absicherung)

**Abhängigkeiten:** Schritt 1.4a (Frontmatter-Stripping), Schritt 2.5 (tool_loop.py)

**Tests:**
- Neuer Test `test_patient_chat_system_prompt_content` (analog zu anderen Prompt-Content-Tests)
- `test_main.py` Chat-Tests auf neuen Import-Pfad

---

### Schritt 3.3 — `workflows/meilenstein/orchestrator.py` und `workflows/stammdaten_extraction/orchestrator.py`

Reine Thin-Wrapper, je <1h.

---

## Phase 4: Bug-Fixes und Ergänzungen

### Schritt 4.1 — Drift-Bug in `main.py` (BEREITS ERLEDIGT — überspringen)

Siehe Hinweis am Anfang dieses Dokuments.

---

### Schritt 4.2 — curate_variant-Parameter durchreichen (R-8, F4.2)

**Ziel:** `regenerate_section` für `verlauf` übergibt `adressat`/`curate_variant` explizit statt Default zu verwenden.

**Details:**
- `main.py:1059` — `adressat` fehlt im `generate_verlauf`-Aufruf von `/generate-section/verlauf`
- Lösung: `adressat` als Query-Parameter des Endpoints ergänzen (überschreibt LLM-Wahl aus Pass 1), an `verlauf/orchestrator.py` weitergereicht als `curate_variant`-Override
- API-Parametername bleibt `adressat` für Kompatibilität; intern `curate_variant`

**Aufwand:** S (1h)

**Abhängigkeiten:** Schritt 2.3e (curate_variant-Konzept implementiert), Schritt 2.4

**Tests:** Test für `/api/brief/{id}/generate-section/verlauf?adressat=minimal`

---

## Phase 5: Alt-Brief-Abschaltung (nach Phase 1)

### Schritt 5.1 — Alt-Brief-System abschalten (F1)

**Entscheidung:** Vollständige Entfernung, kein Compat-Layer. Schritt wird nach Phase 1 ausgeführt (nicht erst nach Phase 4).

**Voraussetzung:** Phase 1 abgeschlossen. Frontend arbeitet nicht mehr gegen `/api/patients/{id}/brief/*` (bereits migriert laut F1-Entscheidung).

**Dateien:**
- `main.py`: Route-Gruppe `/api/patients/{id}/brief/*` entfernen
- `prompts/brief_system.txt` (oder `.md`): löschen (kein Archivieren — Git-History reicht)
- `storage.py`: `BRIEF_FIELDS`, `save_brief`, `load_brief`, `delete_brief`, `brief_input_hash`, `empty_brief_data` entfernen
- `tests/test_storage.py`: Alt-Brief-Tests entfernen
- `data/briefe/` (altes Alt-System JSON): nach Schritt 0.4b-Bestätigung wipe-bar

**Aufwand:** 2–3h

**Abhängigkeiten:** Phase 1 abgeschlossen

**Rollback:** Git-Revert (letzter Commit dieser Phase)

---

## Phase 6: Code-Hygiene (laufend nach jeder Phase)

### Schritt 6.1 — Vulture-Lauf

**Wann:** Nach jeder abgeschlossenen Phase (1–5).

**Vorgehen:**
```bash
vulture backend/ --min-confidence 80
```
Gefundene Leichen begutachten und in eigenem Commit löschen. Falsch-Positive in `.vulture_whitelist.py` eintragen.

**Aufwand:** 30min pro Lauf

---

### Schritt 6.2 — Dead-Import-Sweep

**Wann:** Einmalig nach Phase 5.

**Vorgehen:**
```bash
pyflakes backend/
```
Alle `unused import`-Warnings bereinigen.

**Aufwand:** 1h (einmalig)

---

### Schritt 6.3 — Test-Mortality

**Wann:** Nach Phase 5.

Tests, die nach Migration nichts Sinnvolles mehr testen (z.B. Tests für entfernte Alt-Brief-Routen), explizit löschen statt skippen.

**Aufwand:** 1h

---

## Risikoanalyse

| Risiko | Schritt | Wahrscheinlichkeit | Auswirkung | Mitigierung |
|--------|---------|:-----------------:|:---------:|-------------|
| Import-Zyklen beim Verschieben | 2.1–2.5 | mittel | mittel | Direkter Import-Umzug in main.py, kein Wrapper |
| Prompt-Frontmatter bricht Prompt-Text | 1.4a + Phase 2 | niedrig | hoch | `_get_prompt()` Stripping vor jeder Umbenennung testen |
| Chat-Prompt-Extraktion ändert Verhalten | 3.2a | niedrig | hoch | Bestehende Tests + neuen Content-Test vor Merge |
| Alt-Brief-System abschalten zu früh | 5.1 | mittel | hoch | Frontend-Audit vor Schritt 5.1 |
| `_HEARTBEAT_INTERVAL`-Import bricht | 2.5 | niedrig | niedrig | Export als Public-Symbol umbenennen bei Verschiebung |
| Token-Budget-Abbruch zu streng | 1.7 | niedrig | mittel | Absichtlich hohe Defaults; Test mit niedrigem Budget |
| Lernlog-Migration löscht Daten | 1.6 | niedrig | hoch | Script auf Kopie testen, Original erst nach Verifikation entfernen |

---

## Leverage-Analyse: Was gibt den größten Gewinn?

| Schritt | ICM-Mehrwert | Aufwand | Priorität |
|---------|-------------|---------|-----------|
| **1.1 ULID-Extraktion** | Tech-Debt-Abbau | 1–2h | **hoch** |
| **1.5 Pydantic-Args für Tools** | Type-Safety + Schema-Generierung | 4–6h | **hoch** |
| **3.2a Chat-Prompt als Datei** | Größte ICM-Verletzung behoben | 1–2h | **hoch** |
| **1.4a Frontmatter-Stripping** | Enabler für Phase 2 | 30min | **hoch (Voraussetzung)** |
| **2.1 agent_tools → tools/** | Namens-Hygiene, Vokabular | 1–2h | **mittel** |
| **2.2 Learning-Skills** | Modularität | 2–3h | **mittel** |
| **2.3 Brief-Skills** | Modularität + Lernlog-Struktur | 7–10h (alle Sub-Schritte) | **mittel** |
| **1.6 Lernlog-Migration** | Neue Daten-Architektur | 4–6h | **mittel** |
| **1.7 Token-Observability** | Sicherheitsnetz für Loops | 3–4h | **mittel** |
| **Phase 3 Orchestratoren** | Vollständige ICM-Struktur | 5–8h | **niedrig/langfristig** |
| **Phase 5 Alt-Brief** | Technische Schulden-Abbau | 2–3h | **nach Entscheidung** |

---

## Done-Definition

Die Migration gilt als vollständig abgeschlossen wenn:

- [ ] Kein Dateiname enthält "agent" in `backend/`
- [ ] Alle Prompts sind `.md`-Dateien mit gültigem YAML-Frontmatter, in Section-Ordnern
- [ ] Chat-System-Prompt existiert als `workflows/patient_chat/prompt.md`
- [ ] `utils/ulid.py` ist die einzige ULID-Implementierung
- [ ] `utils/prompts.py` ist die einzige `_get_prompt()`-Implementierung mit Frontmatter-Validierung
- [ ] `utils/auth_context.py` existiert; `MULTI_USER`-Flag in `.env.example`
- [ ] `workflows/<wf>/orchestrator.py` existiert für alle 5 Workflows
- [ ] `workflows/brief/<section>/skill.py` existiert für alle Brief-Sektionen
- [ ] `skills/learning/` existiert als cross-cutting Skill
- [ ] Alle Tools nutzen Pydantic-Args-Modelle, Schemas aus `model_json_schema()`
- [ ] `data/learning_snapshots/` existiert, Daten aus `data/learnings/*/last/` migriert
- [ ] `lernlog/`-Ordner in allen lernfähigen Section-Folders, Regelmengen migriert
- [ ] `AGENTS.md` existiert im Repo-Root + `backend/AGENTS.md` mit bindenden Konventionen
- [ ] Alle 188+ Tests sind grün
- [ ] `GET /api/learn/brief/verlauf/system-prompt` gibt HTTP 200
- [ ] Kein Prompt als Python-String-Template im Code
- [ ] Tool-Calling-Loop hat Token-Budget-Abbruch
- [ ] Kein Regex-Parsing von LLM-Freitext-Output (F14 — alle Fundstellen aus §12 behoben)
- [ ] Alt-Brief-System vollständig entfernt (Schritt 5.1)
- [ ] `data/patienten/` statt `data/patients/`, `data/briefe/` statt `data/briefs/` (Schritt 0.3)
- [ ] Jeder Section-/Workflow-Folder hat eine `README.md` (M1)
- [ ] `curate_variant`-Konzept implementiert, `_extract_substanz_tiefe()` entfernt (F4.2)
- [ ] `llm_client.py` hat Factory-Methode `get_client(model)` (F3)
- [ ] Vulture-Lauf nach Phase 5 ohne Findings (außer Whitelist) (Phase 6)
