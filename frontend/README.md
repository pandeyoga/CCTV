# Dashboard (React 19 + TypeScript)

```bash
cd frontend && yarn install
# .env: REACT_APP_BACKEND_URL=<backend origin>  (required)
#       REACT_APP_DASHBOARD_AUTH=disabled   (ONLY when the backend runs with DASHBOARD_AUTH=disabled; skips the login page)
#       REACT_APP_STORE_ID=<uuid>  (optional default store)
yarn start        # dev server on :3000
yarn build        # production build in build/
CI=true yarn craco test --watchAll=false   # unit tests (src/**/*.test.ts)
```

Login: `/login` (email + password provisioned by the operator via `backend: python -m app.users`). The JWT is kept in `localStorage` (`pc.session.v1`) and sent as `Authorization: Bearer`; any 401 clears it and returns to `/login`. No shared dashboard secret exists in the bundle (ADR-018).

Structure: `src/api` (contract types + fetch client), `src/lib/time.ts` (store-timezone helpers, heartbeat stale threshold), `src/lib/session.ts`, `src/hooks` (polling, `useAuth`), `src/components/dashboard`, `src/pages/{Dashboard,Login}.tsx`. Shadcn primitives in `src/components/ui/*.jsx` are available via `allowJs`.

Rules: never render placeholder numbers; every value comes from `docs/CONTRACTS.md` endpoints. Times are shown in the store's IANA timezone.
