# workflows/brief/anamnese

Skill: generiert den Anamnese-Block eines Arztbriefs aus einem Patient-YAML (Plain-Text-Output).

Eingang: `Patient`-Objekt, vorgerenderter `rules_block: str`, `extra_context: str`.
Ausgang: Plain-Text-String (kein JSON, kein Markdown-Wrapping).

Lernfähig — Regeln in `lernlog/default.yml` (gitignored). Architekturkontext: `backend/AGENTS.md`.
