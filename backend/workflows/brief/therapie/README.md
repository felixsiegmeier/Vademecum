# workflows/brief/therapie

Skill: generiert den Therapie-Block eines Arztbriefs aus einem Patient-YAML (JSON → Markdown).

Eingang: `Patient`-Objekt, vorgerenderter `rules_block: str`, `extra_context: str`.
Ausgang: Markdown-String (Initial-OP, antimikrobielle Therapie, weitere Prozeduren).

Lernfähig — Regeln in `lernlog/default.yml` (gitignored). Architekturkontext: `backend/AGENTS.md`.
