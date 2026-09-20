"""CLI: `python -m edge_agent.cli run --config config.yaml [--max-frames N] [--no-send]`."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading

from .config import EdgeConfig, Secrets, load_config
from .contracts import event_batch_json_schema
from .counting import CrossingCounter, DirectedLine
from .health import HealthState
from .pipeline import CounterPipeline, PipelineIdentity
from .redact import redact_text
from .storage import EventStore
from .tracking import IouTracker
from .transport import EventSender, HeartbeatSender


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


def _setup_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=level.upper(), handlers=[handler])


def build_source(cfg: EdgeConfig, secrets: Secrets, health: HealthState):
    s = cfg.source
    if s.kind == "file":
        from .video.file_source import FileVideoSource
        if not s.path:
            raise SystemExit("source.path is required for kind=file")
        return FileVideoSource(s.path, start_ts=s.start_ts_utc, fps_override=s.fps_override)
    if s.kind == "rtsp":
        from .video.rtsp_source import RtspVideoSource
        if not secrets.rtsp_url:
            raise SystemExit("EDGE_RTSP_URL env var is required for kind=rtsp")
        return RtspVideoSource(secrets.rtsp_url, on_status=health.set_source)
    from .video.synthetic import SyntheticSource
    return SyntheticSource(n_frames=s.synthetic_frames)


def build_detector(cfg: EdgeConfig):
    d = cfg.detector
    if d.kind == "yolox_onnx":
        from .detection.yolox_onnx import YoloxOnnxDetector
        if not d.model_path:
            raise SystemExit("detector.model_path is required for kind=yolox_onnx")
        return YoloxOnnxDetector(d.model_path, d.input_size, d.conf_threshold, d.nms_threshold)
    from .detection.scripted import ScriptedDetector
    return ScriptedDetector({})


def build_pipeline(cfg: EdgeConfig, secrets: Secrets, health: HealthState, store: EventStore) -> CounterPipeline:
    line = DirectedLine(cfg.line.line_id, cfg.line.ax, cfg.line.ay, cfg.line.bx, cfg.line.by, cfg.line.enter_side)
    counter = CrossingCounter(line, cfg.counter.hysteresis, cfg.counter.min_confirm_frames,
                              cfg.counter.track_ttl_frames, cfg.counter.anchor)
    tracker = IouTracker(cfg.tracker.min_iou, cfg.tracker.max_age, cfg.tracker.min_hits)
    source = build_source(cfg, secrets, health)
    return CounterPipeline(source, build_detector(cfg), tracker, counter, store, health,
                           PipelineIdentity(cfg.camera_id, cfg.source.kind), cfg.health_file)


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    secrets = Secrets.from_env()
    health = HealthState()
    store = EventStore(cfg.store.path, cfg.store.capacity)
    pipeline = build_pipeline(cfg, secrets, health, store)
    log = logging.getLogger("edge_agent")
    log.info("device=%s camera=%s source=%s detector=%s", cfg.device_id, cfg.camera_id, cfg.source.kind, cfg.detector.kind)

    stop_flag = threading.Event()
    sender_thread = None
    sender = None
    if cfg.backend and not args.no_send:
        if not secrets.api_key:
            raise SystemExit("EDGE_API_KEY env var is required to send events (or pass --no-send)")
        b = cfg.backend
        sender = EventSender(store, b.url, secrets.api_key, health, batch_size=b.batch_size, timeout_s=b.timeout_s,
                             base_backoff_s=b.base_backoff_s, max_backoff_s=b.max_backoff_s)
        sender_thread = threading.Thread(target=sender.run_forever, args=(stop_flag.is_set,), daemon=True)
        sender_thread.start()
        heartbeat = HeartbeatSender(health, b.url, secrets.api_key, interval_s=b.heartbeat_interval_s, timeout_s=b.timeout_s)
        threading.Thread(target=heartbeat.run_forever, args=(stop_flag.is_set,), daemon=True).start()
    else:
        log.warning("sending disabled; events accumulate in %s", cfg.store.path)

    def on_event(ev):
        log.info("%s track=%d frame=%d ts=%s", ev.event_type.value.upper(), ev.track_id, ev.frame_index, ev.event_ts.isoformat())

    try:
        processed = pipeline.run(max_frames=args.max_frames, on_event=on_event, frame_stride=cfg.source.frame_stride)
    finally:
        if sender is not None:
            sender.flush(max_batches=10)
        stop_flag.set()
        if cfg.health_file:
            health.write(cfg.health_file)
        store.close()
    snap = health.snapshot()
    log.info("done frames=%d enter=%d exit=%d pending=%d status=%s", processed, snap.enter_count, snap.exit_count,
             snap.buffer_pending, snap.status)
    return 0 if snap.status in ("ok", "degraded") else 2


def cmd_schema(_: argparse.Namespace) -> int:
    print(json.dumps(event_batch_json_schema(), indent=2, sort_keys=True))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    store = EventStore(cfg.store.path, cfg.store.capacity)
    c = store.counts()
    print(json.dumps({"pending": c.pending, "sent": c.sent, "rejected": c.rejected, "capacity": cfg.store.capacity}))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="edge_agent")
    p.add_argument("--log-level", default="INFO")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--config", required=True)
    r.add_argument("--max-frames", type=int, default=None)
    r.add_argument("--no-send", action="store_true")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("schema")
    s.set_defaults(fn=cmd_schema)
    st = sub.add_parser("status")
    st.add_argument("--config", required=True)
    st.set_defaults(fn=cmd_status)
    args = p.parse_args(argv)
    _setup_logging(args.log_level)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
