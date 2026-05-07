# 05 — data/-Audit: Inventar und Migrationsplan

Grundlage: `find backend/data -type f | sort` (Stand 2026-05-07).
Kein Löschen ohne explizite Bestätigung von Felix (Schritt 0.4b).

---

## Inventar-Tabelle

| Status | Aktueller Pfad | Neuer Pfad nach ICM | Begründung |
|--------|----------------|---------------------|------------|
| **KEEP-AND-MOVE** | `data/patients/P-0001.yml` | `data/patienten/P-0001.yml` | Aktive Patientenakte |
| **KEEP-AND-MOVE** | `data/patients/P-0002.yml` | `data/patienten/P-0002.yml` | Aktive Patientenakte |
| **KEEP-AND-MOVE** | `data/patients/P-0003.yml` | `data/patienten/P-0003.yml` | Aktive Patientenakte |
| **KEEP-AND-MOVE** | `data/briefs/P-0001.yml` | `data/briefe/P-0001.yml` | Neu-Brief-Snapshots (aktuelles System) |
| **KEEP-AND-MOVE** | `data/briefs/P-0002.yml` | `data/briefe/P-0002.yml` | Neu-Brief-Snapshots (aktuelles System) |
| **KEEP-AND-MOVE** | `data/briefs/P-0003.yml` | `data/briefe/P-0003.yml` | Neu-Brief-Snapshots (aktuelles System) |
| **KEEP-AND-MOVE** | `data/meilensteine/P-0001.md` | `data/meilensteine/P-0001.md` | Aktiver Meilenstein (Pfad bleibt) |
| **KEEP-AND-MOVE** | `data/meilensteine/P-0001.meta.json` | `data/meilensteine/P-0001.meta.json` | Staleness-Hash (Pfad bleibt) |
| **KEEP-AND-MOVE** | `data/meilensteine/P-0002.md` | `data/meilensteine/P-0002.md` | Aktiver Meilenstein |
| **KEEP-AND-MOVE** | `data/meilensteine/P-0002.meta.json` | `data/meilensteine/P-0002.meta.json` | Staleness-Hash |
| **KEEP-AND-MOVE** | `data/meilensteine/P-0003.md` | `data/meilensteine/P-0003.md` | Aktiver Meilenstein |
| **KEEP-AND-MOVE** | `data/meilensteine/P-0003.meta.json` | `data/meilensteine/P-0003.meta.json` | Staleness-Hash |
| **WIPE** | `data/meilensteine/P-0004.md` | — | Verwaister Meilenstein, keine Patientenakte vorhanden (Felix-Bestätigung 2026-05-07) |
| **WIPE** | `data/meilensteine/P-0004.meta.json` | — | Verwaister Meilenstein-Hash (analog) |
| **KEEP-AND-MOVE** | `data/learnings/default/brief/diagnosen/rules.yml` | `workflows/brief/diagnosen/lernlog/default.yml` | Aktive Lernregeln für Diagnosen |
| **KEEP-AND-MOVE** | `data/learnings/default/brief/verlauf/rules.yml` | `workflows/brief/verlauf/lernlog/default.yml` | Aktive Lernregeln für Verlauf |
| **KEEP-AND-MOVE** | `data/learnings/default/brief/diagnosen/last/P-0001.txt` | `data/learning_snapshots/brief/P-0001.yml` (diagnosen-Feld) | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/brief/diagnosen/last/P-0002.txt` | `data/learning_snapshots/brief/P-0002.yml` (diagnosen-Feld) | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/brief/diagnosen/last/P-0003.txt` | `data/learning_snapshots/brief/P-0003.yml` (diagnosen-Feld) | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/brief/anamnese/last/P-0001.txt` | `data/learning_snapshots/brief/P-0001.yml` (anamnese-Feld) | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/brief/anamnese/last/P-0002.txt` | `data/learning_snapshots/brief/P-0002.yml` (anamnese-Feld) | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/brief/anamnese/last/P-0003.txt` | `data/learning_snapshots/brief/P-0003.yml` (anamnese-Feld) | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/brief/therapie/last/P-0001.txt` | `data/learning_snapshots/brief/P-0001.yml` (therapie-Feld) | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/brief/therapie/last/P-0002.txt` | `data/learning_snapshots/brief/P-0002.yml` (therapie-Feld) | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/brief/therapie/last/P-0003.txt` | `data/learning_snapshots/brief/P-0003.yml` (therapie-Feld) | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/brief/verlauf/last/P-0001.txt` | `data/learning_snapshots/brief/P-0001.yml` (verlauf-Feld) | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/brief/verlauf/last/P-0002.txt` | `data/learning_snapshots/brief/P-0002.yml` (verlauf-Feld) | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/brief/verlauf/last/P-0003.txt` | `data/learning_snapshots/brief/P-0003.yml` (verlauf-Feld) | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/meilenstein/last/P-0001.txt` | `data/learning_snapshots/meilenstein/P-0001.yml` | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/meilenstein/last/P-0002.txt` | `data/learning_snapshots/meilenstein/P-0002.yml` | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/meilenstein/last/P-0003.txt` | `data/learning_snapshots/meilenstein/P-0003.yml` | Migrationsquelle für Snapshot |
| **KEEP-AND-MOVE** | `data/learnings/default/meilenstein/rules.yml` | `workflows/meilenstein/lernlog/default.yml` | Aktive Meilenstein-Lernregeln |
| **WIPE** | `data/learnings/default/last_meilenstein/P-0001.txt` | — | Veralteter Pfad (vor Lernlog-Refactoring); Inhalt durch `data/learnings/default/meilenstein/last/P-0001.txt` ersetzt |
| **WIPE** | `data/learnings/default/last_meilenstein/P-0002.txt` | — | Veralteter Pfad (analog) |
| **WIPE** | `data/learnings/default/last_meilenstein/P-0003.txt` | — | Veralteter Pfad (analog) |
| **WIPE** | `data/learnings/default/meilenstein.yml` | — | Veraltete Flat-File vor Subfolder-Strukturierung; durch `meilenstein/rules.yml` ersetzt |
| **KEEP** | `data/briefe/.gitkeep` | `data/briefe/.gitkeep` | Gitkeep bleibt, Ordner bereits ICM-korrekt benannt |
| **WIPE** | `data/briefs/.gitkeep` | — | Redundant nach Umbenennung zu `data/briefe/` (Schritt 0.3) |
| **KEEP** | `data/audit/.gitkeep` | `data/audit/.gitkeep` | Audit-Ordner bleibt |
| **KEEP** | `data/patients/.gitkeep` | Verschiebt zu `data/patienten/` | Nach Schritt 0.3 in neuen Ordner |
| **KEEP** | `data/meilensteine/.gitkeep` | `data/meilensteine/.gitkeep` | Pfad bleibt |
| **KEEP-AND-MOVE** | `data/chat/<P-NNNN>.json` (sofern vorhanden) | `data/chat/<P-NNNN>.json` (Pfad bleibt vorerst) | Persistente Chat-History; Untersuchung in R-9 |

---

## Open Questions — alle geklärt (2026-05-07)

1. **P-0004**: Verwaister Meilenstein → WIPE (siehe Tabelle).
2. **`data/chat/`**: Persistenter Chat-Speicher war ursprünglich als Session-Memory geplant, ist aber tatsächlich auf Disk persistiert. Klärung erfolgt nach ICM-Migration; siehe `01-analysis.md` R-9. Im Audit als KEEP-AND-MOVE behandeln; Pfad bleibt vorerst `data/chat/` (Umbenennung zu `data/gespraeche/` hängt von R-9-Ergebnis ab).
3. **`brief/anamnese/` und `brief/therapie/` ohne `rules.yml`**: Korrekt — keine Lernregeln vorhanden, weil noch nicht trainiert. `lernlog/`-Ordner werden leer angelegt (mit `.gitignore`, `README.md`, `example.yml`); `default.yml` entsteht erst beim ersten Lerntrigger.

---

## Schritt 0.4 in 03-migration-plan.md

Details zu den vier Sub-Schritten (0.4a–0.4d) sind in `03-migration-plan.md` Schritt 0.4 beschrieben. Die Inventar-Tabelle oben ist die Grundlage für Schritt 0.4b (User-Approval).

**Wichtig:** Schritt 0.4 (data/-Audit) ist Voraussetzung für Phase 1 (Lernlog-Migration 1.6).
