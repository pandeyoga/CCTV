"""ADR-025: range report (daily buckets in store tz, previous period, hour profile) and multi-store overview."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from test_aggregates import post
from test_ingest import event


def test_range_report_buckets_previous_period_and_hour_profile(client, fx, auth_a):
    post(client, fx.keys["a"], [
        event(ts="2026-06-01T02:15:00+00:00", event_type="enter"),   # Jun 1 09 WIB  (previous period)
        event(ts="2026-06-02T02:15:00+00:00", event_type="enter"),   # Jun 2 09 WIB  (previous period)
        event(ts="2026-06-03T02:15:00+00:00", event_type="enter"),   # Jun 3 09 WIB  (current)
        event(ts="2026-06-03T02:45:00+00:00", event_type="enter"),   # Jun 3 09 WIB
        event(ts="2026-06-03T10:05:00+00:00", event_type="exit"),    # Jun 3 17 WIB
        event(ts="2026-06-03T17:30:00+00:00", event_type="enter"),   # Jun 4 00:30 WIB -> local day Jun 4
        event(ts="2026-06-05T02:00:00+00:00", event_type="exit"),    # Jun 5 (outside range)
    ])
    r = client.get(f"/api/v1/stores/{fx.ids['store_a']}/report?from=2026-06-03&to=2026-06-04", headers=auth_a)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["timezone"] == "Asia/Jakarta"
    assert b["current"] == {"from_date": "2026-06-03", "to_date": "2026-06-04", "days": 2, "enter": 3, "exit": 1}
    assert b["previous"] == {"from_date": "2026-06-01", "to_date": "2026-06-02", "days": 2, "enter": 2, "exit": 0}
    assert b["daily"] == [{"date": "2026-06-03", "enter": 2, "exit": 1}, {"date": "2026-06-04", "enter": 1, "exit": 0}]
    prof = {h["hour"]: (h["enter"], h["exit"]) for h in b["hourly_profile"]}
    assert len(prof) == 24 and prof[9] == (2, 0) and prof[17] == (0, 1) and prof[0] == (1, 0)


def test_range_report_validation_and_scoping(client, fx, auth_a):
    sid = fx.ids["store_a"]
    assert client.get(f"/api/v1/stores/{sid}/report?from=2026-06-05&to=2026-06-04", headers=auth_a).status_code == 422
    assert client.get(f"/api/v1/stores/{sid}/report?from=2026-01-01&to=2026-06-04", headers=auth_a).status_code == 422
    assert client.get(f"/api/v1/stores/{sid}/report?from=2026-06-01", headers=auth_a).status_code == 422
    assert client.get(f"/api/v1/stores/{sid}/report?from=2026-06-01&to=2026-06-01", headers=auth_a).status_code == 200
    assert client.get(f"/api/v1/stores/{fx.ids['store_b']}/report?from=2026-06-01&to=2026-06-01", headers=auth_a).status_code == 404
    assert client.get(f"/api/v1/stores/{sid}/report?from=2026-06-01&to=2026-06-01").status_code == 401


def test_overview_today_yesterday_avg_and_device_problems(client, fx, auth_a, auth_b):
    now = datetime.now(timezone.utc)
    # Store A is Asia/Jakarta; use noon UTC today/yesterday which stays on the same local day (UTC+7 -> 19:00).
    today_noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
    if today_noon.astimezone(timezone(timedelta(hours=7))).date() != now.astimezone(timezone(timedelta(hours=7))).date():
        today_noon -= timedelta(days=1)
    iso = lambda dt: dt.isoformat().replace("+00:00", "+00:00")  # noqa: E731
    post(client, fx.keys["a"], [
        event(ts=iso(today_noon), event_type="enter"), event(ts=iso(today_noon), event_type="enter"), event(ts=iso(today_noon), event_type="exit"),
        event(ts=iso(today_noon - timedelta(days=1)), event_type="enter"),
        event(ts=iso(today_noon - timedelta(days=3)), event_type="enter"), event(ts=iso(today_noon - timedelta(days=3)), event_type="enter"),
        event(ts=iso(today_noon - timedelta(days=8)), event_type="enter"),  # outside the 7-day window
    ])
    rows = client.get("/api/v1/overview", headers=auth_a).json()
    assert [r["name"] for r in rows] == ["Toko A"]  # tenant-scoped
    a = rows[0]
    assert (a["enter"], a["exit"], a["yesterday_enter"]) == (2, 1, 1)
    assert a["avg_enter_7d"] == round(3 / 7, 1)
    assert a["devices_total"] == 1 and a["devices_problem"] == 1  # dev-a never sent a heartbeat; dev-off is inactive -> excluded
    assert a["last_event_at"] is not None
    hb = {"schema_version": 1, "sent_at": "2026-06-01T00:00:00Z", "source_status": "ok", "last_frame_age_s": 0.5,
          "pending_events": 0, "frames_processed": 1, "tracking_session_id": 0, "agent_version": "t"}
    assert client.post("/api/v1/devices/heartbeat", json=hb, headers={"Authorization": f"Bearer {fx.keys['a']}"}).status_code == 200
    assert client.get("/api/v1/overview", headers=auth_a).json()[0]["devices_problem"] == 0
    b = client.get("/api/v1/overview", headers=auth_b).json()
    assert [r["name"] for r in b] == ["Toko B"] and b[0]["enter"] == 0
