# Architecture

## System (target MVP)
```
[Camera (LAN, RTSP)] --> [Edge Agent (Python)] --HTTPS POST /api/v1/events/batch--> [Backend FastAPI + PostgreSQL] <-- [Dashboard React/TS]
       recorded file ----^         |
                                   +-- SQLite write-ahead buffer (durable before send)
```
- Edge dials out only. Camera is never exposed to the internet. Backend never connects to the edge.
- Multi-tenant from day one: every server row is scoped `tenant → store → (cameras, devices)`; the edge knows only `camera_id` / `line_id` strings and an API key.

## Edge agent modules (`edge_agent/edge_agent/`)
| Module | Role | Swappable via |
|---|---|---|
| `video/` | `VideoSource` protocol: `FileVideoSource`, `RtspVideoSource` (reconnect+backoff), `SyntheticSource` | `Frame` dataclass |
| `detection/` | `Detector` protocol → normalized `Detection` bboxes. `YoloxOnnxDetector`, `ScriptedDetector` (tests) | `detection/base.py` |
| `tracking/` | `Tracker` protocol → `Track(track_id, bbox)`. `IouTracker` baseline | `tracking/base.py` |
| `counting/` | `DirectedLine` (normalized) + `CrossingCounter` (per-track state, hysteresis) | — |
| `storage/` | `EventStore` SQLite WAL, `event_id` PK, capacity → `BufferFullError` | — |
| `transport/` | `EventSender`: batch POST, Bearer key, backoff+jitter, mark sent only on ack | `httpx.Client` injectable |
| `health.py` | Explicit status, JSON health file | — |
| `pipeline.py` | Frame loop, persists events before any network | — |
| `contracts.py` | **SSOT** event payload/ack models | — |
| `config.py` | YAML (non-secret) + env (`EDGE_API_KEY`, `EDGE_RTSP_URL`) | — |
| `cli.py` | `run / status / schema` | — |

Threading: pipeline runs on the main thread; `EventSender.run_forever` on a daemon thread; both share `EventStore` (internal lock, single SQLite connection).

## Counting semantics (authoritative)
- Anchor point per track: `bottom_center` of bbox by default (feet), configurable to `center`.
- `signed_distance(point)` to the directed line `a→b`, in normalized units. `>0` → RIGHT of travel direction on screen (y-down), `<0` → LEFT.
- `|distance| < hysteresis` → DEADBAND: never changes state.
- Per-track state: `confirmed_side` starts `UNKNOWN`. A side is confirmed after `min_confirm_frames` consecutive non-deadband observations on that side.
- Crossing emitted **only** when `confirmed_side` was known and a different side gets confirmed. New side == `enter_side` → `enter`, else `exit`.
- Consequences (by design):
  - Standing near the line / jitter → 0 events (deadband + confirm frames).
  - Real exit then re-enter with the same track id → both counted.
  - Track lost and re-identified with a new id → no phantom event (may undercount; documented limitation).
  - Track state expires after `track_ttl_frames` unseen frames.
- Counting is never derived from the number of boxes in a frame.

## Time model
- `Frame.ts` is the event time base: file → `start_ts_utc + index/fps`; RTSP → wall clock at capture (UTC).
- `event_ts` travels with the event; the server adds `received_at`. Aggregations for display convert `event_ts` to the store's IANA timezone.

## Reliability model
1. Crossing detected → `CountEventV1` built with fresh `uuid4` → `EventStore.append` (fsync'd) → only then eligible for send.
2. Sender picks oldest pending batch, POSTs; on `accepted`/`duplicates` ack → `mark_sent`; on `rejected` → `mark_rejected` (kept for inspection); anything else → `record_attempt` + backoff (1s·2ⁿ, cap 60s, ±50% jitter).
3. `event_id` never changes across retries → backend dedups → at-least-once delivery becomes effectively-once storage.
4. Buffer capacity reached → `append` raises → pipeline logs `EVENT LOST` at ERROR, increments `events_lost_buffer_full`, health = `buffer_full`. Data loss is explicit, never silent.
5. 401/403 → `auth_failed` health; events stay pending.

## Later stages (interfaces only, not built)
- Stage 2 backend: device API-key auth → resolves `device → store → tenant`; validates `camera_id` belongs to that device's store; idempotent insert on `event_id`; aggregation endpoints. See `docs/CONTRACTS.md`, `docs/DATA_MODEL.md`.
- Stage 3 dashboard: React + TypeScript, reads aggregates, no login for pilot.
