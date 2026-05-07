# workflows/brief/polish

Lektor-Prompts für die manuelle Nachkorrektur einzelner Sektionen.

| Prompt-Datei | Verwendung |
|---|---|
| `brief_section_polish.md` | `polish_section` für diagnosen, anamnese, therapie |
| `brief_verlauf_polish.md` | `polish_section` für verlauf (max_tokens=4096) |
| `brief_befunde_format.md` | `format_sap_befunde` — SAP-Roh-Text → formatierter Block |

Kein `lernlog/` — Polish ist eine One-Shot-Korrektur. Architekturkontext: `backend/AGENTS.md`.
