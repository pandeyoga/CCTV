"""Real edge EventSender -> real FastAPI app (in-process via TestClient, which is an httpx.Client)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "edge_agent"))

from edge_agent.contracts import CountEventV1, EventType  # noqa: E402
from edge_agent.health import HealthState, HealthStatus  # noqa: E402
from edge_agent.storage import EventStore  # noqa: E402
from edge_agent.transport import EventSender, SendOutcome  # noqa: E402


def _ev(camera_id="cam-a") -> CountEventV1:
    return CountEventV1(event_id=uuid4(), event_type=EventType.ENTER, event_ts=datetime(2026, 6, 1, 3, tzinfo=timezone.utc),
                        camera_id=camera_id, line_id="door-1", track_id=3, frame_index=42, source_kind="synthetic")


def test_edge_sender_against_real_backend(client, fx, auth_a, tmp_path):
    store = EventStore(tmp_path / "edge.db", capacity=100)
    health = HealthState()
    good, bad = _ev(), _ev("cam-nope")
    store.append(good)
    store.append(bad)
    sender = EventSender(store, str(client.base_url), fx.keys["a"], health, client=client)
    r = sender.send_once()
    assert r.outcome is SendOutcome.SENT and (r.accepted, r.rejected) == (1, 1)
    assert store.status_of(good.event_id) == "sent" and store.status_of(bad.event_id) == "rejected"
    # retry of an already-acked event is reported as duplicate and still counts as sent
    store2 = EventStore(tmp_path / "edge2.db", capacity=100)
    store2.append(good)
    r2 = EventSender(store2, str(client.base_url), fx.keys["a"], health, client=client).send_once()
    assert r2.outcome is SendOutcome.SENT and r2.duplicates == 1
    s = client.get(f"/api/v1/stores/{fx.ids['store_a']}/summary?date=2026-06-01", headers=auth_a).json()
    assert s["enter"] == 1


def test_edge_sender_wrong_key_surfaces_auth_failed(client, fx, auth_a, tmp_path):
    store = EventStore(tmp_path / "edge.db", capacity=100)
    store.append(_ev())
    health = HealthState()
    r = EventSender(store, str(client.base_url), "dk_bad.key", health, client=client).send_once()
    assert r.outcome is SendOutcome.AUTH_FAILED and health.overall() is HealthStatus.AUTH_FAILED
    assert store.counts().pending == 1
