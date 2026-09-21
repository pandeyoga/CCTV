"""Live preview QA for Phase-4 first slice (ADR-029 Telegram, ADR-030 lines+snapshot, ADR-031 zones).

Run: pytest backend/tests/qa_live_phase4.py -v -o addopts=""
Serial: module state passes camera_uuid + created zone_uuid between tests.

Cleanup responsibilities:
  * temporary line 'qa-line-TEST' — deleted here
  * temporary zone 'qa-zone-TEST' — deleted here (and cascades ZoneSamples)
  * Telegram chat_id — restored to original (None expected)
  * Existing 'door-1' line + 'kasir-1' (Antrean kasir) zone MUST remain.
"""
from __future__ import annotations

import io
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from PIL import Image

BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE = line.split("=", 1)[1].strip()
BASE = BASE.rstrip("/")

OWNER = ("owner@tokopilot.id", "Owner-Pilot-2026!")
STAFF = ("staff@tokopilot.id", "Staff-Pilot-2026!")

SEED = json.loads(Path("/app/memory/seed_output.json").read_text())
STORE_ID = SEED["store_id"]
DEV_KEY = SEED["device_api_key_SHOW_ONCE"]
CAM_EXT = "cam-door-front"

_STATE: dict = {}


def _login(cred):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": cred[0], "password": cred[1]}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _dev_hdr(ct="application/json"):
    return {"Authorization": f"Bearer {DEV_KEY}", "Content-Type": ct}


DEV_BEARER = {"Authorization": f"Bearer {DEV_KEY}"}


@pytest.fixture(scope="module")
def owner_token():
    return _login(OWNER)


@pytest.fixture(scope="module")
def staff_token():
    return _login(STAFF)


@pytest.fixture(scope="module")
def camera_uuid(owner_token):
    r = requests.get(f"{BASE}/api/v1/stores/{STORE_ID}/cameras", headers=_hdr(owner_token), timeout=30)
    assert r.status_code == 200, r.text
    for c in r.json():
        if c["external_id"] == CAM_EXT:
            return c["camera_id"]
    pytest.fail(f"camera {CAM_EXT} not found: {r.json()}")


# ---------------------------------------------------------------- ADR-029 Telegram
class TestTelegram:
    def test_channels_no_token(self, owner_token):
        r = requests.get(f"{BASE}/api/v1/notifications/channels", headers=_hdr(owner_token))
        assert r.status_code == 200
        assert r.json() == {"telegram_configured": False}

    def test_put_chat_id_owner(self, owner_token):
        r = requests.put(f"{BASE}/api/v1/stores/{STORE_ID}/telegram", headers=_hdr(owner_token),
                         json={"chat_id": "-1001234"})
        assert r.status_code == 200, r.text
        assert r.json()["telegram_chat_id"] == "-1001234"
        # visible in list
        r2 = requests.get(f"{BASE}/api/v1/stores", headers=_hdr(owner_token))
        assert r2.status_code == 200
        found = [s for s in r2.json() if s["store_id"] == STORE_ID]
        assert found and found[0]["telegram_chat_id"] == "-1001234"

    def test_staff_403(self, staff_token):
        r = requests.put(f"{BASE}/api/v1/stores/{STORE_ID}/telegram", headers=_hdr(staff_token),
                         json={"chat_id": "-1005555"})
        assert r.status_code == 403, r.text

    def test_invalid_chat_id_422(self, owner_token):
        r = requests.put(f"{BASE}/api/v1/stores/{STORE_ID}/telegram", headers=_hdr(owner_token),
                         json={"chat_id": "abc"})
        assert r.status_code == 422, r.text

    def test_test_endpoint_503_without_token(self, owner_token):
        r = requests.post(f"{BASE}/api/v1/stores/{STORE_ID}/telegram/test", headers=_hdr(owner_token))
        assert r.status_code == 503, r.text

    def test_reset_null(self, owner_token):
        r = requests.put(f"{BASE}/api/v1/stores/{STORE_ID}/telegram", headers=_hdr(owner_token),
                         json={"chat_id": None})
        assert r.status_code == 200, r.text
        assert r.json()["telegram_chat_id"] is None


# ---------------------------------------------------------------- ADR-030 Device config + lines
class TestDeviceConfigAndLines:
    def test_device_config_ok(self):
        r = requests.get(f"{BASE}/api/v1/devices/me/config", headers=DEV_BEARER)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "config_version" in data
        assert data["config_version"]
        cams = {c["camera_id"]: c for c in data["cameras"]}
        assert CAM_EXT in cams, cams
        assert isinstance(cams[CAM_EXT]["lines"], list)
        assert isinstance(cams[CAM_EXT]["zones"], list)
        _STATE["initial_version"] = data["config_version"]

    def test_device_config_rejects_jwt(self, owner_token):
        r = requests.get(f"{BASE}/api/v1/devices/me/config", headers={"Authorization": f"Bearer {owner_token}"})
        assert r.status_code == 401, r.text

    def test_put_line_qa(self, owner_token, camera_uuid):
        r = requests.put(f"{BASE}/api/v1/cameras/{camera_uuid}/lines/qa-line-TEST", headers=_hdr(owner_token),
                         json={"ax": 0.1, "ay": 0.5, "bx": 0.9, "by": 0.5, "enter_side": "left"})
        assert r.status_code == 200, r.text
        # config_version must change
        r2 = requests.get(f"{BASE}/api/v1/devices/me/config", headers=DEV_BEARER)
        assert r2.status_code == 200
        assert r2.json()["config_version"] != _STATE.get("initial_version")

    def test_put_line_identical_endpoints_422(self, owner_token, camera_uuid):
        r = requests.put(f"{BASE}/api/v1/cameras/{camera_uuid}/lines/qa-line-BAD", headers=_hdr(owner_token),
                         json={"ax": 0.5, "ay": 0.5, "bx": 0.5, "by": 0.5, "enter_side": "left"})
        assert r.status_code == 422, r.text

    def test_put_line_out_of_range_422(self, owner_token, camera_uuid):
        r = requests.put(f"{BASE}/api/v1/cameras/{camera_uuid}/lines/qa-line-BAD", headers=_hdr(owner_token),
                         json={"ax": 1.5, "ay": 0.5, "bx": 0.9, "by": 0.5, "enter_side": "left"})
        assert r.status_code == 422, r.text

    def test_staff_put_line_403(self, staff_token, camera_uuid):
        r = requests.put(f"{BASE}/api/v1/cameras/{camera_uuid}/lines/qa-line-STAFF", headers=_hdr(staff_token),
                         json={"ax": 0.1, "ay": 0.5, "bx": 0.9, "by": 0.5, "enter_side": "left"})
        assert r.status_code == 403, r.text

    def test_delete_qa_line(self, owner_token, camera_uuid):
        r = requests.delete(f"{BASE}/api/v1/cameras/{camera_uuid}/lines/qa-line-TEST", headers=_hdr(owner_token))
        assert r.status_code == 204, r.text
        r2 = requests.delete(f"{BASE}/api/v1/cameras/{camera_uuid}/lines/qa-line-TEST", headers=_hdr(owner_token))
        assert r2.status_code == 404, r2.text

    def test_door_1_line_still_present(self, owner_token, camera_uuid):
        r = requests.get(f"{BASE}/api/v1/cameras/{camera_uuid}/lines", headers=_hdr(owner_token))
        assert r.status_code == 200
        ids = {l["line_id"] for l in r.json()}
        assert "door-1" in ids, f"door-1 line removed! {ids}"


# ---------------------------------------------------------------- ADR-030 Snapshot
def _make_jpeg(text="QA-SNAPSHOT"):
    im = Image.new("RGB", (160, 90), (30, 30, 30))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=60)
    return buf.getvalue()


class TestSnapshot:
    def test_upload_ok(self):
        jpg = _make_jpeg()
        r = requests.post(f"{BASE}/api/v1/devices/snapshot?camera_id={CAM_EXT}",
                          headers=_dev_hdr("image/jpeg"), data=jpg)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["camera_id"] == CAM_EXT
        assert j["bytes"] == len(jpg)
        assert j["snapshot_at"]

    def test_non_jpeg_415(self):
        r = requests.post(f"{BASE}/api/v1/devices/snapshot?camera_id={CAM_EXT}",
                          headers=_dev_hdr("application/octet-stream"), data=b"not-a-jpeg-body-1234")
        assert r.status_code == 415, r.text

    def test_unknown_camera_404(self):
        r = requests.post(f"{BASE}/api/v1/devices/snapshot?camera_id=nope-xyz",
                          headers=_dev_hdr("image/jpeg"), data=_make_jpeg())
        assert r.status_code == 404, r.text

    def test_owner_get_snapshot(self, owner_token, camera_uuid):
        r = requests.get(f"{BASE}/api/v1/cameras/{camera_uuid}/snapshot", headers=_hdr(owner_token))
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("image/jpeg")
        assert r.content[:3] == b"\xff\xd8\xff"

    def test_cameras_list_snapshot_at(self, owner_token):
        r = requests.get(f"{BASE}/api/v1/stores/{STORE_ID}/cameras", headers=_hdr(owner_token))
        assert r.status_code == 200
        cam = next(c for c in r.json() if c["external_id"] == CAM_EXT)
        assert cam.get("snapshot_at") is not None


# ---------------------------------------------------------------- ADR-031 Zones + occupancy
class TestZones:
    def test_create_zone(self, owner_token, camera_uuid):
        r = requests.post(f"{BASE}/api/v1/cameras/{camera_uuid}/zones", headers=_hdr(owner_token),
                          json={"external_id": "qa-zone-TEST", "name": "QA Zona",
                                "polygon": [[0.6, 0.2], [0.9, 0.2], [0.9, 0.6], [0.6, 0.6]]})
        assert r.status_code == 201, r.text
        _STATE["zone_uuid"] = r.json()["zone_id"]

    def test_create_zone_duplicate(self, owner_token, camera_uuid):
        r = requests.post(f"{BASE}/api/v1/cameras/{camera_uuid}/zones", headers=_hdr(owner_token),
                          json={"external_id": "qa-zone-TEST", "name": "QA Zona",
                                "polygon": [[0.6, 0.2], [0.9, 0.2], [0.9, 0.6], [0.6, 0.6]]})
        assert r.status_code == 409, r.text

    def test_polygon_too_small_422(self, owner_token, camera_uuid):
        r = requests.post(f"{BASE}/api/v1/cameras/{camera_uuid}/zones", headers=_hdr(owner_token),
                          json={"external_id": "qa-zone-BAD", "name": "bad", "polygon": [[0.1, 0.1], [0.9, 0.1]]})
        assert r.status_code == 422, r.text

    def test_ingest_samples(self):
        ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        _STATE["sample_ids"] = ids
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        body = {"samples": [
            {"sample_id": ids[0], "camera_id": CAM_EXT, "zone_id": "qa-zone-TEST",
             "sample_ts": now, "interval_s": 10, "count": 2, "count_max": 3},
            {"sample_id": ids[1], "camera_id": CAM_EXT, "zone_id": "qa-zone-TEST",
             "sample_ts": now, "interval_s": 10, "count": 2, "count_max": 3},
        ]}
        r = requests.post(f"{BASE}/api/v1/zones/samples", headers=_dev_hdr(), json=body)
        assert r.status_code == 200, r.text
        j = r.json()
        assert set(j["accepted"]) == set(ids), j
        assert j["duplicates"] == []
        assert j["rejected"] == []

    def test_ingest_duplicates(self):
        ids = _STATE["sample_ids"]
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        body = {"samples": [
            {"sample_id": ids[0], "camera_id": CAM_EXT, "zone_id": "qa-zone-TEST",
             "sample_ts": now, "interval_s": 10, "count": 2, "count_max": 3},
        ]}
        r = requests.post(f"{BASE}/api/v1/zones/samples", headers=_dev_hdr(), json=body)
        assert r.status_code == 200, r.text
        assert r.json()["duplicates"] == [ids[0]]

    def test_ingest_unknown_zone(self):
        sid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        body = {"samples": [
            {"sample_id": sid, "camera_id": CAM_EXT, "zone_id": "does-not-exist",
             "sample_ts": now, "interval_s": 10, "count": 1, "count_max": 1},
        ]}
        r = requests.post(f"{BASE}/api/v1/zones/samples", headers=_dev_hdr(), json=body)
        assert r.status_code == 200, r.text
        assert r.json()["rejected"] == [{"sample_id": sid, "reason": "unknown zone"}]

    def test_ingest_count_max_less_than_count_422(self):
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        body = {"samples": [
            {"sample_id": str(uuid.uuid4()), "camera_id": CAM_EXT, "zone_id": "qa-zone-TEST",
             "sample_ts": now, "interval_s": 10, "count": 5, "count_max": 1},
        ]}
        r = requests.post(f"{BASE}/api/v1/zones/samples", headers=_dev_hdr(), json=body)
        assert r.status_code == 422, r.text

    def test_zones_list_shows_last_count(self, owner_token):
        r = requests.get(f"{BASE}/api/v1/stores/{STORE_ID}/zones", headers=_hdr(owner_token))
        assert r.status_code == 200, r.text
        z = next((x for x in r.json() if x["external_id"] == "qa-zone-TEST"), None)
        assert z is not None
        assert z["last_count"] == 2
        assert z["last_count_max"] == 3
        assert z["last_sample_ts"] is not None

    def test_occupancy_today(self, owner_token):
        r = requests.get(f"{BASE}/api/v1/stores/{STORE_ID}/zones/occupancy", headers=_hdr(owner_token))
        assert r.status_code == 200, r.text
        j = r.json()
        z = next((x for x in j["zones"] if x["external_id"] == "qa-zone-TEST"), None)
        assert z is not None
        assert len(z["buckets"]) == 24
        assert z["samples"] == 2
        assert z["peak"] == 3

    def test_staff_can_read_zones(self, staff_token):
        r = requests.get(f"{BASE}/api/v1/stores/{STORE_ID}/zones", headers=_hdr(staff_token))
        assert r.status_code == 200

    def test_staff_cannot_delete_zone(self, staff_token):
        r = requests.delete(f"{BASE}/api/v1/zones/{_STATE['zone_uuid']}", headers=_hdr(staff_token))
        assert r.status_code == 403, r.text

    def test_owner_delete_zone(self, owner_token):
        r = requests.delete(f"{BASE}/api/v1/zones/{_STATE['zone_uuid']}", headers=_hdr(owner_token))
        assert r.status_code == 204, r.text

    def test_kasir_1_zone_preserved(self, owner_token):
        r = requests.get(f"{BASE}/api/v1/stores/{STORE_ID}/zones", headers=_hdr(owner_token))
        assert r.status_code == 200
        ids = {z["external_id"] for z in r.json()}
        assert "kasir-1" in ids, f"kasir-1 zone missing: {ids}"
        assert "qa-zone-TEST" not in ids


# ---------------------------------------------------------------- Regression: alerts still works
class TestAlertsRegression:
    def test_alerts_ok(self, owner_token):
        r = requests.get(f"{BASE}/api/v1/alerts", headers=_hdr(owner_token))
        assert r.status_code == 200, r.text
        j = r.json()
        assert "alerts" in j and "open_count" in j
