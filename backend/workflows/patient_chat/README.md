# workflows/patient_chat

Workflow: Patienten-bezogener Chat — routing → single-pass oder 2-pass.

Eingang: `chat_message: str`, `Patient`-Kontext, persistente Chat-History aus `data/chat/`.
Ausgang: Streaming-Antwort (SSE) + persistierte History.

`system_prompt.md` enthält den Chat-System-Prompt (Jinja-Platzhalter `{{ patient_yaml }}`, `{{ today }}`).
Architekturkontext: `backend/AGENTS.md`.
