"""Finding 1: only paths that intersect the finite line SEGMENT count as crossings."""
import pytest

from edge_agent.contracts import EventType
from edge_agent.counting import CrossingCounter, DirectedLine
from edge_agent.counting.line import SEGMENT_EPS

from helpers import track, walk

H_LINE = DirectedLine("door", 0.4, 0.5, 0.6, 0.5, enter_side="left")   # horizontal; LEFT of a->b (x+) is y<0.5 (up)
V_LINE = DirectedLine("door", 0.5, 0.3, 0.5, 0.7, enter_side="left")   # vertical; a->b is y+, LEFT is x>0.5
D_LINE = DirectedLine("door", 0.3, 0.3, 0.7, 0.7, enter_side="left")   # diagonal


def run(line, points, min_confirm=2, hysteresis=0.02, tid=1):
    c = CrossingCounter(line, hysteresis=hysteresis, min_confirm_frames=min_confirm)
    out = []
    for i, (x, y) in enumerate(points):
        out += c.update([track(tid, x, y)], i)
    return c, out


def vertical_walk(x, y_from, y_to, steps=12):
    return [(x, y) for y in walk(y_from, y_to, steps)]


def test_reproduction_from_review_outside_segment_is_not_counted():
    # line (0.4,0.5)-(0.6,0.5); anchor at x=0.9 moves from below to above the infinite line
    _, out = run(H_LINE, vertical_walk(0.9, 0.9, 0.1))
    assert out == []


@pytest.mark.parametrize("x", [0.5, 0.45, 0.55])
def test_valid_crossing_mid_segment_both_directions(x):
    c, out = run(H_LINE, vertical_walk(x, 0.9, 0.1) + vertical_walk(x, 0.1, 0.9))
    assert [e.event_type for e in out] == [EventType.ENTER, EventType.EXIT]
    assert (c.enter_count, c.exit_count) == (1, 1)


@pytest.mark.parametrize("x", [0.39, 0.61, 0.2, 0.95])
def test_passing_beyond_either_endpoint_gives_zero_events(x):
    c, out = run(H_LINE, vertical_walk(x, 0.9, 0.1))
    assert out == [] and (c.enter_count, c.exit_count) == (0, 0)


def test_touching_an_endpoint_counts_and_slightly_beyond_does_not():
    _, on_end = run(H_LINE, vertical_walk(0.6, 0.9, 0.1))
    assert len(on_end) == 1
    _, beyond = run(H_LINE, vertical_walk(0.6 + 1e-6, 0.9, 0.1))
    assert beyond == []
    assert SEGMENT_EPS == 1e-9


def test_walking_around_the_endpoint_is_not_counted_but_side_updates():
    # below the line at x=0.5 -> sidestep past the right endpoint -> up -> back to x=0.5 above the line
    pts = [(0.5, 0.7), (0.6, 0.7), (0.7, 0.7), (0.7, 0.55), (0.7, 0.45), (0.7, 0.3), (0.6, 0.3), (0.5, 0.3), (0.5, 0.3)]
    c, out = run(H_LINE, pts)
    assert out == []
    # the person is now confirmed above; walking straight down through the door must count as EXIT
    _, out2 = [], []
    for i, (x, y) in enumerate(vertical_walk(0.5, 0.3, 0.8), start=len(pts)):
        out2 += c.update([track(1, x, y)], i)
    assert [e.event_type for e in out2] == [EventType.EXIT]


def test_diagonal_path_through_segment_counts_even_if_confirmation_point_is_off_segment():
    # crosses the segment near x=0.5 while moving diagonally; by confirmation the anchor is at x~0.75
    pts = [(0.35, 0.8), (0.42, 0.65), (0.48, 0.53), (0.54, 0.47), (0.62, 0.38), (0.75, 0.2), (0.85, 0.1)]
    _, out = run(H_LINE, pts)
    assert len(out) == 1 and out[0].event_type is EventType.ENTER


def test_diagonal_path_beyond_segment_end_is_not_counted():
    pts = [(0.6, 0.8), (0.66, 0.65), (0.72, 0.53), (0.78, 0.47), (0.84, 0.38), (0.9, 0.2), (0.95, 0.1)]
    _, out = run(H_LINE, pts)
    assert out == []


def test_jitter_inside_deadband_never_counts():
    pts = [(0.5, 0.7)] * 3 + [(0.5, 0.5 + s) for s in (0.01, -0.01, 0.015, -0.015, 0.005, -0.005) * 4]
    c, out = run(H_LINE, pts)
    assert out == [] and (c.enter_count, c.exit_count) == (0, 0)


def test_turning_back_before_confirmation_is_not_counted():
    pts = [(0.5, 0.7)] * 3 + [(0.5, 0.45)] + [(0.5, 0.7)] * 3  # one frame on the far side < min_confirm_frames=2
    _, out = run(H_LINE, pts)
    assert out == []


def test_exit_then_reenter_gives_two_valid_events():
    c, out = run(H_LINE, vertical_walk(0.5, 0.1, 0.9) + vertical_walk(0.5, 0.9, 0.1))
    assert [e.event_type for e in out] == [EventType.EXIT, EventType.ENTER]


def test_vertical_line_inside_and_outside_segment():
    inside = [(x, 0.5) for x in walk(0.1, 0.9, 12)]
    outside = [(x, 0.8) for x in walk(0.1, 0.9, 12)]  # y=0.8 is beyond endpoint b (y=0.7)
    _, out_in = run(V_LINE, inside)
    _, out_out = run(V_LINE, outside)
    assert len(out_in) == 1 and out_out == []


def test_diagonal_line_inside_and_outside_segment():
    inside = [(0.5 + s, 0.5 - s) for s in walk(-0.3, 0.3, 12)]     # perpendicular through the midpoint
    outside = [(0.9 + s, 0.9 - s) for s in walk(-0.3, 0.3, 12)]    # perpendicular beyond endpoint b (0.7,0.7)
    _, out_in = run(D_LINE, inside)
    _, out_out = run(D_LINE, outside)
    assert len(out_in) == 1 and out_out == []


def test_segment_intersects_geometry_directly():
    assert H_LINE.segment_intersects((0.5, 0.6), (0.5, 0.4))
    assert not H_LINE.segment_intersects((0.7, 0.6), (0.7, 0.4))
    assert not H_LINE.segment_intersects((0.5, 0.6), (0.5, 0.55))          # does not reach the line
    assert not H_LINE.segment_intersects((0.3, 0.5), (0.7, 0.5))           # collinear walk along the line
    assert H_LINE.segment_intersects((0.4, 0.6), (0.4, 0.4))               # exactly on endpoint a
