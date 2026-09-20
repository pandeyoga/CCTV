"""Line calibration without a GUI (edge boxes are headless).

  python -m edge_agent.tools.calibrate snapshot --config config.yaml --out frame.png [--frame 100]
      -> saves a frame with a 0.1 normalized grid; read (x, y) of the door threshold off the grid.
  python -m edge_agent.tools.calibrate preview  --config config.yaml --out preview.png [--frame 100]
      -> draws the configured line + ENTER arrow on the frame so you can verify direction before running.
"""
from __future__ import annotations

import argparse
import sys

import cv2

from ..cli import build_source
from ..config import Secrets, load_config
from ..counting.line import DirectedLine
from ..health import HealthState
from .overlay import draw_grid, draw_line


def grab_frame(cfg, frame_index: int):
    source = build_source(cfg, Secrets.from_env(), HealthState())
    try:
        for frame in source.frames():
            if frame.index >= frame_index and frame.image is not None:
                return frame
    finally:
        source.close()
    raise SystemExit(f"no frame >= {frame_index} available from source")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="edge_agent.tools.calibrate")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("snapshot", "preview"):
        s = sub.add_parser(name)
        s.add_argument("--config", required=True)
        s.add_argument("--out", required=True)
        s.add_argument("--frame", type=int, default=0)
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    frame = grab_frame(cfg, args.frame)
    img = frame.image.copy()
    if args.cmd == "snapshot":
        draw_grid(img)
    else:
        line = DirectedLine(cfg.line.line_id, cfg.line.ax, cfg.line.ay, cfg.line.bx, cfg.line.by, cfg.line.enter_side)
        draw_line(img, line)
    cv2.imwrite(args.out, img)
    print(f"wrote {args.out} ({frame.width}x{frame.height}, frame {frame.index})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
