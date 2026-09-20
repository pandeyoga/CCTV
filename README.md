# AI CCTV People Counter — MVP

Edge-processed people counting (enter/exit through one door) for a subscription SaaS.

- **Start here:** `AGENTS.md` (rules), then `docs/STATUS.md` (what is done / next).
- `edge_agent/` — Python edge agent (Stage 1, done). Run/tests: `edge_agent/README.md`.
- `backend/`, `frontend/` — FastAPI API + React/TS dashboard (login, ringkasan, perangkat, **Pengaturan** self-service). Roadmap: `docs/ROADMAP.md`.
- `contracts/` — generated event schema (SSOT in `edge_agent/edge_agent/contracts.py`).
- `docs/` — architecture, data model, decisions (ADRs), API contracts, status.
