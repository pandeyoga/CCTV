"""Frame loop: source -> detector -> tracker -> counter -> SQLite (durable) -> [sender, separately]."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Sequence
from uuid import uuid4

from .contracts import CountEventV1, SourceKind
from .counting.counter import Crossing, CrossingCounter
from .detection.base import Detector
from .health import HealthState
from .storage.event_store import BufferFullError, EventStore
from .tracking.base import Track, Tracker
from .video.base import Frame, VideoSource

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineIdentity:
    camera_id: str
    source_kind: SourceKind


class CounterPipeline:
    def __init__(self, source: VideoSource, detector: Detector, tracker: Tracker, counter: CrossingCounter,
                 store: EventStore, health: HealthState, identity: PipelineIdentity,
                 health_file: str | None = None, health_every_n_frames: int = 25) -> None:
        self.source = source
        self.detector = detector
        self.tracker = tracker
        self.counter = counter
        self.store = store
        self.health = health
        self.identity = identity
        self.health_file = health_file
        self.health_every_n_frames = health_every_n_frames
        self.health.buffer_capacity = store.capacity
        self.last_tracks: Sequence[Track] = []
        self.last_crossings: list[Crossing] = []
        self._source_session: int | None = None
        self.tracking_session_id = 0  # increments on every stream discontinuity; stamped on events

    def _begin_session(self, frame: Frame) -> None:
        """Stream discontinuity: drop tracker + counter track state. Totals and the SQLite buffer are untouched."""
        if self._source_session is not None:
            self.tracking_session_id += 1
            log.warning("stream session changed (%s -> %s): resetting tracker/counter state, tracking_session_id=%d",
                        self._source_session, frame.session_id, self.tracking_session_id)
            self.tracker.reset()
            self.counter.reset()
        self._source_session = frame.session_id

    def process_frame(self, frame: Frame) -> list[CountEventV1]:
        if frame.session_id != self._source_session:
            self._begin_session(frame)
        detections = self.detector.detect(frame)
        tracks = self.tracker.update(detections, frame.index)
        crossings = self.counter.update(tracks, frame.index)
        self.last_tracks, self.last_crossings = tracks, crossings
        events: list[CountEventV1] = []
        for c in crossings:
            ev = CountEventV1(
                event_id=uuid4(), event_type=c.event_type, event_ts=frame.ts,
                camera_id=self.identity.camera_id, line_id=c.line_id, track_id=c.track_id,
                frame_index=frame.index, source_kind=self.identity.source_kind,
                tracking_session_id=self.tracking_session_id,
            )
            try:
                self.store.append(ev)  # durable before any network attempt
                events.append(ev)
            except BufferFullError as exc:
                self.health.events_lost_buffer_full += 1
                log.error("EVENT LOST (%s): %s track=%d frame=%d", exc, ev.event_type.value, c.track_id, frame.index)
        self.health.frames_processed += 1
        self.health.mark_frame(frame.ts)
        self.health.tracking_session_id = self.tracking_session_id
        self.health.enter_count = self.counter.enter_count
        self.health.exit_count = self.counter.exit_count
        if frame.index % self.health_every_n_frames == 0:
            self._refresh_health()
        return events

    def run(self, max_frames: int | None = None, on_event: Callable[[CountEventV1], None] | None = None,
            stop: Callable[[], bool] = lambda: False, frame_stride: int = 1,
            on_frame: Callable[[Frame, list[CountEventV1]], None] | None = None) -> int:
        """frame_stride=N processes every Nth source frame (CPU budget on RTSP). Returns frames processed."""
        if frame_stride < 1:
            raise ValueError("frame_stride must be >= 1")
        processed = 0
        try:
            for frame in self.source.frames():
                if stop() or (max_frames is not None and processed >= max_frames):
                    break
                if frame.index % frame_stride:
                    continue
                events = self.process_frame(frame)
                for ev in events:
                    if on_event:
                        on_event(ev)
                if on_frame:
                    on_frame(frame, events)
                processed += 1
        finally:
            self._refresh_health()
            self.source.close()
        return processed

    def _refresh_health(self) -> None:
        counts = self.store.counts()
        self.health.buffer_pending = counts.pending
        self.health.buffer_rejected = counts.rejected
        if self.health_file:
            self.health.write(self.health_file)
