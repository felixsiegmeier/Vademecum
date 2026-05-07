# workflows/document_extraction

Workflow: Medizinische Dokument-Extraktion — 2-Pass Multi-Turn-Tool-Loop.

| Stage | Zweck |
|-------|-------|
| Block 1 | Thematische Extraktion (12 Tools, max. 8 Iterationen) |
| Block 2 | Chronologische Extraktion (Verlaufseinträge, max. 5 Iterationen) |

Streaming-Transport: NDJSON. Tool-Loop-Infrastruktur: `utils/tool_loop.py`.
Architekturkontext: `backend/AGENTS.md`.
