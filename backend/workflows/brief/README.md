# workflows/brief

Workflow: Arztbrief-Generierung — 4 Sektionen + Pre-Pass + Lektor.

| Section | Zweck |
|---------|-------|
| `diagnosen/` | Diagnosen-Block als Markdown-Liste |
| `anamnese/` | Anamnese-Block als Plain-Text |
| `therapie/` | Therapie-Block als Markdown-Liste |
| `befunde/` | Befunde-Vorformatierung (SAP-Text, nicht lernfähig) |
| `verlauf/` | Compound-Stage: collect → audit → curate (3-Pass) |
| `polish/` | Lektor-Korrektur einer einzelnen Sektion |

Orchestrator: `orchestrator.py`. Architekturkontext: `backend/AGENTS.md`.
