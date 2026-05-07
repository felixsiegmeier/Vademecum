# 04 — Pre-Decisions: ICM-Migration

Pro Frage: Titel + Entscheidung in einem Satz + Reversibilitäts-Label.

---

**F1 [IRREVERSIBEL] — Alt-Brief-System**
Alt-Brief-System (`/api/patients/{id}/brief/*`, `storage.py`-Brief-Teil, `brief_system.txt`) wird vollständig entfernt — kein Compat-Layer, Schritt 5.1 wird nach Phase 1 vorgezogen.

**F2 [REVERSIBEL] — Frontmatter-Pflichtfelder**
Frontmatter wird via Pydantic-Schema (`PromptFrontmatter`) in `utils/prompts.py` validiert; Pflichtfelder sind `id`, `version`, `model`, `role`, `inputs`; `model` ist bindend (Orchestrator-Client-Auflösung); `version` als ISO-Datum (`2026-05-07`) mit Postfix `-2` bei mehreren Änderungen am selben Tag.

**F3 [SEMI-REVERSIBEL] — Skill-Schnittstelle**
Jeder Skill erhält `llm` als Parameter; Singleton `_lite()` entfällt; `llm_client.py` bekommt Factory `get_client(model)` mit Cache per `(provider, model)`; Orchestrator liest `model` aus Frontmatter und übergibt gecachten Client.

**F4 [REVERSIBEL] — Adressaten-Profile**
Adressaten-Profile gelten nur für Verlauf und werden in das einheitliche `curate_variant`-Konzept (F4.2) überführt; `adressat`-Query-Parameter wird im API-Endpoint exponiert.

**F4.2 — Curate-Varianten (Architektur-Konsolidierung)**
`SUBSTANZ_TIEFE`-Regex-Signal und Adressaten werden zu `curate_variant` zusammengeführt; Varianten sind `.md`-Dateien in `workflows/brief/verlauf/03_curate/prompts/` (user-erweiterbar); Pass-1-Output wird als `CollectOutput(BaseModel)` mit `field_validator` gegen verfügbare Dateinamen validiert; `?adressat=...` erzwingt eine Variante; `_extract_substanz_tiefe()` entfällt.

**F5 [SEMI-REVERSIBEL] — Befunde-Lernlog**
`befunde` bleibt dauerhaft nicht-lernfähig (fachliche Entscheidung: SAP-Text-Übernahme ohne generalisierbares Lernpotenzial); dokumentiert in `backend/AGENTS.md`.

**F6 [REVERSIBEL] — `update_status`**
`update_status` bleibt LLM-unsichtbar (Sicherheitsentscheidung: LLM soll Patientenstatus nie eigenständig setzen); dokumentiert in `backend/AGENTS.md` mit explizitem Sicherheitskommentar.

**F7 [REVERSIBEL] — `max_iterations`**
`MAX_ITERATIONS_BLOCK_1=8` und `MAX_ITERATIONS_BLOCK_2=5` bleiben fixe Code-Konstanten; kein Env-Override; Test-Pins bleiben.

**F8 [SEMI-REVERSIBEL] — Chat-System-Prompt-Test**
Chat-System-Prompt wird als `workflows/patient_chat/prompt.md` extrahiert (Jinja-Platzhalter `{{ patient_yaml }}` und `{{ today }}`); Test pinnt 3–5 strukturelle Invarianten, kein Wort-für-Wort-Vergleich.

**F9 [SEMI-REVERSIBEL] — Renderer-Funktionen**
Renderer-Funktionen (`_render_diagnosen`, `_render_therapie`) leben in der jeweiligen `skill.py`; kein `workflows/brief/_helpers.py`.

**F10 [REVERSIBEL] — AGENTS.md-Hierarchie**
Beide Ebenen: Root `AGENTS.md` (repo-weite Konventionen) und `backend/AGENTS.md` (Python-spezifisch, Sicherheits-Doku, Streaming-Transport-Entscheidung).

**F11 [IRREVERSIBEL bei Harmonisierung] — Streaming-Transport**
Streaming-Transport wird nicht angefasst; Inkonsistenz (SSE vs. NDJSON) wird als bewusste Designentscheidung in `backend/AGENTS.md` dokumentiert.

**F13 [SEMI-REVERSIBEL] — Schema-Reihenfolge**
Reihenfolge: 1. Stammdaten → 2. Diagnosen + Therapie parallel → 3. Verlauf-Sub-Schemas → 4. Learning-Schemas.

**F14 [SEMI-REVERSIBEL] — Pydantic statt Regex**
Regex-Parsing von LLM-Output ist verboten; alle Fundstellen (s. `01-analysis.md §12`) werden auf `model_validate_json(raw)` migriert; `_extract_substanz_tiefe()` entfällt mit F4.2.

**F15 [SEMI-REVERSIBEL] — Multi-User-Vorbereitung**
`user_id` wird als expliziter Parameter durch alle Skills, Storage-Aufrufe und Orchestratoren durchgereicht; `.env`-Flag `MULTI_USER=true|false` schaltet nur die Middleware (`utils/auth_context.py`) um; bei `false` (Default) wird immer `user_id="default"` injiziert.

**F16 [BEKANNTE SCHULD] — `tool_loop` Cross-Workflow-Import**
`workflows/patient_chat/orchestrator.py` importiert `Proposal` und `group_proposals` aus `workflows/document_extraction/tool_loop.py` (Cross-Workflow-Import). Akzeptiert für Phase 3; `tool_loop` hat zwei Konsumenten: `document_extraction` (eigen) und `patient_chat` (Importer). Promotion nach `tools/extraction_loop.py` oder `utils/tool_loop.py` in Phase 5/6 evaluieren.
