.PHONY: dev backend frontend

dev:
	@trap 'kill 0' INT; \
	(cd backend && source .venv/bin/activate && uvicorn main:app --reload) & \
	(cd frontend && npm run dev) & \
	wait

backend:
	cd backend && source .venv/bin/activate && uvicorn main:app --reload

frontend:
	cd frontend && npm run dev
