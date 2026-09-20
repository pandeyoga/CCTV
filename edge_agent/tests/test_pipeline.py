from datetime import datetime, timedelta, timezone

from edge_agent.contracts import EventType
from edge_agent.counting import CrossingCounter, DirectedLine
from edge_agent.detection import ScriptedDetector
from edge_agent.health import HealthState, HealthStatus
from edge_agent.pipeline import CounterPipeline, PipelineIdentity
from edge_agent.storage import EventStore
from edge_agent.tracking import IouTracker
from edge_agent.video import SyntheticSource

from helpers import det, walk

LINE = DirectedLine("door", 0.1, 0.5, 0.9, 0.5, enter_side="left")
T0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def build(tmp_path, script, n_frames, capacity=100, health_file=None):
    store = EventStore(tmp_path / "e.db", capacity=capacity)
    health = HealthState()
    pipeline = CounterPipeline(
        source=SyntheticSource(n_frames, fps=10.0, start_ts=T0),
        detector=ScriptedDetector(script),
        tracker=IouTracker(min_hits=2, max_age=10),
        counter=CrossingCounter(LINE, hysteresis=0.02, min_confirm_frames=2),
        store=store, health=health, identity=PipelineIdentity("cam-1", "synthetic"), health_file=health_file,
    )
    return pipeline, store, health


def test_one_person_enters_then_exits_end_to_end(tmp_path):
    ys = walk(0.9, 0.1, 20) + walk(0.1, 0.9, 20)
    script = {i: [det(0.5, y)] for i, y in enumerate(ys)}
    pipeline, store, health = build(tmp_path, script, len(ys))
    seen = []
    processed = pipeline.run(on_event=seen.append)
    assert processed == 40
    assert [e.event_type for e in seen] == [EventType.ENTER, EventType.EXIT]
    assert store.counts().pending == 2
    assert health.snapshot().enter_count == 1 and health.snapshot().exit_count == 1
    # event_ts derives from frame time base, not wall clock
    for e in seen:
        assert e.event_ts == T0 + timedelta(seconds=e.frame_index / 10.0)
        assert e.camera_id == "cam-1" and e.line_id == "door" and e.source_kind == "synthetic"


def test_detector_flicker_does_not_create_phantom_crossings(tmp_path):
    ys = walk(0.9, 0.1, 30)
    script = {i: ([det(0.5, y)] if i % 3 != 2 else []) for i, y in enumerate(ys)}  # drop every 3rd frame
    pipeline, store, _ = build(tmp_path, script, len(ys))
    seen = []
    pipeline.run(on_event=seen.append)
    assert [e.event_type for e in seen] == [EventType.ENTER]


def test_buffer_full_is_loud_not_silent(tmp_path, caplog):
    ys = walk(0.9, 0.1, 15) + walk(0.1, 0.9, 15) + walk(0.9, 0.1, 15)
    script = {i: [det(0.5, y)] for i, y in enumerate(ys)}
    pipeline, store, health = build(tmp_path, script, len(ys), capacity=1, health_file=str(tmp_path / "h.json"))
    with caplog.at_level("ERROR"):
        pipeline.run()
    snap = health.snapshot()
    assert snap.status == HealthStatus.BUFFER_FULL.value
    assert snap.events_lost_buffer_full == 2
    assert store.counts().pending == 1
    assert "EVENT LOST" in caplog.text
    assert (tmp_path / "h.json").exists()


def test_two_people_crossing_opposite_directions(tmp_path):
    a = walk(0.9, 0.1, 25)
    b = walk(0.1, 0.9, 25)
    script = {i: [det(0.25, a[i]), det(0.75, b[i])] for i in range(25)}
    pipeline, _, _ = build(tmp_path, script, 25)
    seen = []
    pipeline.run(on_event=seen.append)
    assert sorted(e.event_type for e in seen) == [EventType.ENTER, EventType.EXIT]
