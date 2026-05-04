# Backend Context — Stand 2026-05-04 (V1.6 Phase 3.5 Iter v2 Patches C/D/E)

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

### /api/uploads — akzeptierte Formate
Alle Formate werden in die bestehende 2-Pass-Block-1/Block-2-Pipeline eingespeist:

| Format | MIME-Typ | Konvertierung |
| --- | --- | --- |
| PDF | application/pdf | Nativ via Gemini PDF-Parts |
| Bild | image/jpeg, image/png, … | Nativ als Image-Parts |
| TXT | text/plain | UTF-8 dekodiert (Fallback latin-1) |
| Markdown | text/markdown | Wie TXT |
| CSV | text/csv | Markdown-Tabelle via csv stdlib |
| XLSX | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | Sheets als Markdown-Tabellen via openpyxl |
| DOCX | application/vnd.openxmlformats-officedocument.wordprocessingml.document | Absätze + Tabellen als Text via python-docx |

- TXT/MD/CSV/XLSX/DOCX werden als `content_type="text"` an `extract_proposals` übergeben
- `/api/extract-stammdaten` akzeptiert weiterhin nur PDF + Bilder (`_BINARY_UPLOAD_MIMES`)
- Unbekannter MIME → HTTP 415

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

## Test-Stand
106 passed in 0.40s
