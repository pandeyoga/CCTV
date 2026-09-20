from edge_agent.tracking import IouTracker

from helpers import det


def test_keeps_id_for_moving_object_and_outputs_after_min_hits():
    t = IouTracker(min_iou=0.3, max_age=5, min_hits=2)
    ys = [0.9 - 0.01 * i for i in range(20)]
    assert t.update([det(0.5, ys[0])], 0) == []  # not yet confirmed
    ids = set()
    for i, y in enumerate(ys[1:], start=1):
        out = t.update([det(0.5, y)], i)
        assert len(out) == 1
        ids.add(out[0].track_id)
    assert ids == {1}


def test_two_separate_people_get_distinct_ids():
    t = IouTracker(min_hits=1)
    out = t.update([det(0.2, 0.8), det(0.8, 0.8)], 0)
    assert sorted(o.track_id for o in out) == [1, 2]
    out = t.update([det(0.21, 0.8), det(0.79, 0.8)], 1)
    assert sorted(o.track_id for o in out) == [1, 2]


def test_lost_track_expires_and_new_id_assigned_after_max_age():
    t = IouTracker(min_hits=1, max_age=2)
    t.update([det(0.5, 0.8)], 0)
    for f in range(1, 5):
        assert t.update([], f) == []
    out = t.update([det(0.5, 0.8)], 5)
    assert out[0].track_id == 2


def test_short_occlusion_keeps_id_via_prediction():
    t = IouTracker(min_hits=1, max_age=5)
    for f, y in enumerate([0.9, 0.88, 0.86, 0.84]):
        t.update([det(0.5, y)], f)
    assert t.update([], 4) == []
    assert t.update([], 5) == []
    out = t.update([det(0.5, 0.78)], 6)
    assert out[0].track_id == 1


def test_reset_clears_state():
    t = IouTracker(min_hits=1)
    t.update([det(0.5, 0.8)], 0)
    t.reset()
    assert t.update([det(0.5, 0.8)], 0)[0].track_id == 1
