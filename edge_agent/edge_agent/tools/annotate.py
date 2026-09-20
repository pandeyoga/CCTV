"""Run the real pipeline on a recorded video and write an annotated review video + events JSONL.

  python -m edge_agent.tools.annotate --config config.yaml --out review.avi --events events.jsonl [--max-frames N]

Events are also written to the SQLite store configured in the YAML (sending disabled here), so the
same run can be evaluated with `edge_agent.tools.evaluate`.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import cv2

from ..cli import build_pipeline
from ..config import Secrets, load_config
from ..health import HealthState
from ..storage import EventStore
from .overlay import draw_counts, draw_crossings, draw_line, draw_tracks


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="edge_agent.tools.annotate")
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True, help="annotated video path (.avi MJPG or .mp4 mp4v)")
    p.add_argument("--events", default=None, help="JSONL of emitted events")
    p.add_argument("--max-frames", type=int, default=None)
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    health = HealthState()
    store = EventStore(cfg.store.path, cfg.store.capacity)
    pipeline = build_pipeline(cfg, Secrets.from_env(), health, store)
    writer = None
    events_fh = open(args.events, "w", encoding="utf-8") if args.events else None
    t0 = time.time()

    def on_frame(frame, events):
        nonlocal writer
        if frame.image is None:
            return
        if writer is None:
            fourcc = cv2.VideoWriter_fourcc(*("mp4v" if args.out.endswith(".mp4") else "MJPG"))
            fps = getattr(pipeline.source, "fps", 10.0) / cfg.source.frame_stride
            writer = cv2.VideoWriter(args.out, fourcc, fps, (frame.width, frame.height))
        img = frame.image.copy()
        draw_line(img, pipeline.counter.line)
        draw_tracks(img, pipeline.last_tracks, cfg.counter.anchor)
        draw_crossings(img, pipeline.last_crossings)
        draw_counts(img, pipeline.counter.enter_count, pipeline.counter.exit_count, frame.index)
        writer.write(img)
        for ev in events:
            print(f"{ev.event_type.value.upper():5s} frame={ev.frame_index} track={ev.track_id} ts={ev.event_ts.isoformat()}")
            if events_fh:
                events_fh.write(ev.model_dump_json() + "\n")

    try:
        processed = pipeline.run(max_frames=args.max_frames, frame_stride=cfg.source.frame_stride, on_frame=on_frame)
    finally:
        if writer is not None:
            writer.release()
        if events_fh:
            events_fh.close()
        store.close()
    dt = time.time() - t0
    print(json.dumps({"frames_processed": processed, "seconds": round(dt, 1), "fps_processed": round(processed / dt, 2) if dt else None,
                      "enter": pipeline.counter.enter_count, "exit": pipeline.counter.exit_count, "out": args.out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
