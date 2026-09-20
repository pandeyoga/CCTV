"""Phase 4: Telegram channel (ADR-029), server-side lines/snapshots/device config (ADR-030), zones + occupancy (ADR-031)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app import telegram
from app.config import Settings
from app.main import create_app
from app.routers.zones import bucketize
from conftest import JWT_SECRET, login

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def dev(key):
    return {"Authorization": f"Bearer {key}"}


def sample(cam="cam-a", zone="kasir", ts=None, count=2, count_max=3, **kw):
    return {"schema_version": 1, "sample_id": str(uuid4()), "camera_id": cam, "zone_id": zone,
            "sample_ts": (ts or datetime.now(timezone.utc)).isoformat(), "interval_s": 10, "count": count, "count_max": count_max, **kw}


# ----------------------------------------------------------------------------- ADR-030 lines + device config
def test_line_crud_scoping_and_device_config_version(client, fx, auth_a, auth_b, auth_staff):
    cam = str(fx.ids["camera_a"])
    body = {"ax": 0.2, "ay": 0.5, "bx": 0.8, "by": 0.5, "enter_side": "left"}
    assert client.get(f"/api/v1/cameras/{cam}/lines", headers=auth_a).json() == []
    cfg0 = client.get("/api/v1/devices/me/config", headers=dev(fx.keys["a"])).json()
    assert cfg0["cameras"] == [{"camera_id": "cam-a", "lines": [], "zones": []}]
    assert client.put(f"/api/v1/cameras/{cam}/lines/door-1", json=body, headers=auth_staff).status_code == 403
    assert client.put(f"/api/v1/cameras/{cam}/lines/door-1", json=body, headers=auth_b).status_code == 404
    assert client.put(f"/api/v1/cameras/{cam}/lines/door-1", json={**body, "bx": 0.2, "by": 0.5}, headers=auth_a).status_code == 422
    assert client.put(f"/api/v1/cameras/{cam}/lines/door-1", json={**body, "ax": 1.5}, headers=auth_a).status_code == 422
    assert client.put(f"/api/v1/cameras/{cam}/lines/bad id", json=body, headers=auth_a).status_code == 422
    r = client.put(f"/api/v1/cameras/{cam}/lines/door-1", json=body, headers=auth_a)
    assert r.status_code == 200 and r.json()["line_id"] == "door-1" and r.json()["enter_side"] == "left"
    cfg1 = client.get("/api/v1/devices/me/config", headers=dev(fx.keys["a"])).json()
    assert cfg1["cameras"][0]["lines"] == [{"line_id": "door-1", **body}]
    assert cfg1["config_version"] != cfg0["config_version"]
    # upsert changes version; identical PUT keeps it
    client.put(f"/api/v1/cameras/{cam}/lines/door-1", json={**body, "enter_side": "right"}, headers=auth_a)
    cfg2 = client.get("/api/v1/devices/me/config", headers=dev(fx.keys["a"])).json()
    assert cfg2["config_version"] != cfg1["config_version"] and len(cfg2["cameras"][0]["lines"]) == 1
    assert client.get("/api/v1/devices/me/config", headers=dev(fx.keys["a"])).json()["config_version"] == cfg2["config_version"]
    # device B sees only its own store
    assert client.get("/api/v1/devices/me/config", headers=dev(fx.keys["b"])).json()["cameras"][0]["camera_id"] == "cam-b"
    assert client.get("/api/v1/devices/me/config", headers=auth_a).status_code == 401  # JWT is not a device key
    assert client.get(f"/api/v1/cameras/{cam}/lines", headers=auth_b).status_code == 404
    assert client.delete(f"/api/v1/cameras/{cam}/lines/door-1", headers=auth_a).status_code == 204
    assert client.delete(f"/api/v1/cameras/{cam}/lines/door-1", headers=auth_a).status_code == 404
    assert client.get("/api/v1/devices/me/config", headers=dev(fx.keys["a"])).json()["config_version"] == cfg0["config_version"]


def test_snapshot_upload_and_read(db_url, fx, tmp_path):
    settings = Settings(database_url=db_url, cors_origins=[], auto_create_schema=False, jwt_secret=JWT_SECRET, snapshot_dir=str(tmp_path / "snaps"))
    with TestClient(create_app(settings)) as c:

        auth_a, auth_b = login(c, "owner-a@example.com"), login(c, "owner-b@example.com")
        cam = str(fx.ids["camera_a"])
        assert c.get(f"/api/v1/cameras/{cam}/snapshot", headers=auth_a).status_code == 404
        assert c.post("/api/v1/devices/snapshot?camera_id=cam-a", content=b"not jpeg", headers=dev(fx.keys["a"])).status_code == 415
        assert c.post("/api/v1/devices/snapshot?camera_id=cam-zzz", content=JPEG, headers=dev(fx.keys["a"])).status_code == 404
        assert c.post("/api/v1/devices/snapshot?camera_id=cam-a", content=JPEG, headers=dev(fx.keys["b"])).status_code == 404  # other store
        assert c.post("/api/v1/devices/snapshot?camera_id=cam-a", content=b"\xff\xd8\xff" + b"0" * (2 * 1024 * 1024), headers=dev(fx.keys["a"])).status_code == 413
        r = c.post("/api/v1/devices/snapshot?camera_id=cam-a", content=JPEG, headers=dev(fx.keys["a"]))
        assert r.status_code == 200 and r.json()["bytes"] == len(JPEG)
        r = c.get(f"/api/v1/cameras/{cam}/snapshot", headers=auth_a)
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content == JPEG
        assert c.get(f"/api/v1/cameras/{cam}/snapshot", headers=auth_b).status_code == 404
        cams = c.get(f"/api/v1/stores/{fx.ids['store_a']}/cameras", headers=auth_a).json()
        assert cams[0]["snapshot_at"] is not None
        assert (tmp_path / "snaps" / f"{cam}.jpg").read_bytes() == JPEG


# ----------------------------------------------------------------------------- ADR-031 zones + samples + occupancy
def test_zone_crud_samples_and_occupancy(client, fx, auth_a, auth_b, auth_staff):
    cam = str(fx.ids["camera_a"])
    poly = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]
    zin = {"external_id": "kasir", "name": "Antrean kasir", "polygon": poly}
    assert client.post(f"/api/v1/cameras/{cam}/zones", json=zin, headers=auth_staff).status_code == 403
    assert client.post(f"/api/v1/cameras/{cam}/zones", json=zin, headers=auth_b).status_code == 404
    assert client.post(f"/api/v1/cameras/{cam}/zones", json={**zin, "polygon": poly[:2]}, headers=auth_a).status_code == 422
    assert client.post(f"/api/v1/cameras/{cam}/zones", json={**zin, "polygon": [[0, 0], [2, 0], [1, 1]]}, headers=auth_a).status_code == 422
    r = client.post(f"/api/v1/cameras/{cam}/zones", json=zin, headers=auth_a)
    assert r.status_code == 201, r.text
    z = r.json()
    assert z["polygon"] == poly and z["camera_external_id"] == "cam-a" and z["last_sample_ts"] is None
    assert client.post(f"/api/v1/cameras/{cam}/zones", json=zin, headers=auth_a).status_code == 409
    assert client.get("/api/v1/devices/me/config", headers=dev(fx.keys["a"])).json()["cameras"][0]["zones"] == [{"zone_id": "kasir", "name": "Antrean kasir", "polygon": poly}]

    # samples: accepted / duplicate / unknown zone / unknown camera / cross-store
    s1, s2 = sample(), sample(count=5, count_max=5)
    r = client.post("/api/v1/zones/samples", json={"samples": [s1, s2, s1, sample(zone="nope"), sample(cam="cam-b")]}, headers=dev(fx.keys["a"]))
    assert r.status_code == 200, r.text
    out = r.json()
    assert set(out["accepted"]) == {s1["sample_id"], s2["sample_id"]} and out["duplicates"] == [s1["sample_id"]]
    assert sorted(x["reason"] for x in out["rejected"]) == ["unknown camera", "unknown zone"]
    assert client.post("/api/v1/zones/samples", json={"samples": [s1]}, headers=dev(fx.keys["a"])).json()["duplicates"] == [s1["sample_id"]]
    assert client.post("/api/v1/zones/samples", json={"samples": [sample(count=4, count_max=3)]}, headers=dev(fx.keys["a"])).status_code == 422
    assert client.post("/api/v1/zones/samples", json={"samples": [{**sample(), "store_id": "x"}]}, headers=dev(fx.keys["a"])).status_code == 422
    assert client.post("/api/v1/zones/samples", json={"samples": [s1]}, headers=auth_a).status_code == 401

    zones = client.get(f"/api/v1/stores/{fx.ids['store_a']}/zones", headers=auth_staff).json()
    assert len(zones) == 1 and zones[0]["last_count"] in (2, 5) and zones[0]["last_sample_ts"] is not None
    assert client.get(f"/api/v1/stores/{fx.ids['store_a']}/zones", headers=auth_b).status_code == 404
    occ = client.get(f"/api/v1/stores/{fx.ids['store_a']}/zones/occupancy", headers=auth_a).json()
    assert occ["timezone"] == "Asia/Jakarta" and len(occ["zones"]) == 1 and len(occ["zones"][0]["buckets"]) == 24
    assert occ["zones"][0]["samples"] == 2 and occ["zones"][0]["peak"] == 5
    assert sum(b["samples"] for b in occ["zones"][0]["buckets"]) == 2
    assert client.get(f"/api/v1/stores/{fx.ids['store_a']}/zones/occupancy?date=2020-01-01", headers=auth_a).json()["zones"][0]["samples"] == 0

    r = client.patch(f"/api/v1/zones/{z['zone_id']}", json={"name": "Kasir 1"}, headers=auth_a)
    assert r.status_code == 200 and r.json()["name"] == "Kasir 1" and r.json()["last_count"] is not None
    assert client.patch(f"/api/v1/zones/{z['zone_id']}", json={"name": "x"}, headers=auth_b).status_code == 404
    assert client.delete(f"/api/v1/zones/{z['zone_id']}", headers=auth_staff).status_code == 403
    assert client.delete(f"/api/v1/zones/{z['zone_id']}", headers=auth_a).status_code == 204
    assert client.get(f"/api/v1/stores/{fx.ids['store_a']}/zones", headers=auth_a).json() == []
    assert client.get(f"/api/v1/stores/{fx.ids['store_a']}/zones/occupancy", headers=auth_a).json()["zones"] == []


def test_bucketize_pure():
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Asia/Jakarta")
    day = datetime(2026, 6, 1, tzinfo=tz)
    zid = uuid4()
    rows = [(zid, day + timedelta(hours=9, minutes=5), 2, 4), (zid, day + timedelta(hours=9, minutes=15), 4, 6),
            (zid, day + timedelta(hours=23, minutes=59), 1, 1), (zid, day + timedelta(hours=24), 9, 9), (zid, day - timedelta(seconds=1), 9, 9)]
    b = bucketize(rows, day)[zid]
    assert len(b) == 24 and b[9].avg_count == 3.0 and b[9].max_count == 6 and b[9].samples == 2 and b[23].samples == 1 and b[0].samples == 0
    assert bucketize([], day) == {}


# ----------------------------------------------------------------------------- ADR-029 Telegram
class FakeTelegram:
    def __init__(self, fail=False):
        self.calls: list[dict] = []
        self.fail = fail

    def transport(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert "bottest-token" in str(request.url)
            self.calls.append(json.loads(request.content))
            return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"}) if self.fail else httpx.Response(200, json={"ok": True})
        return httpx.MockTransport(handler)


@pytest.fixture
def tg(monkeypatch):
    fake = FakeTelegram()
    monkeypatch.setattr(telegram, "_transport", fake.transport())
    return fake


def test_telegram_settings_test_message_and_alert_flow(db_url, fx, tg):
    settings = Settings(database_url=db_url, cors_origins=[], auto_create_schema=False, jwt_secret=JWT_SECRET, telegram_bot_token="test-token")
    with TestClient(create_app(settings)) as c:

        auth_a, auth_b, staff = login(c, "owner-a@example.com"), login(c, "owner-b@example.com"), login(c, "staff-a@example.com")
        store = str(fx.ids["store_a"])
        assert c.get("/api/v1/notifications/channels", headers=staff).json() == {"telegram_configured": True}
        assert c.post(f"/api/v1/stores/{store}/telegram/test", headers=auth_a).status_code == 422  # no chat id yet
        assert c.put(f"/api/v1/stores/{store}/telegram", json={"chat_id": "abc"}, headers=auth_a).status_code == 422
        assert c.put(f"/api/v1/stores/{store}/telegram", json={}, headers=auth_a).status_code == 422
        assert c.put(f"/api/v1/stores/{store}/telegram", json={"chat_id": "-100123"}, headers=staff).status_code == 403
        assert c.put(f"/api/v1/stores/{store}/telegram", json={"chat_id": "-100123"}, headers=auth_b).status_code == 404
        r = c.put(f"/api/v1/stores/{store}/telegram", json={"chat_id": "-100123"}, headers=auth_a)
        assert r.status_code == 200 and r.json()["telegram_chat_id"] == "-100123"
        assert c.get("/api/v1/stores", headers=auth_a).json()[0]["telegram_chat_id"] == "-100123"
        r = c.post(f"/api/v1/stores/{store}/telegram/test", headers=auth_a)
        assert r.json() == {"ok": True, "error": None} and tg.calls[-1]["chat_id"] == "-100123" and "Pesan uji" in tg.calls[-1]["text"]

        # heartbeat then age it -> heartbeat_lost -> Telegram "opened"; heartbeat again -> resolved -> "pulih"
        c.put(f"/api/v1/stores/{store}/alert-rules", json={"heartbeat_lost_min": 3, "camera_down_min": 2, "buffer_pending_threshold": 1000, "no_events_min": None}, headers=auth_a)
        hb = {"schema_version": 1, "sent_at": datetime.now(timezone.utc).isoformat(), "source_status": "ok", "last_frame_age_s": 1,
              "pending_events": 0, "frames_processed": 1, "tracking_session_id": 0, "agent_version": "t"}
        assert c.post("/api/v1/devices/heartbeat", json=hb, headers=dev(fx.keys["a"])).status_code == 200
        import asyncio
        from sqlalchemy import update
        from app.db import Database
        from app.models import Device

        async def age():
            db = Database(db_url)
            async with db.sessionmaker() as s:
                await s.execute(update(Device).where(Device.id == fx.ids["device_a"]).values(last_heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=10)))
                await s.commit()
            await db.dispose()
        asyncio.run(age())
        n_before = len(tg.calls)
        alerts = c.get("/api/v1/alerts", headers=auth_a).json()
        assert alerts["open_count"] == 1 and alerts["alerts"][0]["rule"] == "heartbeat_lost", alerts
        assert len(tg.calls) == n_before + 1 and "heartbeat_lost" in tg.calls[-1]["text"] and "Toko A" in tg.calls[-1]["text"]
        c.get("/api/v1/alerts", headers=auth_a)
        assert len(tg.calls) == n_before + 1  # idempotent: not re-sent
        assert c.post("/api/v1/devices/heartbeat", json=hb, headers=dev(fx.keys["a"])).status_code == 200
        assert c.get("/api/v1/alerts", headers=auth_a).json()["open_count"] == 0
        assert len(tg.calls) == n_before + 2 and "pulih" in tg.calls[-1]["text"]
        c.get("/api/v1/alerts", headers=auth_a)
        assert len(tg.calls) == n_before + 2
        # switching the channel off stops messages
        assert c.put(f"/api/v1/stores/{store}/telegram", json={"chat_id": None}, headers=auth_a).json()["telegram_chat_id"] is None


def test_telegram_failure_is_retried_and_no_token_is_noop(db_url, fx, monkeypatch):
    fake = FakeTelegram(fail=True)
    monkeypatch.setattr(telegram, "_transport", fake.transport())
    settings = Settings(database_url=db_url, cors_origins=[], auto_create_schema=False, jwt_secret=JWT_SECRET, telegram_bot_token="test-token")
    with TestClient(create_app(settings)) as c:

        auth_a = login(c, "owner-a@example.com")
        store = str(fx.ids["store_a"])
        c.put(f"/api/v1/stores/{store}/telegram", json={"chat_id": "-1"}, headers=auth_a)
        r = c.post(f"/api/v1/stores/{store}/telegram/test", headers=auth_a).json()
        assert r["ok"] is False and "chat not found" in r["error"] and "test-token" not in r["error"]
    settings = Settings(database_url=db_url, cors_origins=[], auto_create_schema=False, jwt_secret=JWT_SECRET)
    with TestClient(create_app(settings)) as c:

        auth_a = login(c, "owner-a@example.com")
        assert c.get("/api/v1/notifications/channels", headers=auth_a).json() == {"telegram_configured": False}
        assert c.post(f"/api/v1/stores/{fx.ids['store_a']}/telegram/test", headers=auth_a).status_code == 503
        n = len(fake.calls)
        c.get("/api/v1/alerts", headers=auth_a)
        assert len(fake.calls) == n
