# Backend (FastAPI + SQLAlchemy 2 async)

PostgreSQL in production (Docker Compose), SQLite in the hosted preview — same code, `DATABASE_URL` decides.

## Run locally with Docker Compose (repo root)
```bash
cp .env.compose.example .env.compose   # set POSTGRES_PASSWORD, CORS_ORIGINS, JWT_SECRET (>= 32 random chars)
docker compose --env-file .env.compose up --build
# api: http://localhost:8001/api/health  (migrations run automatically: alembic upgrade head)
docker compose --env-file .env.compose exec api \
  python -m app.seed --tenant "My Tenant" --contact-email you@example.com \
  --store "Store 1" --timezone Asia/Jakarta --camera cam-door-front --device dev-01
# -> prints device_api_key_SHOW_ONCE once; put it in the edge agent's EDGE_API_KEY
docker compose --env-file .env.compose exec -e DASHBOARD_PASSWORD='<password>' api \
  python -m app.users create --email owner@example.com --tenant "My Tenant"   # dashboard login (no public signup)
```

## Run without Docker
```bash
cd backend && pip install -r requirements.txt
export DATABASE_URL=sqlite+aiosqlite:///./data/people_counter.sqlite3   # or postgresql+asyncpg://...
export JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")   # or DASHBOARD_AUTH=disabled for local dev only
alembic upgrade head
uvicorn server:app --host 0.0.0.0 --port 8001
```

## Env vars
| var | required | notes |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql+asyncpg://…` or `sqlite+aiosqlite:///…` |
| `CORS_ORIGINS` | no | comma-separated; empty → `*` (pilot) |
| `JWT_SECRET` | yes (unless `DASHBOARD_AUTH=disabled`) | ≥ 32 chars; signs dashboard login tokens (ADR-018). Server refuses to start without it |
| `JWT_TTL_MINUTES` | no | default 720 |
| `ADMIN_EMAIL` + `ADMIN_PASSWORD` | no (set together) | platform admin seeded/re-synced at startup (ADR-024); password ≥ 10 chars. After that, everything else (tenants, stores, devices, users) is done in the dashboard `/pengaturan` |
| `DASHBOARD_AUTH` | no | `required` (default) or `disabled` — explicit local-dev mode, every tenant readable, `/api/auth/login` → 404 |
| `AUTO_CREATE_SCHEMA` | no | `true` only for throwaway dev DBs; production uses Alembic |

## Migrations
`alembic revision --autogenerate -m "..."` then review the file (replace `app.models.UTCDateTime(...)` with `sa.DateTime(timezone=True)` if autogenerate emits it) → `alembic upgrade head`.

## Tests
```bash
cd backend && python -m pytest tests -q
```
Includes: device auth (401/403), idempotent ingest, tenant isolation, payload identity spoof → 422, timezone bucketing (Asia/Jakarta), dashboard login/JWT/tenant scoping (`test_auth.py`), device heartbeat (`test_heartbeat.py`), contract drift vs `contracts/*.schema.json`, and the real edge `EventSender` / `HeartbeatSender` against the in-process app.

## Dashboard users (operator CLI, ADR-018)
```bash
DASHBOARD_PASSWORD='...' python -m app.users create --email owner@example.com --tenant "My Tenant"
python -m app.users grant --email owner@example.com --tenant "Other Tenant"
DASHBOARD_PASSWORD='...' python -m app.users set-password --email owner@example.com
python -m app.users list
```
Passwords: ≥ 10 chars, from `DASHBOARD_PASSWORD` (or interactive prompt), never printed. Emails must be real-looking (`EmailStr`; e.g. `.local` domains are rejected at login).
