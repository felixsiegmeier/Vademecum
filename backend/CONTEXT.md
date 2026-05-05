# Backend Context — Stand 2026-05-05 (Phase E — FE shadcn/ui-Migration)

## Pydantic-Modelle (kompakt)

### Patient
- stammdaten (Stammdaten), anamnese, therapieziel,
  behandlungsdiagnosen[], verlaufsdiagnosen[], vorbekannte_diagnosen[],
  befunde[], therapien[], verlaufseintraege[]
- **Kein `prozeduren`-Feld mehr** (V1.6 Phase 1: merge in therapien)

### Stammdaten
- id, name, geburtsdatum?, geschlecht?, bettplatz?, aufnahmedatum,
  aufnahme_quelle?, verlegungsziel?, aktiv (bool, default true)

### Diagnose
- id, text, datum?, source_quote

### Befund
- id, art, text, datum, source_quote

### Therapie
- id, kategorie (9 Werte: operativ|MCS|RRT|respiratorisch|interventionell|
  antimikrobiell|medikamentös|bedside|sonstiges), bezeichnung, beginn, ende?,
  indikation?, source_quote
- beginn=ende: einmaliges Event (z.B. OP)
- ende=null: noch laufend
- `bedside` (Iter v2): Bedside-Eingriffe auf Station — PAK/Shaldon-Anlage,
  Pleurapunktion, Bronchoskopie, Bedside-Tracheotomie, Magensonde,
  Drainagen-Wechsel mit Konsequenz. `respiratorisch` ist seit Iter v2 nur
  Atemunterstützungs-MODI (Beatmung, NIV, HFNC) — Tracheotomie ist Eingriff,
  nicht Modus. Keine Backwards-Compat: bei vorhandenen YAMLs `rm` + Re-Upload.

### VerlaufsEintrag
- id, text, datum, source_quote

## Tool-Inventar (13 Tools)

### add_*
- add_behandlungsdiagnose(text, datum?, source_quote)
- add_verlaufsdiagnose(text, datum, source_quote)
- add_vorbekannte_diagnose(text, source_quote)
- add_befund(art, text, datum, source_quote)
- add_therapie(kategorie, bezeichnung, beginn, ende?, indikation?, source_quote)
- add_verlaufseintrag(text, datum, source_quote)

### update_* (singletons)
- update_stammdaten(feld, wert, source_quote)
  feld enum: name|geburtsdatum|geschlecht|aufnahmedatum|aufnahme_quelle
- update_anamnese(text, source_quote)
- update_therapieziel(text, source_quote)
- update_status(aktiv: bool, source_quote)
- update_bettplatz(bettplatz, source_quote)
- update_verlegungsziel(verlegungsziel, source_quote)

### delete_*
- delete_entry(id)
  sucht über alle Listen: behandlungsdiagnosen|verlaufsdiagnosen|
  vorbekannte_diagnosen|befunde|therapien|verlaufseintraege

## Multi-Turn-Loop-Konstanten
- MAX_ITERATIONS_BLOCK_1 = 8
- MAX_ITERATIONS_BLOCK_2 = 5
- THINKING_BUDGET_BLOCK_1 = 512
- THINKING_BUDGET_BLOCK_2 = 1024

## Prompt-Files
- extraction_block1.txt (Iter 5 + Patches C/D/E):
  - 9-Kategorie-Tag-Set inkl. `bedside`, ANTI-CONFOUND-Klausel als Priorität 1
  - Klinisch geschärfte Diagnose-Klassifikation mit konkreten Beispielen
  - Therapie-Recall-Verstärkung (alle AB-Linien, pharma. Hauptlinien, Bedside)
  - Befund-Recall-Liste (TEE, HIT, PAK-Messungen, Bronchoskopie-Befunde)
  - Anamnese-Vollständigkeitsklausel
  - **Patch C:** Aufnahmedatum-Klausel — stationäre/ITS-Aufnahme im DHZC, NICHT
    ambulantes Aufnahmegespräch/Sprechstunde; bei Doppelterminen: späteres Datum
  - **Patch D:** Vorerkrankungen-Granularität — jede Vorerkrankung als eigenes
    `add_vorbekannte_diagnose`-Item (NICHT clustern); Negativ-Beispiel mit 7er-Liste
  - **Patch E:** Therapie-`ende`-Differenzierung — `ende` nur bei explizit
    dokumentierter Beendigung; wenn Therapie am letzten Doku-Tag noch läuft → `ende: null`
- extraction_block2.txt (Iter v2): Verlaufseintrag-Generierung mit
  Konvergenz-Prinzip, 8 MUSS/SOLL/KANN-Dimensionen als Prüfliste,
  Mittelweg-Redundanz, 3 klinische Beispiele inkl. Mikrobio-Trigger-Merge

## Cache-Hinweis
- _BLOCK1_PROMPT_CACHE / _BLOCK2_PROMPT_CACHE laden Prompts einmal beim
  ersten Request. Bei Prompt-Änderung: Backend-Restart nötig.

## Datei-Format-Support (Phase 5)

### POST /api/uploads — Streaming-Endpoint (Phase D Iter 3)

**Transport:** NDJSON über chunked HTTP (`application/x-ndjson`)  
**Header:** `X-Accel-Buffering: no` (verhindert Nginx-Pufferung in Reverse-Proxy-Setups)  
**Warum kein SSE:** Endpoint ist POST (File-Upload), Browser `EventSource` unterstützt nur GET/HEAD.

Der Sync-Endpoint wurde gelöscht — kein Dual-Maintenance.

#### Event-Schema (5 Typen, ein JSON-Objekt pro Zeile + `\n`)

```jsonc
// status — vor jedem LLM-Call; items_in_phase zählt add_*-Calls kumulativ in der Phase
{"type": "status", "phase": "block1", "iter": 1, "max_iter": 8, "items_in_phase": 0}

// heartbeat — alle ~5s während laufendem LLM-Call (Reverse-Proxy Idle-Timeout-Schutz)
{"type": "heartbeat"}

// proposals — nach erfolgreichem Tool-Batch (ganzer Batch, kein Drip per Item)
// items: Liste von gruppierten Proposal-Dicts (gleiche Struktur wie apply-proposals)
{"type": "proposals", "phase": "block1", "items": [{"type": "add", "call": {...}, ...}]}

// done — am Ende beider Pässe; auto_skipped=true wenn total_proposals==0
{"type": "done", "total_proposals": 3, "auto_skipped": false}

// error — bei Retry-Erschöpfung oder LLM-Exception; Stream endet danach
{"type": "error", "message": "LLM provider instability ...", "retryable": true}
```

**Event-Reihenfolge:** status → heartbeat* → proposals (pro Iteration) → status → ... → done  
**Bei Error:** alles verwerfen (kein Resume). Frontend soll den User neu starten lassen.

#### Heartbeat-Pattern

- `_yield_heartbeats_and_run(coro, out)` startet den LLM-Call als asyncio.Task
- Polling via `asyncio.wait([llm_task, heartbeat_task], return_when=FIRST_COMPLETED)`
- Alle 5 s (`_HEARTBEAT_INTERVAL`) wird `{"type": "heartbeat"}` geliefert
- Task-Cleanup (cancel + await) im `finally`-Block

#### Akzeptierte Formate

| Format | MIME-Typ | Konvertierung |
| --- | --- | --- |
| PDF | application/pdf | Nativ via Gemini PDF-Parts |
| Bild | image/jpeg, image/png, … | Nativ als Image-Parts |
| TXT | text/plain | UTF-8 dekodiert (Fallback latin-1) |
| Markdown | text/markdown | Wie TXT |
| CSV | text/csv | Markdown-Tabelle via csv stdlib |
| XLSX | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | Sheets als Markdown-Tabellen via openpyxl |
| DOCX | application/vnd.openxmlformats-officedocument.wordprocessingml.document | Absätze + Tabellen als Text via python-docx |

- TXT/MD/CSV/XLSX/DOCX werden als `content_type="text"` an `extract_proposals_streaming` übergeben
- `/api/extract-stammdaten` akzeptiert weiterhin nur PDF + Bilder (`_BINARY_UPLOAD_MIMES`)
- Unbekannter MIME → HTTP 415 (vor Stream-Start, noch als normaler HTTP-Fehler)

## Stammdaten-Extraktion (V1.6 Phase 2)

### StammdatenExtractResult
- name?, geburtsdatum? (YYYY-MM-DD), geschlecht? (m|w|d),
  bettplatz?, aufnahmedatum? (YYYY-MM-DD), aufnahme_quelle? (elektiv|notfall|extern)
- Alle Felder Optional/nullable
- Service: `agent_stammdaten_extraction.extract_stammdaten(client, file_bytes, mime_type)`

### POST /api/extract-stammdaten
- multipart/form-data, akzeptiert nur PDF + Bilder (`_BINARY_UPLOAD_MIMES`, enger als /api/uploads)
- Single-LLM-Call, JSON-Mode, temperature=0
- Response: StammdatenExtractResult (alle Felder null wenn kein Patientendokument)
- Kein Error bei unerkannten Dokumenten — nur null-Felder
- Prompt: `prompts/extract_stammdaten.txt`
- PDF-Fallback: bei APIStatusError → Konversion zu PNG-Seiten (wie /api/uploads)

## Apply-Endpoint
POST /api/patients/{id}/apply-proposals
- Transactional: delete fail → add skip in Update-Gruppe
- Proposal-Types: add | update_singleton | update (delete+add-pair)
- Request-Body: `{ proposals: [...], force: bool = False }`

### Mismatch-Detection (V1.6 Phase 3)
- Identitätsfelder: `name`, `geburtsdatum`, `geschlecht`
- Trigger: update_stammdaten auf ein Identitätsfeld, current != null/leer, current != proposed
- Antwort bei Konflikt: HTTP 409 `{ mismatch_warning: true, conflicting_fields: [{feld, current, proposed}] }`
- Keine YAML-Änderung bei 409 (atomar)
- `force: true` im Request überspringt den Check komplett

## Block-2 State-Aware (V1.6 Phase 3.5 — Iter v2)

- Block 2 bekommt ALLE existierenden Verlaufseinträge im System-Prompt
- Format: `[YYYY-MM-DD] (id=...) Preview` (max. 250 Zeichen pro Eintrag)
- XML-Tag: `<existierende_verlaufseintraege>` (kein Eintrag → `keine`)
- Helper: `_compact_verlauf_overview(patient)` in `agent_document_extraction.py`
- Prompt (extraction_block2.txt, Iter v2): Skip/Update/Add-Logik mit Konvergenz-Prinzip
  - SKIP: Tag bereits vollständig erfasst, keine neue klinische Info
  - UPDATE: `delete_entry` + `add_verlaufseintrag` ZWINGEND im selben Turn; Merge (kein Replace)
  - ADD: Tag noch kein Eintrag
  - **Konvergenz statt Idempotenz**: Re-Upload soll anreichern, kein Durchlaufen — Merge ist sicher
  - **8 Dimensionen als MUSS/SOLL/KANN-Prüfliste** (keine Output-Struktur):
    MUSS: Therapie-Trigger/Begründung, Akute Events, Gespräche/Therapieziel, Mikrobio-Steuerung
    SOLL: Klinische Tendenz, Bedside-Eingriffe, Pflege-Beobachtungen mit Konsequenz
    KANN: Klinisches Tagesbild (RASS, Hämodynamik, Diurese)
  - **Mittelweg-Redundanz**: klinisch wichtige Items namentlich im Narrativ, nicht als Liste
  - **Tool-Trennung**: Block 2 ruft ausschließlich Verlauf-Tools auf (kein add_behandlungsdiagnose o.ä.)
- Übergangstag (Früh+Spät): automatisch als UPDATE-Gruppe abgebildet

## Chat-Endpoint (V1.6 Phase 4)

### POST /api/patients/{id}/chat — neues Routing

**Kurze Inputs (≤ 2000 Zeichen, `CHAT_2PASS_CUTOFF`):**
- Single-Pass via `run_single_pass_chat()` in `agent_patient_chat.py`
- LLM-natives Routing: Tool-Call → `proposals`, Text-Antwort → `reply`
- Kein vorgeschaltetes Klassifizierungsmodell

**Lange Inputs (> 2000 Zeichen):**
- 2-Pass-Pipeline wie Upload-Endpoint (profitiert von Phase-3.5-Idempotenz)
- `reply` ist immer `null`

### Response-Schema (neu)
```json
{
  "proposals": [...],
  "auto_skipped": bool,
  "message": "...",   // optional, nur bei auto_skipped
  "reply": "..." | null  // LLM-Textantwort (Single-Pass-Pfad)
}
```

### System-Prompt Routing-Logik
- Hypothetisch/Fragen/Diskussion → Text, KEINE Tools (Beispiele 7-9 im Prompt)
- Faktische Zustandsmeldung/Dokument-Paste → Tool-Call (Beispiel 10)
- Im Zweifel: Text bevorzugen

### Konstanten
- `CHAT_2PASS_CUTOFF = 2000` (in `agent_patient_chat.py`)

## Frontend Streaming-Pattern (Phase D Iter 3)

### NDJSON-Consumer (`frontend/src/utils/ndjson.ts`)
- `parseNdjson<T>(body: ReadableStream)` — AsyncGenerator, yields one event per line
- TextDecoder mit Line-Buffer; `releaseLock()` im finally für sauberes Early-Break
- Konsumiert via `for await (const event of parseNdjson<StreamEvent>(res.body))`

### Section-Counter (`frontend/src/utils/streamSection.ts`)
- `formatSectionCounts(proposals)` → `"2 Diagnosen, 4 Therapien, 1 Befund"`
- Reihenfolge: Diagnosen | Therapien | Befunde | Verlauf | Sonstiges
- Tool→Section-Mapping: alle `add_*`-Tools → Section, Rest → Sonstiges

### State-Modell im ProposalsEntry (Streaming)
- `streaming: boolean` — true während NDJSON-Stream aktiv
- `streamStatus: {phase, iter, max_iter, items_in_phase} | null`
- `proposals: Proposal[]` — wächst inkrementell bei jedem `proposals`-Event
- `updateEntryById` — funktionale setState-Updates (async-sicher, kein Stale-Closure)

### Upload-Flow
1. Streaming-ProposalsEntry sofort in History eingetragen (Live-Bar sichtbar)
2. `for await` über Events: heartbeat ignorieren, status → streamStatus, proposals → akkumulieren
3. `error`-Event → Toast + Entry discarden (kein Half-State)
4. `done` mit `auto_skipped` → Entry durch AutoSkipEntry ersetzen (gleiche Position)
5. `done` ohne Skip → `streaming: false`, Apply-Bar aktiv

### Streaming-UI in ProposalsEntry
- Header zeigt Section-Counts während Stream statt Global-Count
- Sticky Live-Bar (amber): `Loader2 animate-spin` + `"Block 1 — Iteration 2/8, 7 Items bisher"`
- Cards laufen progressiv ein; Checkboxen/Toggles mid-stream interagierbar
- Apply-Bar: disabled + Loader2 während `streaming`, aktiv nach `done`

### Chat-Markdown-Rendering
- `react-markdown` für Assistant-Replies in `PatientChatPanel` (`chat-text` role=assistant)
- `prose prose-sm` ohne `@tailwindcss/typography`-Plugin (Tailwind 4 default genügt)
- User-Messages: weiterhin `whitespace-pre-wrap`

## Frontend-Stack (Phase E — shadcn/ui)

### Tooling
- **Tailwind 4** via `@tailwindcss/vite`-Plugin (kein PostCSS, kein `tailwind.config.js`).
  Theme + CSS-Variablen liegen komplett in `frontend/src/index.css` via `@theme inline`.
- **shadcn/ui v4.6** mit `radix-nova`-Preset (Radix-UI primitives, Geist Variable Font,
  Lucide-Icons). `components.json` definiert Pfad-Aliase (`@/components/ui`, `@/lib/utils`).
- **Path-Alias `@/*`** in `tsconfig.json` + `vite.config.ts`.
- Komponenten in `frontend/src/components/ui/`: button, card, dialog, input, textarea,
  select, checkbox, separator, badge, tooltip, scroll-area, sonner, tabs, skeleton,
  avatar, label.

### Design-Tokens (`index.css`)
- Light-only (kein Dark-Mode-Toggle, klinik-tageslicht).
- Slate-tinted Neutrals (chroma 0.003–0.046 in OKLCH-Blau-Achse).
- Primary = blue-600 (`oklch(0.546 0.215 262.881)`).
- `--radius: 0.5rem` (medium, weniger consumer-y als shadcn-Default).
- Compact density: Button-Default `h-8`, Input `h-8`, Card-Padding `p-4`,
  Section-Spacing `space-y-3`/`space-y-4`.

### Toasts
- **Sonner** (`@/components/ui/sonner`) statt eigener `Toast.tsx` (gelöscht).
- Toaster auf App-Root außerhalb Dialog-Subtrees gemountet
  → behält Stacking-Context-Vertrag bei (Toasts erscheinen über Dialog-Backdrop).
- API: `toast.success/error/warning/info(text)`.

### Komponenten-Migration (1:1 visual, State-Logic unangetastet)
- **ProposalCard**: Checkbox/Input/Textarea/Select/Label/Badge/Button, Border-Tinting
  per Proposal-Type (delete=destructive, update=amber, add=blue) bei `selected`,
  muted-grau bei deselected. Diff-View für update-Gruppen.
- **PatientChatPanel**: Chat-Bubbles (User=primary, AI=muted+border), `prose prose-sm`
  für Markdown, Sticky Live-Bar (`amber-50` + Loader2), Apply-Bar als gerader
  primary-Button-Footer, Mismatch-Modal als shadcn Dialog mit `AlertTriangle` (amber).
- **NewPatientDialog**: shadcn Dialog, Input/Select/Label-Form, Drop-Zone als
  gestrichelte Card mit Upload-Icon und Loader2 während Stammdaten-Extract.
- **Sidebar**: Compact-Liste mit `border-l-2 border-primary` für aktive Patienten,
  ScrollArea, Filter-Tabs als Button-Pair, "+Neu" als ghost-Button.
- **PatientLanding**: shadcn Tabs (variant=line) für Chat/Meilenstein/Brief mit
  navigation-driven `onValueChange`. Delete-Confirm als Dialog mit destructive-Button.
- **BriefPanel/MeilensteinPanel**: Lucide-Icons für Toolbar (Copy/Check/RefreshCw),
  Stale-Banner amber-50, Regen-Confirm als Dialog.

### Bewusst NICHT migriert
- Globaler App-Header (h-12, App-Name + Avatar): Single-User-App, jeder Page-Header
  würde dupliziert werden → visueller Lärm. Sidebar enthält Branding-Pfad.
- DropdownMenu-Komponente (nicht im Order-Scope) → Patient-Action-Menü als
  einfacher absolute-positioned Toggle mit shadcn-getunten Klassen.

### Datenschutz-Hinweis: backend/data/ Git-History
- Commit `5dbb7ba` entfernte Patientendaten aus Tracking (nur `.gitkeep` im Index)
- **Initial commit `2b1258c` enthält noch Patientendaten in der Git-History**
- Cleanup: `git filter-repo` oder GitHub Support notwendig (Felix-Entscheidung ausstehend)

## Meilenstein-Endpoint (V1 — Meilenstein-Neufassung)

### POST /api/patients/{id}/meilenstein/generate

**Request Body** (optional JSON):
```json
{ "current_meilenstein": "<plain-text>" | null }
```

**Zwei Modi:**
- **GENERATIONS-MODUS**: `current_meilenstein` leer/null → Übersicht rein aus YAML
- **KONSOLIDIERUNGS-MODUS**: `current_meilenstein` gefüllt → LLM bekommt `<aktueller_meilenstein>`-Block; manuelle Einträge (Studienpatient, Sprachbarriere, etc.) werden bewahrt, YAML-Daten aktualisiert

**User-Message-Struktur:**
```
<patient_yaml>...YAML...</patient_yaml>

<generierungsdatum>YYYY-MM-DD</generierungsdatum>

<aktueller_meilenstein>...nur wenn gefüllt...</aktueller_meilenstein>
```

**Response:** `{ "content": "<plain-text>", "generated_at": "ISO", "is_stale": false }`

**Postprocessing:** LLM-Output wird aus ` ```plain text ... ``` ` Code-Block-Markern extrahiert. Kein JSON-Mode.

**Prompt-Cache:** `_MEILENSTEIN_SYSTEM_PROMPT` in `main.py` lädt `prompts/meilenstein_system.txt` beim ersten Request. Bei Prompt-Änderung: Backend-Restart nötig.

**Output-Format (V1, nach Smoketest-Patches):** `=== Patientenübersicht ===` als Haupt-Header, **8 Sektionen** mit `== Sektion ==` Format (Besonderheiten-Sektion gestrichen — empirisch fehleranfällig). Keine VERLAUF-Sektion. Kein Leerzeilen-Gap zwischen Sektion-Header und erstem Listenpunkt. temperature=0.

**Aktive Klauseln (Smoketest-Patches):**
- KHK-Konsolidierung: vorbekannte Stents/CABG in Behandlungsdiagnose integrieren, nicht in Nebendiagnosen
- Diagnose-Granularität: Erreger/Anatomie/Stadium anreichern wenn im YAML
- Antikoag 3-Layer kumulativ: ALLE parallelen Indikationen nennen (inkl. bMKE-Negativbeispiel)
- Kardiale Funktion: Zeile 3 weggelassen wenn keine Tendenz (kein `—`-Platzhalter); Verlaufs-Pharmako-Aussagen verboten
- Allergien-MUSS: IMMER als eigene Zeile, kein klinischer Cutoff
- Vorbekannt-Default: übernehmen, nur eindeutige Bagatellen filtern
- Suffix-Cleaning: Meropenem-1 → Meropenem in Antimikrobiell-Output
- Eingriff-Detail aus source_quote: Bypass-Konfiguration/Lateralität integrieren

**Folge-Order ausstehend:** Order B — Lernlog (noch nicht implementiert).

## Test-Stand
131 passed in 0.85s
