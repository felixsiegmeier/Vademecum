# Backend Context — Stand 2026-05-02 (V1.6 Phase 2)

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
- id, kategorie (8 Werte: operativ|MCS|RRT|respiratorisch|interventionell|
  antimikrobiell|medikamentös|sonstiges), bezeichnung, beginn, ende?,
  indikation?, source_quote
- beginn=ende: einmaliges Event (z.B. OP)
- ende=null: noch laufend

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
- extraction_block1.txt: 8-Kategorie-Tag-Set, Datums-Logik (beginn=ende für Events)
- extraction_block2.txt: Verlaufseintrag-Generierung

## Cache-Hinweis
- _BLOCK1_PROMPT_CACHE / _BLOCK2_PROMPT_CACHE laden Prompts einmal beim
  ersten Request. Bei Prompt-Änderung: Backend-Restart nötig.

## Stammdaten-Extraktion (V1.6 Phase 2)

### StammdatenExtractResult
- name?, geburtsdatum? (YYYY-MM-DD), geschlecht? (m|w|d),
  bettplatz?, aufnahmedatum? (YYYY-MM-DD), aufnahme_quelle? (elektiv|notfall|extern)
- Alle Felder Optional/nullable
- Service: `agent_stammdaten_extraction.extract_stammdaten(client, file_bytes, mime_type)`

### POST /api/extract-stammdaten
- multipart/form-data, akzeptiert PDF + Bilder (gleiche MIME-Allowlist wie /api/uploads)
- Single-LLM-Call, JSON-Mode, temperature=0
- Response: StammdatenExtractResult (alle Felder null wenn kein Patientendokument)
- Kein Error bei unerkannten Dokumenten — nur null-Felder
- Prompt: `prompts/extract_stammdaten.txt`
- PDF-Fallback: bei APIStatusError → Konversion zu PNG-Seiten (wie /api/uploads)

## Apply-Endpoint
POST /api/patients/{id}/apply-proposals
- Transactional: delete fail → add skip in Update-Gruppe
- Proposal-Types: add | update_singleton | update (delete+add-pair)

## Test-Stand
78 passed in 0.46s
