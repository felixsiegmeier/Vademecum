# workflows/brief/verlauf/03_curate

Pass 3 von 3 im Verlauf-Compound-Stage: Format-spezifische Endredaktion.

Eingang: Auditierter Text aus Pass 2 + `curate_variant` aus Pass 1 + Adressatenprofil.
Ausgang: Verlaufs-Block als Plain-Text (Länge abhängig von Variante).

`prompts/` enthält `shared.md` und je eine `<variante>.md` (`minimal`, `kompakt`, `ausfuehrlich`).
User-erweiterbar: neue `.md`-Datei in `prompts/` wird automatisch als Variante erkannt.
Architekturkontext: `backend/AGENTS.md`.
