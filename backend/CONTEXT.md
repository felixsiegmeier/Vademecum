# Backend Context — Stand 2026-04-29

## Pydantic-Modelle (kompakt)

### Patient
- stammdaten (Stammdaten), anamnese, therapieziel, status,
  behandlungsdiagnosen[], verlaufsdiagnosen[], vorbekannte_diagnosen[],
  prozeduren[], befunde[], therapien[], verlaufseintraege[]

### Stammdaten
- id, name, geburtsdatum?, geschlecht?, bettplatz?, aufnahmedatum,
  aufnahme_quelle?, verlegungsziel?, aktiv (bool, default true)

### Diagnose
- id, text, datum?, source_quote

### Prozedur
- id, text, datum, source_quote

### Befund
- id, art, text, datum, source_quote

### Therapie
- id, kategorie (antimikrobiell|operativ|medikamentös|konservativ|sonstiges),
  bezeichnung, beginn, ende?, indikation, source_quote

### VerlaufsEintrag
- id, text, datum, source_quote

## Tool-Inventar (14 Tools)

### add_*
- add_behandlungsdiagnose(text, datum?, source_quote)
- add_verlaufsdiagnose(text, datum?, source_quote)
- add_vorbekannte_diagnose(text, datum?, source_quote)
- add_prozedur(text, datum, source_quote)
- add_befund(art, text, datum, source_quote)
- add_therapie(kategorie, bezeichnung, beginn, ende?, indikation, source_quote)
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
- delete_entry(liste, id)
  liste enum: behandlungsdiagnosen|verlaufsdiagnosen|vorbekannte_diagnosen|
              prozeduren|befunde|therapien|verlauf

## Multi-Turn-Loop-Konstanten
- MAX_ITERATIONS_BLOCK_1 = 8
- MAX_ITERATIONS_BLOCK_2 = 5
- THINKING_BUDGET_BLOCK_1 = 512
- THINKING_BUDGET_BLOCK_2 = 1024

## Prompt-Files (aktuelle Größen)
- extraction_block1.txt: 85 Zeilen, 3.8 KB
- extraction_block2.txt: 43 Zeilen, 1.8 KB

## Cache-Hinweis
- _BLOCK1_PROMPT_CACHE / _BLOCK2_PROMPT_CACHE laden Prompts einmal beim
  ersten Request. Bei Prompt-Änderung: Backend-Restart nötig.

## Apply-Endpoint
POST /api/patients/{id}/apply-proposals
- Transactional: delete fail → add skip in Update-Gruppe
- Proposal-Types: add | update_singleton | update (delete+add-pair)

## Test-Stand
61 passed in 0.27s
