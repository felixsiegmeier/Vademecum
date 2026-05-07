# workflows/brief/verlauf

Skill: generiert den Verlauf-Block eines Arztbriefs (3-Pass: collect → audit → curate).

Eingang: `Patient`-Objekt, `rules_block`, `extra_context`, sowie vorgerenderte Strings für
meilenstein, befunde_formatted, diagnosen, anamnese, therapie, adressatenprofil.
Ausgang: Plain-Text-Verlaufstext (Länge abhängig von SUBSTANZ_TIEFE: minimal/kompakt/ausführlich).

Lernfähig — Regeln in `lernlog/default.yml` (gitignored). Architekturkontext: `backend/AGENTS.md`.
