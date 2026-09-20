"""Live QA for Phase 2 reports (ADR-025) against preview backend.
Run: pytest backend/tests/qa_live_reports.py -v -o addopts=""
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://cctv-system-1.preview.emergentagent.com").rstrip("/")
OWNER = ("owner@tokopilot.id", "Owner-Pilot-2026!")
ADMIN = ("admin@peoplecounter.app", "Admin-Pilot-2026!")
JKT = ZoneInfo("Asia/Jakarta")


def _login(email: str, pw: str) -> str:
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def owner_h():
    return {"Authorization": f"Bearer {_login(*OWNER)}"}


@pytest.fixture(scope="module")
def admin_h():
    return {"Authorization": f"Bearer {_login(*ADMIN)}"}


@pytest.fixture(scope="module")
def pilot_store(owner_h):
    r = requests.get(f"{BASE}/api/v1/stores", headers=owner_h, timeout=15)
    assert r.status_code == 200, r.text
    stores = r.json()
    pilot = next((s for s in stores if s["name"] == "Toko Pilot"), None)
    assert pilot, f"Toko Pilot not found: {stores}"
    return pilot


def _today_jkt() -> date:
    return datetime.now(timezone.utc).astimezone(JKT).date()


# --- Range report happy path ---
def test_report_7d_shape(owner_h, pilot_store):
    today = _today_jkt()
    frm = today - timedelta(days=6)
    r = requests.get(f"{BASE}/api/v1/stores/{pilot_store['store_id']}/report",
                     params={"from": frm.isoformat(), "to": today.isoformat()},
                     headers=owner_h, timeout=15)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["timezone"] == "Asia/Jakarta"
    assert b["current"]["days"] == 7 and b["previous"]["days"] == 7
    assert b["current"]["from_date"] == frm.isoformat()
    assert b["current"]["to_date"] == today.isoformat()
    assert b["previous"]["to_date"] == (frm - timedelta(days=1)).isoformat()
    assert b["previous"]["from_date"] == (frm - timedelta(days=7)).isoformat()
    # daily has 7 entries in order
    assert len(b["daily"]) == 7
    expected_dates = [(frm + timedelta(days=i)).isoformat() for i in range(7)]
    assert [d["date"] for d in b["daily"]] == expected_dates
    # hourly profile 0..23
    assert len(b["hourly_profile"]) == 24
    assert [h["hour"] for h in b["hourly_profile"]] == list(range(24))
    # sums match
    assert sum(d["enter"] for d in b["daily"]) == b["current"]["enter"]
    assert sum(h["enter"] for h in b["hourly_profile"]) == b["current"]["enter"]
    # synthetic seed => >0
    assert b["current"]["enter"] > 0, "expected synthetic seed enter > 0"


# --- Validation ---
def test_report_to_before_from(owner_h, pilot_store):
    r = requests.get(f"{BASE}/api/v1/stores/{pilot_store['store_id']}/report",
                     params={"from": "2026-01-10", "to": "2026-01-05"}, headers=owner_h, timeout=15)
    assert r.status_code == 422, r.text


def test_report_range_gt_92(owner_h, pilot_store):
    r = requests.get(f"{BASE}/api/v1/stores/{pilot_store['store_id']}/report",
                     params={"from": "2025-01-01", "to": "2025-06-01"}, headers=owner_h, timeout=15)
    assert r.status_code == 422, r.text


def test_report_missing_to(owner_h, pilot_store):
    r = requests.get(f"{BASE}/api/v1/stores/{pilot_store['store_id']}/report",
                     params={"from": "2026-01-01"}, headers=owner_h, timeout=15)
    assert r.status_code == 422, r.text


def test_report_unauthenticated(pilot_store):
    r = requests.get(f"{BASE}/api/v1/stores/{pilot_store['store_id']}/report",
                     params={"from": "2026-01-01", "to": "2026-01-02"}, timeout=15)
    assert r.status_code == 401, r.text


def test_report_other_tenant_404(owner_h):
    fake = "00000000-0000-0000-0000-000000000000"
    r = requests.get(f"{BASE}/api/v1/stores/{fake}/report",
                     params={"from": "2026-01-01", "to": "2026-01-02"}, headers=owner_h, timeout=15)
    assert r.status_code == 404, r.text


# --- Overview ---
def test_overview_owner(owner_h, pilot_store):
    r = requests.get(f"{BASE}/api/v1/overview", headers=owner_h, timeout=15)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert isinstance(rows, list) and len(rows) >= 1
    pilot = next((x for x in rows if x["store_id"] == pilot_store["store_id"]), None)
    assert pilot, f"Toko Pilot not in overview: {rows}"
    # Fields present
    for k in ["yesterday_enter", "avg_enter_7d", "last_event_at", "devices_problem", "devices_total", "date", "enter", "exit"]:
        assert k in pilot, f"missing {k}"
    assert pilot["devices_total"] == 1
    # Cross-check with /summary
    s = requests.get(f"{BASE}/api/v1/stores/{pilot_store['store_id']}/summary", headers=owner_h, timeout=15)
    assert s.status_code == 200, s.text
    sb = s.json()
    assert pilot["enter"] == sb["enter"], f"overview.enter={pilot['enter']} vs summary.enter={sb['enter']}"
    assert pilot["exit"] == sb["exit"]


def test_overview_admin_sees_all(admin_h, owner_h):
    a = requests.get(f"{BASE}/api/v1/overview", headers=admin_h, timeout=15).json()
    o = requests.get(f"{BASE}/api/v1/overview", headers=owner_h, timeout=15).json()
    assert len(a) >= len(o), f"admin rows={len(a)}, owner rows={len(o)}"
