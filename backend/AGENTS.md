# AGENTS.md — Backend-Konventionen (Python)

Python-spezifische Konventionen für `backend/`. Repo-weite Regeln in [`/AGENTS.md`](../AGENTS.md).

---

## Workflows (`backend/workflows/`)

- Ein `orchestrator.py` pro Workflow-Ordner.
- Bei Compound-Stages (z.B. `verlauf`): eigene `orchestrator.py` im Compound-Stage-Ordner.
- Stages sind nummeriert und sequenziell (kein paralleles Stage-Spawning).
- Orchestratoren importieren Skills, keine anderen Orchestratoren.
- Kein YAML-Runner, kein generisches Orchestrierungs-Framework.
- `main.py` ruft immer den Orchestrator, nie einzelne Skills direkt — auch nicht für Lern-Endpunkte.
- Lernen ist eine Methode des Orchestrators (`brief.learn_from_edits(...)`), die intern an `skills.learning.from_edits(...)` delegiert.

---

## Skills (workflow-spezifisch vs. cross-cutting)

- **Workflow-spezifischer Skill** → `workflows/<wf>/<section>/skill.py`.
- **Cross-cutting Skill** (in ≥ 2 Workflows nutzbar) → `skills/<name>/`.
- Faustregel: Starte unter `workflows/`, promote zu `skills/` erst bei tatsächlicher zweiter Verwendung.
- Aktuell qualifiziert sich nur "Lernen" als cross-cutting: `skills/learning/`.
- Jeder Skill hat eine `run(llm, ...)` Funktion (immer `async`).
- Skills geben immer einen primitiven Typ zurück (str, dict, Pydantic-Modell).
- Skills haben keine Seiteneffekte (kein Storage-Zugriff).
- Frontmatter wird von `_get_prompt()` gestripped — Skills sehen nur den Body.

---

## Tools (`backend/tools/patient_tools.py`)

- Jede Tool-Funktion: `load_patient → mutate → save_patient`.
- Pydantic-Args-Modell pro Tool; JSON-Schema aus `model_json_schema()` generieren.
- ULID-Generierung immer via `utils.ulid.generate_ulid()`.

---

## Prompts (in den jeweiligen Section-Ordnern)

- Dateiformat: Markdown mit YAML-Frontmatter.
- `_get_prompt()` bevorzugt `.md` über `.txt` (Backwards-Compat).
- Platzhalter-Format: `{snake_case}`.
- Kein Prompt als Python-String — alle Prompts als Dateien.

Pflichtfelder im Frontmatter (F2):
- `id`: Namespace-Pfad (`brief.diagnosen`, `verlauf.collect` etc.)
- `version`: ISO-Datum als String in Quotes (`"2026-05-07"`) — verhindert YAML-Date-Coercion
- `model`: bindender Modell-String für Client-Auflösung (z.B. `gemini-3-flash-preview`)
- `role`: `Literal["user", "system"]`
- `inputs`: `list[str]` aller `{placeholder}`-Slots im Body

`PromptFrontmatter` nutzt `model_config = ConfigDict(extra="allow")` für optionale Felder wie `description` (curate-Varianten).

---

## Schemas (`schema.py` im jeweiligen Section-Folder)

- Pydantic-Modelle für LLM-JSON-Mode-Outputs.
- Import ist immer relativ: `from .schema import DiagnosenOutput`.
- Renderer (`_render_diagnosen`, `_render_therapie`) leben im jeweiligen `skill.py` — keine geteilten Helpers (`workflows/_helpers.py` existiert nicht).
- Regex-Parsing von LLM-Output ist verboten. Immer `model_validate_json(raw)`.

---

## Lernlog

- **Patient-Snapshots:** `data/learning_snapshots/<workflow>/<P-NNNN>.yml` (gitignored).
  - Format: `{diagnosen: "...", anamnese: "...", therapie: "...", verlauf: "..."}` (brief) oder `{content: "..."}` (meilenstein).
- **User-Regelmengen:** `workflows/<wf>/<section>/lernlog/<user>.yml` (gitignored via Whitelist).
  - Whitelist-`.gitignore` in jedem `lernlog/`-Ordner committed.
- Bei Compound-Stages: Lernlog auf Compound-Level, nicht in Sub-Stages.
- `learning_storage.py` hat zwei separate Pfad-Funktionen: `_snapshot_path(workflow, pid)` und `_rules_path(workflow, section, user)`.

---

## Sicherheitsentscheidungen

### `update_status` — LLM-unsichtbar (F6)

`update_status` darf kein Tool-Schema erhalten. Der LLM soll den Patientenstatus (`aktiv`/`inaktiv`) nie selbst deaktivieren können. Die Funktion existiert, ist aber aus dem Tool-Schema-Set ausgeschlossen.

### `befunde` — kein Lernlog (F5)

`befunde` ist explizit aus `BRIEF_SECTIONS_WITH_LEARNING` ausgeschlossen. Fachliche Entscheidung: Befunde-Formatierung ist eine reine SAP-Text-Übernahme ohne generalisierbares Lernpotenzial. Kein API-Endpoint `/api/learn/brief/befunde/*`.

---

## Streaming-Transport — nicht anfassen (F11)

Das aktuelle SSE-Streaming zwischen `main.py` und Frontend ist heterogen gewachsen. Eine Harmonisierung ist möglich, aber kein Migrations-Ziel. Nicht anfassen, bis ein konkretes Feature es erfordert. Jede Änderung an Streaming-Logik muss explizit dokumentiert werden.

---

## Tests

- Alle Tests via `pytest`.
- `isolated_data`-Fixture für alle Storage-Tests.
- Prompt-Inhalts-Asserts schützen vor versehentlichem Löschen von Schlüssel-Klauseln.

---

## Verbotene Muster

- `import agent_*` — alte Dateinamen nicht in neuem Code verwenden.
- Prompts als Python-String-Templates (`string.Template`, `f-string`).
- Tool-Calling-Loop ohne `max_iterations` und `max_total_tokens`.
- Direktes Schreiben in `data/` ohne atomares `tmp + os.replace`.
- Regex- oder String-Split-Parsing von LLM-Freitext-Output — immer Pydantic.
- `skill.md` als Dateiname — Skills sind immer `skill.py` (Python-Module, keine Markdown-Beschreibungen).
- Orchestratoren in Section-Foldern — `orchestrator.py` existiert nur auf Workflow- oder Compound-Stage-Ebene.

---

## Offene Punkte

- **TODO**: `workflows/brief/verlauf/02_audit/` gibt heute Plain-Text zurück. Output-Schema (Pydantic-Modell) bei Gelegenheit nachziehen, analog zu `01_collect/CollectOutput`.
