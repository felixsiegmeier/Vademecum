# arztbrief-app

Lokale Desktop-App zur KI-gestützten Erstellung von Arztbriefen. Backend: FastAPI + Gemini. Frontend: Vite + React + TypeScript + Tailwind.

## Setup

```bash
# Backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.template .env  # GEMINI_API_KEY eintragen

# Frontend
cd frontend && npm install

# Beide zusammen starten
make dev
```
