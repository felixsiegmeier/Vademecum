# workflows/brief/diagnosen

Skill: generiert den Diagnosen-Block eines Arztbriefs aus einem Patient-YAML.

Eingang: `Patient`-Objekt, vorgerenderter `rules_block: str`, `extra_context: str`.
Ausgang: Markdown-String (Behandlungs-, Verlaufs-, Vorbekannte-Diagnosen).

Lernfähig — Regeln in `lernlog/default.yml` (gitignored). Architekturkontext: `backend/AGENTS.md`.
