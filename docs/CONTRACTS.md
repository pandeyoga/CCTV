# Contracts (HTTP API) — SSOT for the API surface

Payload shapes: `contracts/event_v1.schema.json` and `contracts/heartbeat_v1.schema.json` (generated; see ADR-002). All endpoints are under `/api`.

Two independent authentication mechanisms (ADR-018):
- **Device key** `Authorization: Bearer dk_<key_id>.<secret>` — edge ingest + heartbeat only. Never accepted on dashboard endpoints.
- **Dashboard user JWT** `Authorization: Bearer <access_token>` from `POST /api/auth/login` — dashboard read endpoints only. Never accepted on edge endpoints.

## Edge → Backend
### `POST /api/v1/events/batch`
- Auth: device key (ADR-012). Server resolves `device → store → tenant`. 401 unknown/invalid key, 403 inactive device.
- Body: `EventBatchRequestV1` — `{ "events": [CountEventV1, ...] }`, 1..500 items.
- Response 200: `EventBatchResponseV1`
  ```json
  { "accepted": ["<event_id>"], "duplicates": ["<event_id>"], "rejected": [{"event_id": "...", "reason": "unknown camera"}] }
  ```
  - `accepted`: newly stored. `duplicates`: `event_id` already existed (idempotent; nothing changed). Both mean "edge may mark sent".
  - `rejected`: per-event validation failure the edge cannot fix by retrying (unknown camera, camera not in device's store). Edge keeps them as `rejected` locally.
- 400/422: whole body malformed (edge keeps batch pending, backs off, logs). 429/5xx: retry with backoff.
- Server sets `received_at = now()`; never trusts identity fields from the body (they are not in the schema; unknown fields → 422).
- Side effect: `devices.last_seen_at` (exposed as `last_event_at`) = server time of the last batch. This is **visitor activity, not liveness** (see heartbeat).

### `CountEventV1` fields
`schema_version=1, event_id (uuid4), event_type ("enter"|"exit"), event_ts (UTC ISO-8601, tz-aware), camera_id (external string), line_id (external string), track_id (int ≥0), frame_index (int ≥0), source_kind ("file"|"rtsp"|"synthetic"), tracking_session_id (int ≥0, optional/null)`.
- `tracking_session_id` (added 2026-06, ADR-019): increments on every stream reconnect; `track_id` is unique only within a session. Optional for backward compatibility — agents that omit it are still accepted and the column stays `NULL`.

### `POST /api/v1/devices/heartbeat` (ADR-020)
- Auth: device key. Updates **only** the authenticated device row; nothing in the body identifies a device/tenant.
- Body: `HeartbeatV1` — `{ schema_version: 1, sent_at (UTC ISO, informational), source_status ("ok"|"source_down"), last_frame_age_s (float ≥0 | null), pending_events (int ≥0), frames_processed (int ≥0), tracking_session_id (int ≥0), agent_version (str) }`. Unknown fields → 422.
- Response 200: `HeartbeatAckV1` — `{ received_at }` (server clock). 401/403 as for ingest.
- Server stores `last_heartbeat_at = received_at` (never `sent_at`) plus the health fields.
- **Interval / staleness (single definition):** edge sends every `backend.heartbeat_interval_s` (default **60 s**); a failed heartbeat is not queued — the next one supersedes it (bounded backoff up to 300 s). Dashboard marks a device **stale after 3 × interval = 180 s** without a heartbeat (`frontend/src/lib/time.ts::HEARTBEAT_STALE_SECONDS`). A device that never sent a heartbeat is **"Belum diketahui"** (unknown), not healthy. Heartbeats never create count events.

## Dashboard → Backend
### `POST /api/auth/login`
- Body `{ email, password }` (extra fields → 422). 200 → `{ access_token, token_type: "bearer", expires_in (s), user: { user_id, email, tenant_ids[] } }`.
- 401 for unknown email / wrong password / inactive user (uniform). 429 after 5 failures per (client IP, email) within 15 min. 404 when `DASHBOARD_AUTH=disabled`.
- Token: HS256 JWT, `typ: "dashboard"`, TTL `JWT_TTL_MINUTES` (default 720). Authorization (tenant memberships) is re-read from the DB on every request, so deactivating a user takes effect immediately.
### `GET /api/auth/me` → `{ user_id, email, tenant_ids[], is_platform_admin, memberships: [{ tenant_id, tenant_name, role }] }`
- `role ∈ owner | staff | platform_admin` (ADR-024). The same `user` object is returned by login.
### `POST /api/auth/change-password` — `{ current_password, new_password (≥10) }` → 204; 403 when the current password is wrong.

## Management (ADR-024) — dashboard JWT; role-scoped writes
Roles: **platform admin** (`dashboard_users.is_platform_admin`, every tenant), tenant **owner** (manages that tenant), **staff** (read-only). Every write resolves the tenant from the DB row and checks the caller: outside the caller's tenants → 404; inside but staff → 403. Bodies use `extra="forbid"`. Name collisions → 409.
- `GET /api/v1/tenants` → `[{ tenant_id, name, contact_email, role, store_count, created_at }]` (`role` = caller's role for that tenant). `POST /api/v1/tenants` `{ name, contact_email? }` → 201 and `PATCH /api/v1/tenants/{id}` — platform admin only (403 otherwise).
- `POST /api/v1/stores` `{ tenant_id, name, timezone (IANA, validated) }` → 201 `StoreOut`. `PATCH /api/v1/stores/{id}` `{ name?, timezone? }`.
- `POST /api/v1/stores/{store_id}/devices` `{ name }` → 201 `{ device: DeviceOut, api_key_show_once }`. **The key is returned exactly once** and never again by any endpoint. `PATCH /api/v1/devices/{id}` `{ name?, is_active? }` → `DeviceOut`. `POST /api/v1/devices/{id}/rotate-key` → same shape as create; the previous key is invalid immediately.
- `GET /api/v1/stores/{store_id}/cameras` (staff may read) → `[{ camera_id, store_id, device_id, external_id, name, created_at }]`. `POST` `{ external_id (^[A-Za-z0-9_.-]+$, == payload camera_id), name, device_id? }` → 201; `device_id` must belong to the same store (422). `PATCH /api/v1/cameras/{id}` `{ name?, device_id? | clear_device: true }`. `DELETE /api/v1/cameras/{id}` → 204, or 409 when count events reference it.
- `GET /api/v1/tenants/{id}/members` (owner/admin) → `[{ user_id, email, role, is_active, is_platform_admin, created_at }]`. `POST` `{ email, role, password? }` → 201: unknown email creates the user (password ≥10 required, 422 otherwise); existing user gets a membership; platform admin or existing member → 409. `PATCH …/members/{user_id}` `{ role }`; `DELETE …/members/{user_id}` → 204. Changing/removing yourself → 409.
- `POST /api/v1/users/{user_id}/reset-password` `{ password }` → 204. Owner: only users who are members of a tenant the owner manages and are not platform admins (else 404). Admin: anyone.
- `GET /api/v1/users` and `PATCH /api/v1/users/{id}` `{ is_active }` — platform admin only; self-deactivation → 409. Deactivation takes effect on the next request (memberships/user re-read per request).
- Platform admin seeding: `ADMIN_EMAIL` + `ADMIN_PASSWORD` (≥10) env → created or re-synced at startup (idempotent).

### Read endpoints (all require a dashboard JWT; 401 otherwise)
- `GET /api/v1/stores` → `[{ store_id, tenant_id, name, timezone }]` — **only stores of tenants the user is a member of**; `[]` if none.
- `GET /api/v1/stores/{store_id}/summary?date=YYYY-MM-DD` → `{ store_id, date, timezone, enter, exit, occupancy_estimate, last_event_at }`
  - `date` interpreted in the store timezone; defaults to today in that timezone. `occupancy_estimate = enter - exit` for that day (may be negative; label as estimate). `last_event_at` is the latest `event_ts` for the store overall (UTC ISO) or null.
- `GET /api/v1/stores/{store_id}/hourly?date=YYYY-MM-DD` → `{ store_id, date, timezone, buckets: [{ hour_start (store-local ISO with offset), enter, exit }] }` — 24 buckets, zero-filled.
- `GET /api/v1/stores/{store_id}/devices` → `[{ device_id, name, is_active, last_event_at, last_heartbeat_at, source_status, last_frame_age_s, pending_events, agent_version }]`
  - `last_event_at` = server time of the last accepted event batch (visitor activity). `last_heartbeat_at` = server time of the last heartbeat (liveness). `source_status` = camera state from the last heartbeat. `api_key_prefix` was removed from the API (2026-06).
- `GET /api/v1/devices` → `[{ ...DeviceOut fields, store_id, store_name, store_timezone }]` — every device across the user's permitted tenants (operator "Perangkat" page); `[]` if none. Same field semantics as the per-store list.
- Unknown **or not-permitted** `store_id` → 404 (a known UUID is not a permission; the two cases are indistinguishable).

### Reports (ADR-025)
- `GET /api/v1/stores/{store_id}/report?from=YYYY-MM-DD&to=YYYY-MM-DD` → `{ store_id, timezone, current: RangeTotals, previous: RangeTotals, daily: [{ date, enter, exit }], hourly_profile: [{ hour 0..23, enter, exit }] }`. Both bounds inclusive, interpreted in the store timezone; `to < from` or more than **92 days** → 422. `previous` = the immediately preceding period of the same length (`RangeTotals = { from_date, to_date, days, enter, exit }`). `daily` is zero-filled for every day; `hourly_profile` sums the range per store-local hour (for "busiest hours"). CSV export is done client-side from `daily`.
- `GET /api/v1/overview` → `[{ store_id, tenant_id, name, timezone, date, enter, exit, yesterday_enter, avg_enter_7d, last_event_at, devices_total, devices_problem, is_open_now, open_time, close_time }]` for every permitted store. `date` = today in that store's timezone; `avg_enter_7d` = mean daily `enter` over the 7 days before today (1 decimal); `devices_total` counts active devices only; `devices_problem` = active devices with no heartbeat, heartbeat older than 180 s, or `source_status = source_down` — **always 0 while the store is closed** (ADR-026). Counts only include events inside opening hours.

### Opening hours (ADR-026)
- `StoreOut` carries `open_time` / `close_time` (`"HH:MM"` store-local, both `null` = open 24 h). `POST /api/v1/stores` and `PATCH /api/v1/stores/{id}` accept them: both or neither (422 otherwise), `HH:MM` 00:00–23:59, must differ; `close <= open` means an overnight window (e.g. 18:00–02:00). In `PATCH`, omitting both leaves hours unchanged; sending both as `null` resets to 24 h.
- Open at `open_time` inclusive, closed at `close_time` exclusive. `/report` and `/overview` ignore events outside the window; `/report` reports how many were ignored in `outside_hours_excluded` and echoes `open_time`/`close_time`. `/summary` and `/hourly` (single-day dashboard) are **not** filtered — they show the raw day.

### Heartbeat history (ADR-027)
- Every accepted heartbeat is appended to `device_heartbeats` (server `received_at`, `source_status`, agent fields); rows older than **7 days** are pruned per device on insert.
- `GET /api/v1/devices/{device_id}/heartbeats?hours=24` (dashboard JWT; device outside the user's tenants → 404; `hours` 1..168) → `{ device_id, from_ts, to_ts, stale_after_s: 180, samples, uptime_pct, segments: [{ start, end, status }] }` with `status ∈ connected | camera_down | stale | unknown`. Consecutive heartbeats ≤ 180 s apart extend a `connected`/`camera_down` segment; a larger gap is `connected` for 180 s then `stale` until the next heartbeat (or `to_ts`); time before the first sample in the window is `unknown`. `uptime_pct` = share of the window in `connected`.
### Alerts / notification centre (ADR-028)
- Rules per store (`alert_rules`, defaults when no row): `heartbeat_lost_min` 3, `camera_down_min` 2, `buffer_pending_threshold` 1000, `no_events_min` 60 (`null` = off). `GET /api/v1/stores/{id}/alert-rules` (any member) → `{ store_id, heartbeat_lost_min, camera_down_min, buffer_pending_threshold, no_events_min, is_default }`. `PUT` (owner/admin; body has all four fields — `no_events_min` must be present, `null` turns the rule off — `extra="forbid"`, ranges 1..1440 min / 1..10⁶ events / `no_events_min` 5..1440 or null) upserts; `DELETE` removes the row → defaults again. Staff → 403, foreign store → 404.
- Evaluation: on every `GET /api/v1/alerts` for the caller's tenants **and** every `ALERT_EVAL_INTERVAL_S` (env, default 60; 0 disables the loop) for all tenants in-process. New incidents are created **only while the store is open** (`app/hours.py::is_open_at`, ADR-026); an open incident is resolved as soon as its condition clears (open or closed). Rules: `heartbeat_lost` (critical; last heartbeat older than N min — devices that never sent one stay `unknown`, no alert), `camera_down` (critical; fresh heartbeat with `source_down` for longer than N min, measured from `device_heartbeats`), `buffer_full` (warning; `pending_events ≥ threshold`), `no_events_open_hours` (warning, store-level, `device_id = null`; requires a connected device, a registered camera and the store open for the whole window). A dead agent suppresses camera/buffer rules for that device. At most one open row per `(store, device, rule)`.
- `GET /api/v1/alerts?status=open|resolved|all&store_id=&limit=100` → `{ evaluated_at, open_count, unacknowledged_count, alerts: [{ alert_id, tenant_id, store_id, store_name, store_timezone, device_id, device_name, rule, severity ("warning"|"critical"), message (id-ID), opened_at (threshold crossed), last_seen_at, resolved_at, acknowledged_at, acknowledged_by_email }] }` — open first, newest first. `open_count`/`unacknowledged_count` always describe the open set (bell badge). `POST /api/v1/alerts/{id}/ack` → `AlertOut` (owner/admin; staff 403; foreign 404; idempotent).
- `GET /api/health` → `{ status: "ok" }` (always public).

### Telegram channel (ADR-029)
- `GET /api/v1/notifications/channels` → `{ telegram_configured }` (server has `TELEGRAM_BOT_TOKEN`). `StoreOut` now carries `telegram_chat_id` (`null` = off).
- `PUT /api/v1/stores/{id}/telegram` `{ chat_id: "-100…" | "@channel" | null }` (owner/admin; staff 403; foreign 404; pattern `^-?\d+$|^@[A-Za-z0-9_]{5,}$` else 422) → `StoreOut`. `POST /api/v1/stores/{id}/telegram/test` → `{ ok, error }` (503 without token, 422 without chat_id; `error` never contains the token).
- Delivery: after every alert evaluation (read + loop) each store with a `chat_id` gets one HTML message per opened incident and one per resolution ("pulih"); marks in `alerts.notified_at` / `resolved_notified_at`; failures retried next tick.

### Camera geometry + snapshots (ADR-030)
- **Edge (device key):** `GET /api/v1/devices/me/config` → `DeviceConfigV1` `{ schema_version: 1, config_version (sha256[:16] of content), generated_at, cameras: [{ camera_id (external), lines: [{ line_id, ax, ay, bx, by, enter_side }], zones: [{ zone_id, name, polygon: [[x,y],…] }] }] }` — every camera of the device's store whose `device_id` is this device or `null`. Schema: `contracts/device_config_v1.schema.json`. `POST /api/v1/devices/snapshot?camera_id=<external>` with a raw `image/jpeg` body (≤ 2 MB, JPEG magic checked → 415/413; unknown/foreign camera 404) → `{ camera_id, snapshot_at, bytes }`; the previous file is overwritten.
- **Dashboard (JWT):** `GET /api/v1/cameras/{id}/lines` → `[{ camera_id, line_id, ax, ay, bx, by, enter_side }]`; `PUT /api/v1/cameras/{id}/lines/{line_id}` `{ ax, ay, bx, by, enter_side }` (owner; coords 0..1, endpoints must differ, `line_id` `^[A-Za-z0-9_.-]+$`) upserts; `DELETE` → 204 / 404. `GET /api/v1/cameras/{id}/snapshot` → `image/jpeg` (`Cache-Control: no-store`) or 404 when none uploaded; `CameraOut.snapshot_at` tells the UI whether to fetch.

### Zones + occupancy (ADR-031)
- **Edge:** `POST /api/v1/zones/samples` `{ samples: [ZoneSampleV1 ×1..500] }`, `ZoneSampleV1 = { schema_version: 1, sample_id (uuid4), camera_id, zone_id, sample_ts (UTC), interval_s (0<x≤3600), count ≥ 0, count_max ≥ count }` → `{ accepted[], duplicates[], rejected: [{ sample_id, reason: "unknown camera" | "unknown zone" }] }`, idempotent by `sample_id`. Schema: `contracts/zone_sample_v1.schema.json`.
- **Dashboard:** `GET /api/v1/stores/{id}/zones` and `GET /api/v1/cameras/{id}/zones` → `[{ zone_id, store_id, camera_id, camera_external_id, external_id, name, polygon, created_at, last_sample_ts, last_count, last_count_max }]`. `POST /api/v1/cameras/{id}/zones` `{ external_id, name, polygon (3..64 points in 0..1) }` → 201 (409 duplicate `external_id` per camera); `PATCH /api/v1/zones/{id}` `{ name?, polygon? }`; `DELETE /api/v1/zones/{id}` → 204 (samples deleted too). `GET /api/v1/stores/{id}/zones/occupancy?date=YYYY-MM-DD` → `{ store_id, date, timezone, zones: [{ zone_id, external_id, name, samples, peak, buckets: [{ hour_start (store-local), avg_count, max_count, samples }] ×24 }] }`.

`DASHBOARD_AUTH=disabled` (explicit env, local development only): read endpoints return every tenant's data and `/api/auth/login` is 404. It is never a fallback — a missing/short `JWT_SECRET` with `DASHBOARD_AUTH=required` makes the server refuse to start. The frontend mirrors this with `REACT_APP_DASHBOARD_AUTH=disabled`; otherwise it always requires login. No shared dashboard secret exists in the frontend bundle (`REACT_APP_DASHBOARD_KEY` removed).

## Edge local health file (`health_file`)
```json
{ "status": "ok|degraded|source_down|auth_failed|buffer_full", "transport_status": "...", "transport_error": null,
  "source_status": "ok|source_down", "buffer_pending": 0, "buffer_capacity": 50000, "buffer_rejected": 0,
  "events_lost_buffer_full": 0, "frames_processed": 0, "enter_count": 0, "exit_count": 0, "tracking_session_id": 0, "updated_at": "UTC ISO" }
```
