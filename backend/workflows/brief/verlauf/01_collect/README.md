# workflows/brief/verlauf/01_collect

Pass 1 von 3 im Verlauf-Compound-Stage: Substanz-Sammlung.

Eingang: `patient_yaml`, `meilenstein`, `befunde`, `diagnosen`, `anamnese`, `therapie`, `extra_context`, `available_variants`.
Ausgang: `CollectOutput` (Pydantic) mit `substance: str` und `curate_variant: str`.

`curate_variant` bestimmt, welcher Prompt-Variant in Pass 3 geladen wird. Architekturkontext: `backend/AGENTS.md`.
