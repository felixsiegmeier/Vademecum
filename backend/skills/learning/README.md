# skills/learning

Cross-cutting Skill: Regelextraktion aus manuellen Brief- und Meilenstein-Korrekturen.

Public API:
- `from_edits(client, last_generated, edited, existing_rules, ...)` → extrahiert neue Regelkandidaten
- `rebuild(client, rule, clarification, ...)` → schärft einen Regelkandidaten nach

Konsumenten: `workflows/brief/orchestrator.py`, `workflows/meilenstein/orchestrator.py`.
Prompts in `prompts/` (rule_extraction, conflict_detection, rule_rebuild).
Architekturkontext: `backend/AGENTS.md`.
