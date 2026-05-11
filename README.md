# arztbrief-app

Lokale Desktop-App zur KI-gestützten Erstellung von Arztbriefen. Backend: FastAPI + OpenAI-kompatible LLMs. Frontend: Vite + React + TypeScript + Tailwind.

## Lokale Entwicklung

```bash
# Backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.template .env  # API-Key + LLM_BACKEND eintragen

# Frontend
cd frontend && npm install

# Beide zusammen starten
make dev
```

## LLM-Backend wechseln

Über `.env` steuerbar — keine Code-Änderung nötig:

```
LLM_BACKEND=gemini     # Standard (Gemini via OpenAI-kompatibler API)
LLM_BACKEND=lmstudio   # Lokales Modell via LM Studio
```

Neues Backend: Eintrag in `backend/llm_client.py` → `_BACKENDS`-Dict ergänzen.

## Windows-Prototyp bauen

GitHub Actions baut automatisch ein portables Windows-Bundle (kein Python/Node.js nötig):

- **Artifact:** Push auf `main` → Actions-Tab → Artifact `arztbrief-windows`
- **Release:** `git tag v1.0.0 && git push origin v1.0.0` → erstellt GitHub Release mit ZIP

Die ZIP enthält `arztbrief.exe` (Doppelklick zum Starten). Beim ersten Start wird der API-Key abgefragt und in einer `.env` neben der `.exe` gespeichert. Patientendaten landen im `data/`-Ordner neben der `.exe`.
