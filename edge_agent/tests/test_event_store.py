from datetime import datetime, timezone
from uuid import uuid4

import pytest

from edge_agent.contracts import CountEventV1, EventType
from edge_agent.storage import BufferFullError, EventStore


def make_event(**kw) -> CountEventV1:
    base = dict(event_id=uuid4(), event_type=EventType.ENTER, event_ts=datetime.now(timezone.utc),
                camera_id="cam", line_id="door", track_id=1, frame_index=1, source_kind="synthetic")
    base.update(kw)
    return CountEventV1(**base)


def test_append_persists_before_send_and_survives_reopen(tmp_path):
    p = tmp_path / "e.db"
    ev = make_event()
    s = EventStore(p, capacity=10)
    s.append(ev)
    s.close()
    s2 = EventStore(p, capacity=10)
    rows = s2.pending(10)
    assert len(rows) == 1 and rows[0].event == ev and rows[0].attempts == 0
    assert s2.status_of(ev.event_id) == "pending"


def test_event_id_is_primary_key_no_duplicates(tmp_path):
    s = EventStore(tmp_path / "e.db")
    ev = make_event()
    s.append(ev)
    with pytest.raises(Exception):
        s.append(ev)


def test_capacity_raises_instead_of_dropping(tmp_path):
    s = EventStore(tmp_path / "e.db", capacity=2)
    s.append(make_event())
    s.append(make_event())
    with pytest.raises(BufferFullError):
        s.append(make_event())
    assert s.counts().pending == 2


def test_mark_sent_frees_capacity_and_only_after_ack(tmp_path):
    s = EventStore(tmp_path / "e.db", capacity=1)
    ev = make_event()
    s.append(ev)
    s.record_attempt([ev.event_id], "network")
    assert s.pending(10)[0].attempts == 1
    assert s.counts().pending == 1
    assert s.mark_sent([ev.event_id]) == 1
    assert s.status_of(ev.event_id) == "sent"
    s.append(make_event())  # capacity freed
    assert s.counts() .pending == 1


def test_pending_is_fifo(tmp_path):
    s = EventStore(tmp_path / "e.db")
    evs = [make_event(frame_index=i) for i in range(5)]
    for e in evs:
        s.append(e)
    assert [r.event.frame_index for r in s.pending(3)] == [0, 1, 2]


def test_rejected_leaves_pending_but_is_kept(tmp_path):
    s = EventStore(tmp_path / "e.db")
    ev = make_event()
    s.append(ev)
    s.mark_rejected(ev.event_id, "unknown camera")
    c = s.counts()
    assert (c.pending, c.rejected) == (0, 1)


def test_purge_sent_keeps_recent(tmp_path):
    s = EventStore(tmp_path / "e.db")
    evs = [make_event() for _ in range(5)]
    for e in evs:
        s.append(e)
    s.mark_sent([e.event_id for e in evs])
    assert s.purge_sent(keep_last=2) == 3
    assert s.counts().sent == 2
