"""Frame loop: source -> detector -> tracker -> counter (+ zone sampler) -> SQLite (durable) -> [sender, separately].

Server configuration (ADR-030) arrives from another thread via `apply_config`; it is staged and swapped in at the start of
the next frame, so the frame loop never holds a lock during inference."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
from uuid import uuid4

from .contracts import CountEventV1, DeviceConfigV1, SourceKind, ZoneSampleV1
from .counting.counter import Crossing, CrossingCounter
from .counting.line import DirectedLine
from .counting.zones import Zone, ZoneSampler
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
    def __init__(self, source: VideoSource, detector: Detector, tracker: Tracker, counter: CrossingCounter | None,
                 store: EventStore, health: HealthState, identity: PipelineIdentity,
                 health_file: str | None = None, health_every_n_frames: int = 25, zone_sampler: ZoneSampler | None = None,
                 on_zone_samples: Callable[[list[ZoneSampleV1]], None] | None = None) -> None:
        self.source = source
        self.detector = detector
        self.tracker = tracker
        self.counter = counter  # None until a line exists (YAML or server)
        self.store = store
        self.health = health
        self.identity = identity
        self.health_file = health_file
        self.health_every_n_frames = health_every_n_frames
        self.zone_sampler = zone_sampler
        self.on_zone_samples = on_zone_samples
        self.health.buffer_capacity = store.capacity
        self.last_tracks: Sequence[Track] = []
        self.last_crossings: list[Crossing] = []
        self.last_image: np.ndarray | None = None  # latest frame image, for snapshot upload (read from another thread)
        self._source_session: int | None = None
        self.tracking_session_id = 0  # increments on every stream discontinuity; stamped on events
        self._pending_config: DeviceConfigV1 | None = None
        self._config_lock = threading.Lock()
        self.applied_config_version: str | None = None

    # ------------------------------------------------------------------ server config (ADR-030)
    def apply_config(self, cfg: DeviceConfigV1) -> None:
        """Thread-safe: stage a server config; it takes effect before the next processed frame."""
        with self._config_lock:
            self._pending_config = cfg

    def _take_pending_config(self) -> DeviceConfigV1 | None:
        with self._config_lock:
            cfg, self._pending_config = self._pending_config, None
            return cfg

    def _apply_now(self, cfg: DeviceConfigV1) -> None:
        cam = next((c for c in cfg.cameras if c.camera_id == self.identity.camera_id), None)
        if cam is None:
            log.warning("server config %s has no entry for camera %s; keeping current line/zones", cfg.config_version, self.identity.camera_id)
            return
        if cam.lines:
            l = cam.lines[0]  # one counting line per camera in this version
            if len(cam.lines) > 1:
                log.warning("camera %s has %d lines on the server; only %s is used", cam.camera_id, len(cam.lines), l.line_id)
            self.replace_line(DirectedLine(l.line_id, l.ax, l.ay, l.bx, l.by, l.enter_side))
        else:
            log.warning("server config has no line for camera %s; keeping current line", cam.camera_id)
        if self.zone_sampler is not None:
            self.zone_sampler.set_zones([Zone(z.zone_id, tuple(tuple(p) for p in z.polygon)) for z in cam.zones])
        self.applied_config_version = cfg.config_version
        log.info("applied server config %s: line=%s zones=%d", cfg.config_version, cam.lines[0].line_id if cam.lines else "-", len(cam.zones))

    def replace_line(self, line: DirectedLine) -> None:
        """Swap the counting line: per-track side state is dropped (a new geometry has no history), totals are kept."""
        if self.counter is not None and self.counter.line == line:
            return
        old = self.counter
        new = CrossingCounter(line, old.hysteresis, old.min_confirm_frames, old.track_ttl_frames, old.anchor) if old else CrossingCounter(line)
        if old is not None:
            new.enter_count, new.exit_count = old.enter_count, old.exit_count
        self.counter = new

    # ------------------------------------------------------------------ frame loop
    def _begin_session(self, frame: Frame) -> None:
        """Stream discontinuity: drop tracker + counter track state. Totals and the SQLite buffer are untouched."""
        if self._source_session is not None:
            self.tracking_session_id += 1
            log.warning("stream session changed (%s -> %s): resetting tracker/counter state, tracking_session_id=%d",
                        self._source_session, frame.session_id, self.tracking_session_id)
            self.tracker.reset()
            if self.counter is not None:
                self.counter.reset()
        self._source_session = frame.session_id

    def process_frame(self, frame: Frame) -> list[CountEventV1]:
        cfg = self._take_pending_config()
        if cfg is not None:
            self._apply_now(cfg)
        if frame.session_id != self._source_session:
            self._begin_session(frame)
        detections = self.detector.detect(frame)
        tracks = self.tracker.update(detections, frame.index)
        crossings = self.counter.update(tracks, frame.index) if self.counter is not None else []
        self.last_tracks, self.last_crossings = tracks, crossings
        if frame.image is not None:
            self.last_image = frame.image
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
        if self.zone_sampler is not None:
            samples = self.zone_sampler.update(tracks, frame.ts)
            if samples and self.on_zone_samples:
                self.on_zone_samples(samples)
        self.health.frames_processed += 1
        self.health.mark_frame(frame.ts)
        self.health.tracking_session_id = self.tracking_session_id
        if self.counter is not None:
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
