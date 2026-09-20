from __future__ import annotations

from test_ingest import auth, event


def post(client, key, events):
    r = client.post("/api/v1/events/batch", json={"events": events}, headers=auth(key))
    assert r.status_code == 200, r.text
    return r.json()


def test_summary_and_hourly_use_store_timezone(client, fx, auth_a):
    # Asia/Jakarta = UTC+7. 2026-06-01T17:30Z is 2026-06-02 00:30 local -> belongs to June 2 local day.
    post(client, fx.keys["a"], [
        event(ts="2026-06-01T02:15:00+00:00", event_type="enter"),   # Jun 1 09:15 WIB
        event(ts="2026-06-01T02:45:00+00:00", event_type="enter"),   # Jun 1 09:45 WIB
        event(ts="2026-06-01T10:05:00+00:00", event_type="exit"),    # Jun 1 17:05 WIB
        event(ts="2026-06-01T17:30:00+00:00", event_type="enter"),   # Jun 2 00:30 WIB
    ])
    s1 = client.get(f"/api/v1/stores/{fx.ids['store_a']}/summary?date=2026-06-01", headers=auth_a).json()
    assert (s1["enter"], s1["exit"], s1["occupancy_estimate"]) == (2, 1, 1)
    assert s1["timezone"] == "Asia/Jakarta" and s1["last_event_at"].startswith("2026-06-01T17:30:00")
    s2 = client.get(f"/api/v1/stores/{fx.ids['store_a']}/summary?date=2026-06-02", headers=auth_a).json()
    assert (s2["enter"], s2["exit"]) == (1, 0)

    h = client.get(f"/api/v1/stores/{fx.ids['store_a']}/hourly?date=2026-06-01", headers=auth_a).json()
    assert len(h["buckets"]) == 24
    by_hour = {b["hour_start"][11:13]: (b["enter"], b["exit"]) for b in h["buckets"]}
    assert by_hour["09"] == (2, 0) and by_hour["17"] == (0, 1) and by_hour["00"] == (0, 0)
    assert h["buckets"][0]["hour_start"] == "2026-06-01T00:00:00+07:00"


def test_store_list_and_404(client, fx, auth_a):
    stores = client.get("/api/v1/stores", headers=auth_a).json()
    assert {s["name"] for s in stores} == {"Toko A"}  # tenant-scoped (Finding 3)
    assert client.get("/api/v1/stores/00000000-0000-0000-0000-000000000000/summary", headers=auth_a).status_code == 404


def test_summary_defaults_to_today_in_store_tz(client, fx, auth_a):
    s = client.get(f"/api/v1/stores/{fx.ids['store_a']}/summary", headers=auth_a).json()
    assert s["enter"] == 0 and s["last_event_at"] is None
