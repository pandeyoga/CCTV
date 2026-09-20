import json

import httpx
import pytest

from edge_agent.health import HealthState, HealthStatus
from edge_agent.storage import EventStore
from edge_agent.transport import EventSender, SendOutcome

from test_event_store import make_event


class FakeServer:
    """Idempotent in-memory backend used to drive httpx.MockTransport."""

    def __init__(self):
        self.seen: set[str] = set()
        self.requests: list[httpx.Request] = []
        self.fail_next: list = []  # each item: int status or "network"
        self.reject_ids: set[str] = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_next:
            f = self.fail_next.pop(0)
            if f == "network":
                raise httpx.ConnectError("boom")
            return httpx.Response(f)
        if request.headers.get("Authorization") != "Bearer secret-key":
            return httpx.Response(401)
        body = json.loads(request.content)
        accepted, duplicates, rejected = [], [], []
        for ev in body["events"]:
            eid = ev["event_id"]
            if eid in self.reject_ids:
                rejected.append({"event_id": eid, "reason": "unknown camera"})
            elif eid in self.seen:
                duplicates.append(eid)
            else:
                self.seen.add(eid)
                accepted.append(eid)
        return httpx.Response(200, json={"accepted": accepted, "duplicates": duplicates, "rejected": rejected})


@pytest.fixture
def env(tmp_path):
    server = FakeServer()
    store = EventStore(tmp_path / "e.db", capacity=100)
    health = HealthState(buffer_capacity=100)
    sleeps: list[float] = []
    sender = EventSender(store, "https://backend.test", "secret-key", health,
                         client=httpx.Client(transport=httpx.MockTransport(server.handler)),
                         batch_size=2, base_backoff_s=1.0, max_backoff_s=8.0,
                         sleep=sleeps.append, rng=lambda: 0.5)  # jitter factor == 1.0
    return server, store, health, sender, sleeps


def test_happy_path_marks_sent_only_after_ack(env):
    server, store, health, sender, _ = env
    evs = [make_event() for _ in range(3)]
    for e in evs:
        store.append(e)
    results = sender.flush()
    assert [r.outcome for r in results] == [SendOutcome.SENT, SendOutcome.SENT, SendOutcome.NOTHING_TO_SEND]
    assert store.counts().pending == 0 and store.counts().sent == 3
    assert health.transport_status is HealthStatus.OK
    assert server.requests[0].url.path == "/api/v1/events/batch"


def test_event_id_stable_across_retries_and_server_dedups(env):
    server, store, health, sender, sleeps = env
    ev = make_event()
    store.append(ev)
    server.fail_next = ["network", 503]
    r1 = sender.send_once()
    r2 = sender.send_once()
    r3 = sender.send_once()
    assert (r1.outcome, r2.outcome, r3.outcome) == (SendOutcome.RETRY, SendOutcome.RETRY, SendOutcome.SENT)
    sent_ids = {json.loads(req.content)["events"][0]["event_id"] for req in server.requests}
    assert sent_ids == {str(ev.event_id)}
    assert store.status_of(ev.event_id) == "sent"
    # exponential backoff: 1s, 2s (jitter factor fixed at 1.0)
    assert (r1.next_delay_s, r2.next_delay_s) == (1.0, 2.0)


def test_not_marked_sent_when_server_unreachable(env):
    server, store, health, sender, _ = env
    store.append(make_event())
    server.fail_next = ["network"] * 5
    for _ in range(5):
        sender.send_once()
    assert store.counts().pending == 1
    assert store.pending(1)[0].attempts == 5
    assert health.transport_status is HealthStatus.DEGRADED


def test_backoff_is_capped(env):
    server, store, _, sender, _ = env
    store.append(make_event())
    server.fail_next = ["network"] * 6
    delays = [sender.send_once().next_delay_s for _ in range(6)]
    assert delays == [1.0, 2.0, 4.0, 8.0, 8.0, 8.0]


def test_duplicate_ack_is_treated_as_sent(env):
    server, store, _, sender, _ = env
    ev = make_event()
    server.seen.add(str(ev.event_id))  # server already has it (e.g. ack lost previously)
    store.append(ev)
    r = sender.send_once()
    assert r.outcome is SendOutcome.SENT and r.duplicates == 1 and r.accepted == 0
    assert store.status_of(ev.event_id) == "sent"


def test_auth_failure_is_surfaced_not_retried_blindly(tmp_path):
    server = FakeServer()
    store = EventStore(tmp_path / "e.db")
    health = HealthState()
    sender = EventSender(store, "https://backend.test", "wrong-key", health,
                         client=httpx.Client(transport=httpx.MockTransport(server.handler)))
    store.append(make_event())
    r = sender.send_once()
    assert r.outcome is SendOutcome.AUTH_FAILED
    assert health.overall() is HealthStatus.AUTH_FAILED
    assert store.counts().pending == 1


def test_server_rejected_event_is_marked_rejected_not_dropped(env):
    server, store, _, sender, _ = env
    bad, good = make_event(), make_event()
    server.reject_ids.add(str(bad.event_id))
    store.append(bad)
    store.append(good)
    r = sender.send_once()
    assert (r.accepted, r.rejected) == (1, 1)
    assert store.status_of(bad.event_id) == "rejected"
    assert store.status_of(good.event_id) == "sent"


def test_malformed_ack_does_not_mark_sent(tmp_path):
    def handler(_):
        return httpx.Response(200, json={"weird": True})

    store = EventStore(tmp_path / "e.db")
    sender = EventSender(store, "https://b", "k", HealthState(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    store.append(make_event())
    assert sender.send_once().outcome is SendOutcome.RETRY
    assert store.counts().pending == 1


def test_api_key_never_in_logs(env, caplog):
    server, store, _, sender, _ = env
    store.append(make_event())
    server.fail_next = ["network"]
    with caplog.at_level("DEBUG"):
        sender.send_once()
    assert "secret-key" not in caplog.text
