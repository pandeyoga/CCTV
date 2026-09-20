# Data model (server side, PostgreSQL) — SSOT for Stage 2 models

All ids are UUIDv4. All timestamps `timestamptz` stored in UTC. Every table except `tenants` carries `tenant_id` for tenant isolation and cheap row-level filtering.

```
tenants 1──* stores 1──* cameras 1──* count_lines
                  │           ▲
                  └──* devices ┘ (camera.device_id → devices.id; a camera is processed by exactly one device)
count_events *──1 cameras, *──1 devices, *──1 stores, *──1 tenants
```

## Tables
### tenants
| col | type | notes |
|---|---|---|
| id | uuid pk | |
| name | text | unique |
| contact_email | text nullable | owner/operator contact |
| created_at | timestamptz | |

### stores
| id | uuid pk |
| tenant_id | uuid fk tenants |
| name | text | unique per tenant |
| timezone | text | IANA, e.g. `Asia/Jakarta`; used for display/aggregation buckets |
| open_time, close_time | text nullable | `HH:MM` store-local opening window (ADR-026); both NULL = 24 h; `close <= open` wraps past midnight |
| created_at | timestamptz |

### devices  (edge agents)
| id | uuid pk |
| tenant_id | uuid fk tenants |
| store_id | uuid fk stores | must belong to `tenant_id` |
| name | text |
| key_id | text unique | public part of `dk_<key_id>.<secret>`; indexed lookup (ADR-012) |
| secret_hash | text | sha256 hex of the secret only (never the token) |
| api_key_prefix | text | first 12 chars of the token, for support lookup only |
| is_active | bool |
| last_seen_at | timestamptz nullable | server time of the last accepted **event** batch (API name `last_event_at`); visitor activity, not liveness |
| last_heartbeat_at | timestamptz nullable | server receive time of the last heartbeat (ADR-020); NULL → status unknown |
| hb_source_status | text nullable | `ok` / `source_down` from the last heartbeat |
| hb_last_frame_age_s | double nullable | |
| hb_pending_events | int nullable | |
| hb_tracking_session_id | int nullable | |
| hb_agent_version | text nullable | |
| created_at | timestamptz |

### device_heartbeats  (liveness history, ADR-027)
| id | uuid pk |
| tenant_id, device_id | fks |
| received_at | timestamptz | server clock |
| source_status | text | `ok` / `source_down` |
| last_frame_age_s | double nullable |
| pending_events, tracking_session_id | int |
| agent_version | text |
Index `(device_id, received_at)`. Rows older than 7 days are deleted per device whenever that device sends a heartbeat.

### dashboard_users  (operator-provisioned logins, ADR-018)
| id | uuid pk |
| email | text unique | stored lower-case |
| password_hash | text | bcrypt |
| is_active | bool | false → login and existing tokens rejected |
| is_platform_admin | bool | true → every tenant visible and manageable (ADR-024); seeded from `ADMIN_EMAIL`/`ADMIN_PASSWORD` |
| created_at | timestamptz |

### tenant_memberships  (authorization SSOT: which tenants a user may access, and how)
| id | uuid pk |
| user_id | uuid fk dashboard_users |
| tenant_id | uuid fk tenants |
| role | text | `owner` (manage stores/devices/cameras/members) or `staff` (read-only). Legacy `viewer` migrated to `staff` (rev `c4d5e6f7a8b9`) |
| created_at | timestamptz |
Unique `(user_id, tenant_id)`; indexed on both fks.

### cameras
| id | uuid pk |
| tenant_id | uuid fk tenants |
| store_id | uuid fk stores |
| device_id | uuid fk devices nullable | the device allowed to post events for this camera |
| external_id | text | == `camera_id` string in edge payload; **unique per store** |
| name | text |
| created_at | timestamptz |

### count_lines  (server copy of line config; optional in Stage 2, needed for dashboard overlay later)
| id | uuid pk |
| tenant_id, camera_id | fks |
| external_id | text | == `line_id` in payload; unique per camera |
| ax, ay, bx, by | double | normalized |
| enter_side | text | `left` / `right` |

### count_events
| col | type | notes |
|---|---|---|
| event_id | uuid pk | client-generated; **idempotency key** |
| tenant_id | uuid fk | from auth |
| store_id | uuid fk | from auth (device.store_id) |
| device_id | uuid fk | from auth |
| camera_id | uuid fk cameras | resolved from payload `camera_id` (external_id) within device's store |
| line_id | text | payload `line_id` (external string) |
| event_type | enum `enter`/`exit` | |
| event_ts | timestamptz | from payload (edge time) |
| received_at | timestamptz | server `now()` |
| track_id | int | local tracker id, not an identity |
| frame_index | int | |
| source_kind | text | `file`/`rtsp`/`synthetic` |
| schema_version | smallint | |
| tracking_session_id | int nullable | edge tracking session (ADR-019); `track_id` is unique only within it; NULL for agents that predate the field |

Indexes: `(store_id, event_ts)`, `(camera_id, event_ts)`, `(tenant_id, event_ts)`.

## Invariants the backend must enforce
1. Tenant/store/device on `count_events` come **only** from the authenticated device row.
2. `camera_id` in payload must resolve to a camera with `store_id == device.store_id` (and `device_id == device.id` if set), else the event is `rejected` with reason `unknown camera`.
3. Insert is idempotent on `event_id`: existing row → report in `duplicates`, do not update.
4. Aggregations bucket `event_ts AT TIME ZONE stores.timezone`.
5. No deletes of `count_events` through the API in the MVP.
6. Dashboard reads are filtered by `tenant_memberships` of the authenticated user; a store outside those tenants is 404. Heartbeats update only the authenticated device row.

### alert_rules  (per-store thresholds, ADR-028; optional row — code defaults apply when absent)
| store_id | uuid pk fk stores |
| tenant_id | uuid fk tenants |
| heartbeat_lost_min, camera_down_min | int | minutes |
| buffer_pending_threshold | int | `pending_events ≥` |
| no_events_min | int nullable | NULL = rule off (no ORM default on purpose) |
| updated_at | timestamptz |

### alerts  (incidents, ADR-028)
| id | uuid pk |
| tenant_id, store_id | fks |
| device_id | uuid fk devices nullable | NULL for store-level rules |
| rule | text | `heartbeat_lost` / `camera_down` / `buffer_full` / `no_events_open_hours` |
| severity | text | `warning` / `critical` |
| message | text | server-generated (id-ID) |
| opened_at | timestamptz | when the threshold was crossed |
| last_seen_at | timestamptz | last evaluation that still saw the condition |
| resolved_at | timestamptz nullable | NULL = open; at most one open row per `(store_id, device_id, rule)` (enforced in code) |
| acknowledged_at | timestamptz nullable |
| acknowledged_by | uuid fk dashboard_users nullable |
Indexes: `(tenant_id, opened_at)`, `(store_id, resolved_at)`.
