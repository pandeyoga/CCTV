# PRD — AI CCTV People Counter (subscription SaaS), MVP

## Original problem statement (verbatim intent)
Build an MVP people counter: count people entering/exiting through one door with one camera, process video on an edge device, show results on a dashboard. Scope: one store, one camera (pilot); recorded video first, then RTSP; pretrained person detector + tracker; no face recognition, no training, no heatmap/queue/POS/payments. Prepare `tenant_id, store_id, camera_id, device_id` for SaaS growth. Edge agent in Python (video input, detector, tracker, crossing counter, SQLite, HTTPS sender). Backend FastAPI + PostgreSQL (Docker Compose). Dashboard React + TypeScript. Swappable detector/tracker interfaces. Verify licenses before choosing dependencies. Directed-line crossing with normalized coords, per-track state + hysteresis, no box-count counting, same track may count again on real re-cross, track id ≠ identity, track loss must not create phantom crossings, event ts ≠ server receive ts, UTC storage / store tz display. Reliability: persist to SQLite before send, stable event_id across retries, idempotent backend, mark sent only after ack, backoff + bounded buffer, loud failure when buffer full, no secrets in repo/logs, identity from server auth, edge dials out.

## User choices (2026-06)
- Start with Stage 1 (edge agent core + tests). Backend: SQLAlchemy 2 async + PostgreSQL via Compose; SQLite in preview. Detector: agent decides after license verification (→ YOLOX/ONNX Runtime, ADR-003). Device auth: per-device API key (hashed, Bearer). Dashboard: no login for pilot → superseded 2026-06 by local email+password/JWT login with tenant scoping (Finding 3, ADR-018); `tracking_session_id` added to event contract (optional); PostgreSQL test skipped (no Docker) and recorded as not run. Strong emphasis on: foundations first, scalable design, no duplication/hallucination, clear DB relations, SSOT, context continuity for AI sessions.
- 2026-06 roadmap session: "everything that most impacts usability first; subscription packages later"; plan + implement priority #1 immediately; email notifications not yet (no provider chosen); billing manual first (no gateway); roles = platform admin + tenant owner + staff (view-only).

## Personas
- Store owner / manager: sees daily enter/exit and hourly pattern for their store.
- Operator (us): installs edge device, configures camera + line, monitors device health.
- Future: multi-store tenant admin.

## Architecture (see docs/ARCHITECTURE.md)
Edge (Python) → HTTPS `/api/v1/events/batch` → Backend (FastAPI + PostgreSQL) ← Dashboard (React/TS). Contract SSOT: `edge_agent/edge_agent/contracts.py` → `contracts/event_v1.schema.json`.

## Implemented
- 2026-06 — Stage 1 edge agent core + 51 passing tests (synthetic fixtures only) + project memory docs (`AGENTS.md`, `docs/*`). Details: `docs/STATUS.md`.
- 2026-06 — Stage 2 backend: FastAPI + SQLAlchemy 2 async (PostgreSQL via Compose / SQLite preview), Alembic, device API-key auth, idempotent ingest, tenant-scoped camera validation, summary/hourly/devices endpoints in store timezone, seed CLI, 19 backend tests + edge↔backend integration test.
- 2026-06 — Stage 3 dashboard: React 19 + TypeScript, store selector, date navigation in store timezone, KPI cards, 24-hour chart, device health with stale badge, honest empty/error states, 30 s polling. 5 helper tests.
- 2026-06 — Stage 4 tooling: headless `calibrate` (snapshot/preview), `annotate` (review video + events JSONL), `evaluate` (vs manual truth CSV), `frame_stride`, systemd unit, `docs/PILOT_RUNBOOK.md`. First real YOLOX-S ONNX run on OpenCV `vtest.avi`: 398 frames processed at 1.58 fps (CPU), 12 enter / 14 exit — agent output only, **no accuracy measured** (no ground truth). Edge 58 + 21 QA tests, backend 19 tests green.
- 2026-06 — Dashboard visual redesign: light theme tokens (CSS variables → Tailwind), 72 px charcoal nav rail + mobile top bar, glass toolbar, KPI "Selisih masuk–keluar" (not occupancy), event-based device status wording, skeleton / refreshing / stale-banner / error / empty states. Verified by tsc, 5 unit tests, screenshots at 1440/768/390, testing agent (iteration_5) — no fictional data written.

- 2026-06 — Code-review remediation (6 findings, commit 980a9c4): finite-segment crossing (ADR-023), tracker/counter reset on stream reconnect + optional `tracking_session_id` (ADR-019), dashboard login (bcrypt + JWT) with tenant-membership scoping, operator CLI `app.users`, login page, shared key removed (ADR-018), device heartbeat endpoint + `HeartbeatSender` + heartbeat-based device states (ADR-020), overflow-safe shared `Backoff` (ADR-021), exact Hungarian evaluator (ADR-022). Edge 142 tests, backend 41 tests, tsc/build green, migration `3b9c2d1e5a70` verified on SQLite (PostgreSQL not run — no Docker). Details + limitations: `docs/STATUS.md`.
- 2026-06 — **Roadmap written** (`docs/ROADMAP.md`, 5 phases; user choice: usability first, subscription last) and **Phase 1 done (ADR-024)**: roles platform admin / owner / staff, env-seeded admin, management API (tenants, stores, devices with one-time API key + rotation, cameras, members, users, change-password), `/pengaturan` UI with tabs. Backend 51 tests, live QA iteration_7 all green.

- 2026-06 — **Phase 2 done (ADR-025)**: `/laporan` — multi-store overview table, date-range report (7/30/custom ≤ 92 days) with previous-period %, daily chart, busiest day/hours, CSV export. Backend 54 tests, 4 frontend unit tests, live QA iteration_8 all green; synthetic verification events removed afterwards.
- 2026-06 — **Phase 3a (ADR-026/027)**: store opening hours (reports/overview ignore closed hours, device problems = 0 while closed) + 24 h heartbeat history timeline per device. Backend live QA iteration_9 6/6; frontend live QA iteration_10 15/15.
- 2026-06 — **Phase 3b (ADR-028)**: per-store alert rules (heartbeat lost, camera down, buffer full, no events during opening hours) evaluated server-side (on read + 60 s loop), incidents with open/resolve/acknowledge, `/notifikasi` notification centre + bell badge, "Aturan alert" dialog in Pengaturan. Backend 66 tests green, tsc clean. Workspace restored from GitHub (SQLite, seeded users in `memory/test_credentials.md`).

## Backlog (prioritized) — see docs/ROADMAP.md
- P0 Field measurement: real door RTSP camera, observer tally per `docs/PILOT_RUNBOOK.md` §7.
- P1 Alert channels: email (provider undecided) / WhatsApp / Telegram; per-user mute.
- P1 Edge: controlled agent update rollout; server-side count-line config (`count_lines` exists).
- P1 Scheduled daily/weekly report email (blocked on email provider choice).
- P1 Run `docker compose up` + `alembic upgrade head` on PostgreSQL (migrations `3b9c2d1e5a70`…`e6f7a8b9c0d1` untested on PG).
- P1 ByteTrack adapter (MIT) behind `Tracker` protocol; legal confirmation of YOLOX weights license.
- P2 Phase 4: zone occupancy / dwell / queue analytics (new edge contract). Phase 5: subscription packages + billing (manual first, gateway later).
- P2 Audit log of management actions; styled confirm dialogs; store archive.

## Not in scope (current stage)
Face recognition, model training, POS, payments (deferred to Phase 5).
