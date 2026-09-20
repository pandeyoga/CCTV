from edge_agent.contracts import EventType
from edge_agent.counting import CrossingCounter, DirectedLine

from helpers import track, walk

# door line at y=0.5; "inside the store" is above (LEFT of a->b), outside below (RIGHT)
LINE = DirectedLine("door", 0.1, 0.5, 0.9, 0.5, enter_side="left")


def run(counter, path, track_id=1, start_frame=0):
    out = []
    for i, y in enumerate(path):
        out += counter.update([track(track_id, 0.5, y)], start_frame + i)
    return out


def test_walk_across_from_outside_to_inside_counts_one_enter():
    c = CrossingCounter(LINE, hysteresis=0.02, min_confirm_frames=2)
    events = run(c, walk(0.9, 0.1, 20))
    assert [e.event_type for e in events] == [EventType.ENTER]
    assert (c.enter_count, c.exit_count) == (1, 0)


def test_walk_inside_to_outside_counts_one_exit():
    c = CrossingCounter(LINE, hysteresis=0.02, min_confirm_frames=2)
    events = run(c, walk(0.1, 0.9, 20))
    assert [e.event_type for e in events] == [EventType.EXIT]


def test_jitter_inside_deadband_never_counts():
    c = CrossingCounter(LINE, hysteresis=0.03, min_confirm_frames=2)
    # approach from outside then oscillate +-0.02 around the line (inside the deadband)
    path = walk(0.9, 0.52, 5) + [0.52, 0.48, 0.51, 0.49, 0.52, 0.48] * 5
    assert run(c, path) == []


def test_oscillation_just_outside_deadband_needs_confirm_frames():
    c = CrossingCounter(LINE, hysteresis=0.02, min_confirm_frames=3)
    # single-frame blips past the deadband must not count
    path = walk(0.9, 0.6, 5) + [0.45, 0.6, 0.45, 0.6, 0.45, 0.6]
    assert run(c, path) == []
    # but sustained presence on the other side does
    events = run(c, [0.45, 0.44, 0.43], start_frame=100)
    assert [e.event_type for e in events] == [EventType.ENTER]


def test_exit_then_reenter_with_same_track_counts_both():
    c = CrossingCounter(LINE, hysteresis=0.02, min_confirm_frames=2)
    events = run(c, walk(0.1, 0.9, 15) + walk(0.9, 0.1, 15) + walk(0.1, 0.9, 15))
    assert [e.event_type for e in events] == [EventType.EXIT, EventType.ENTER, EventType.EXIT]
    assert (c.enter_count, c.exit_count) == (1, 2)


def test_new_track_id_appearing_on_other_side_is_not_a_crossing():
    c = CrossingCounter(LINE, hysteresis=0.02, min_confirm_frames=2)
    # track 1 stands outside, disappears near the line; track 2 appears inside
    run(c, walk(0.9, 0.55, 10), track_id=1)
    events = run(c, walk(0.45, 0.1, 10), track_id=2, start_frame=10)
    assert events == []


def test_track_lost_beyond_ttl_forgets_side():
    c = CrossingCounter(LINE, hysteresis=0.02, min_confirm_frames=2, track_ttl_frames=5)
    run(c, [0.9, 0.9, 0.9], track_id=1)
    assert c.active_tracks == 1
    c.update([], 50)  # long gap -> state expired
    assert c.active_tracks == 0
    events = run(c, [0.1, 0.1, 0.1], track_id=1, start_frame=51)  # same id re-appears inside
    assert events == []


def test_track_briefly_lost_then_reappears_on_same_side_no_count():
    c = CrossingCounter(LINE, hysteresis=0.02, min_confirm_frames=2, track_ttl_frames=30)
    run(c, [0.9, 0.9, 0.9], track_id=1)
    for f in range(3, 10):
        c.update([], f)
    assert run(c, [0.9, 0.9], track_id=1, start_frame=10) == []


def test_multiple_tracks_are_independent():
    c = CrossingCounter(LINE, hysteresis=0.02, min_confirm_frames=2)
    a = walk(0.9, 0.1, 12)
    b = walk(0.1, 0.9, 12)
    events = []
    for i in range(12):
        events += c.update([track(1, 0.3, a[i]), track(2, 0.7, b[i])], i)
    kinds = sorted(e.event_type for e in events)
    assert kinds == [EventType.ENTER, EventType.EXIT]
    assert {e.track_id for e in events} == {1, 2}


def test_enter_side_right_flips_semantics():
    c = CrossingCounter(DirectedLine("door", 0.1, 0.5, 0.9, 0.5, enter_side="right"), min_confirm_frames=1)
    events = run(c, walk(0.9, 0.1, 10))
    assert [e.event_type for e in events] == [EventType.EXIT]


def test_no_count_from_bbox_count_alone():
    """Three people standing still on both sides for many frames: zero events."""
    c = CrossingCounter(LINE, min_confirm_frames=1)
    for f in range(50):
        assert c.update([track(1, 0.2, 0.9), track(2, 0.5, 0.9), track(3, 0.8, 0.1)], f) == []
