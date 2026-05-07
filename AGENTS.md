# AGENTS.md — Repo-weite Konventionen

Kardiologische ICU-Dokumentationshilfe (DHZC Berlin).
Vokabular: **Workflow, Stage, Skill, Task, Tool**. Das Wort "Agent" erscheint nicht in neuem Code.

---

## Sprach-Regel (M3)

Hybride Namenskonvention: technische Strukturen auf Englisch, Domain-Konzepte auf Deutsch.

| Ebene | Sprache | Beispiele |
|-------|---------|-----------|
| Tech-Strukturen (Top-Level) | Englisch | `data/`, `workflows/`, `skills/`, `tests/`, `utils/` |
| Domain-Daten-Container | Deutsch | `data/briefe/`, `data/patienten/`, `data/lernlog/` |
| Domain-Begriffe innerhalb Workflows | Deutsch | `workflows/brief/diagnosen/`, `verlauf/`, `anamnese/` |
| API-Routen | Englisch-Topologie + deutsche Domain | `/api/brief/{id}/diagnosen`, `/api/patienten/{id}` |
| Code-Identifier | Englisch-Verb + deutsche Domain-Substantive | `def generate_diagnosen()`, `class DiagnosenOutput` |

---

## Top-Level-Topologie

```
arztbrief-app/
├── backend/               # FastAPI-Anwendung (Python)
│   ├── main.py            # HTTP-Schicht
│   ├── workflows/         # Workflow-Orchestratoren + Section-Skills
│   ├── skills/            # Cross-cutting Skills (≥ 2 Workflows)
│   ├── tools/             # Patient-Mutations-Tools (Pydantic-Args)
│   ├── utils/             # Geteilte Utilities (ULID, Prompts, Auth)
│   ├── models/            # Pydantic-Domänenmodelle
│   ├── data/              # Runtime-Daten (gitignored, außer Struktur)
│   └── tests/             # pytest-Tests
├── frontend/              # Vite + React + Tailwind
├── docs/                  # Architektur- und Migrationsdokumentation
└── AGENTS.md              # Diese Datei
```

---

## Branch-Naming

```
main                                      # immer stabil, direktes Deployment
feature/<kurzbeschreibung>                # neue Features
fix/<kurzbeschreibung>                    # Bug-Fixes
refactoring/<kurzbeschreibung>            # strukturelle Umbauten ohne Verhaltensänderung
```

---

## Commit-Konventionen

Format: `<type>(<scope>/<step>): <kurze Beschreibung>`

Typen: `feat`, `fix`, `test`, `refactor`, `docs`, `chore`

Beispiele:
```
feat(brief/c1.8-b): drei format-spezifische Curate-Prompts
fix(brief/c1.7.5-b): SICHERHEITS-PFLICHT-INHALTE reformuliert
refactor(icm/0.4): data/-Wipe + Storage-Pfad-Migration
docs(icm/0.2): AGENTS.md anlegen
```

---

## README-Pflicht (M1)

Jeder neu angelegte Ordner bekommt eine `README.md` (3–10 Zeilen: was passiert hier, welche Dateien erwartet, Verweis auf AGENTS.md). Gilt für alle Workflow-, Section-, Skill- und `lernlog/`-Ordner.

---

## Patientendaten-Sicherheit

- `backend/data/patienten/`, `backend/data/briefe/`, `backend/data/lernlog/`, `backend/data/learning_snapshots/` sind gitignored — **niemals committen**.
- `backend/test_data/*.pdf` und `backend/test_data/celik_*.md` sind gitignored.
- Atomares Schreiben via `tmp + os.replace` überall in Storage-Modulen.

---

## Python-spezifische Konventionen

Siehe [`backend/AGENTS.md`](backend/AGENTS.md).
