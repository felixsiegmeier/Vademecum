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

**F4.2 — Curate-Varianten (Architektur-Konsolidierung)** ✅ implementiert (Schritt 4.2)
`SUBSTANZ_TIEFE`-Regex-Signal und Adressaten werden zu `curate_variant` zusammengeführt; Varianten sind `.md`-Dateien in `workflows/brief/verlauf/03_curate/prompts/` (user-erweiterbar); Pass-1-Output wird als `CollectOutput(BaseModel)` mit `field_validator` gegen verfügbare Dateinamen validiert; `?adressat=...` erzwingt eine Variante; `_extract_substanz_tiefe()` entfällt. **Validator-Reuse:** `validate_curate_variant(v: str) -> str` lebt als freie Funktion in `workflows/brief/verlauf/__init__.py` — wird sowohl von `CollectOutput` als auch vom HTTP-Request-Model delegiert; löst R-8.

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

**F16 — `tool_loop` Cross-Workflow-Import** ✅ gelöst in Schritt 5.3
Promoviert nach `utils/tool_loop.py` (Runtime-Mechanik, nicht Domain-Tool). Begründung: `tools/` ist reserviert für LLM-callable Domain-Funktionen mit Pydantic-Args (`patient_tools.py`); `tool_loop` ist Infrastruktur (LLM-Call-Wrapper, Streaming, Heartbeat) und gehört zur `utils/`-Familie neben `prompts.py`/`auth_context.py`. Fünf Konsumenten auf einheitlichen Importpfad `utils.tool_loop` umgestellt; Cross-Workflow-Abhängigkeit von `patient_chat` → `document_extraction` aufgelöst.

---

**D-mittel-Tier — Verlauf-Curate-Tiers bleiben bei drei**
`minimal`, `kompakt` (2–14 Tage), `ausfuehrlich` (>14 Tage). `mittel` wurde in Schritt 2.3e entfernt — eine vierte Stufe wäre semantisch unscharf zwischen kompakt und ausfuehrlich ohne klinische Trennlinie. Erweiterung jederzeit möglich ohne Code-Change: `03_curate/prompts/<name>.md` anlegen genügt; der Filesystem-Scan-Validator in `workflows/brief/verlauf/__init__.py` erkennt neue Varianten automatisch.

---

## R-Status-Übersicht (Stand 2026-05-07)

| R | Bezeichnung | Status |
|---|---|---|
| R-1 | Duales Brief-System | ✅ gelöst in 5.1 — Alt-Brief-System vollständig entfernt (`/api/patients/{id}/brief/*`, `storage.py`-Brief-Teil, `brief_system.md`) |
| R-2 | Prompt-Drift-Bug (`brief_verlauf_curate.txt`) | ✅ gefixt vor ICM-Branch (separater Branch, bereits gemerged) |
| R-3 | Hardcodierter Chat-Prompt | ✅ gelöst in 3.2a/3.2b — System-Prompt als `workflows/patient_chat/system_prompt.md` extrahiert, SHA-256-Test pinnt Byte-Identität |
| R-4 | ULID-Duplikation | ✅ gelöst — `utils/ulid.py` existiert, `learning_storage.py` und `tools/patient_tools.py` importieren daraus; dokumentiert in `backend/AGENTS.md` |
| R-5 | `user_id` hardcodiert | ⏸ bewusst offen — F15-Architektur vorbereitet (`user_id="default"` als expliziter Parameter), Multi-User-Aktivierung via `MULTI_USER`-Flag deferred nach Phase 6 |
| R-6 | Streaming-Transport-Inkonsistenz | ⏸ by design — akzeptiert als F11; dokumentiert in `backend/AGENTS.md` |
| R-7 | `_HEARTBEAT_INTERVAL` Symbol-Export | ⏸ by design — bleibt privat-aber-test-pinned; nach Promotion nach `utils/tool_loop.py` (5.3) ist Import-Pfad jetzt `utils.tool_loop._HEARTBEAT_INTERVAL` |
| R-8 | Adressat-Parameter nicht durchgereicht | ✅ gelöst in 4.2 — `curate_variant_override` + `adressat` durchgereicht; Validator-Reuse via freie Funktion in `verlauf/__init__.py` |
| R-9 | Unklare Chat-Persistenz | 🔲 offen → Phase 6 / post-migration backlog (Frontend-Audit: greift `/api/chat/{id}` aktiv?) |

## Phase-6-Backlog (nicht in Phase 1–5 adressiert)

- **TrivialChange-Smell**: Nie formal in Migrationsdocs erfasst — prüfen in Phase 6 ob es um `learning_storage.TrivialChange`-ähnliche Guard-Patterns geht; falls nicht relevant, explizit schließen.
- **Verlauf-Audit-Output-Schema**: Pass 2 (`02_audit`) gibt heute Plain-Text zurück — kein strukturiertes Pydantic-Modell analog zu `CollectOutput`. Bewusst nicht in Phase 5 angefasst; Kandidat für Phase 6 (F14-Konsequenz: auch Audit-Pass auf `model_validate_json` umstellen?).
- **Re-Export-Brücken (1.3)**: Audit in Schritt 5.0 bestätigt — alle Re-Exports verschwanden organisch mit der Löschung der `agent_*.py`-Module in Phase 3. Kein expliziter Cleanup nötig.
- **`data/lernlog/`-Migration**: Audit in Schritt 5.0 bestätigt DIR NOT FOUND — bereits durch (3.3-Bestätigung + `LERNLOG_BASE`-Pfad schreibt schon in `workflows/`).
