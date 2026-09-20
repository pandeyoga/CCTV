# Pilot runbook — one store, one door, one camera

Purpose: get from "camera on the wall" to "measured accuracy numbers written in `docs/STATUS.md`". Nothing in this document contains measured numbers yet; fill the **Measured results** section only with what you actually observed.

## 0. What you need
- Edge box: Linux x86-64 or ARM64 (4 cores / 4 GB RAM minimum for YOLOX-S CPU; see step 5 for throughput check), Python 3.11+, on the same LAN as the camera.
- Camera with RTSP (H.264). Use the **sub-stream** (≤ 1280×720, ≤ 15 fps) for the agent.
- Backend reachable over HTTPS (`docker compose up` per `backend/README.md`), device API key from `python -m app.seed …`.
- 30–60 minutes of a person on site with a clicker/notebook for ground truth (step 7).

## 1. Camera placement (decides accuracy more than the model)
- Mount high, looking **down at the door threshold at 30–60°**; whole body visible on both sides of the threshold for ≥ 1 m.
- Avoid: head-on at eye level (occlusion), glass doors with reflections in frame, backlight from outside (set WDR/backlight compensation on the camera).
- Nobody should be able to stand *on* the threshold for long (deadband handles jitter, but a queue on the line is unmeasurable).

## 2. Install the agent
```bash
git clone <repo> && cd edge_agent
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[onnx]"
mkdir -p models
# YOLOX-S official ONNX export (Apache-2.0 repo; see docs/DECISIONS.md ADR-003 for the weights caveat)
curl -L -o models/yolox_s.onnx https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx
cp config.example.yaml config.yaml
cp .env.example .env && chmod 600 .env       # EDGE_API_KEY, EDGE_RTSP_URL — never commit
```
RTSP over TCP is far more stable than UDP on Wi-Fi/cheap switches:
```bash
export OPENCV_FFMPEG_CAPTURE_OPTIONS="rtsp_transport;tcp|stimeout;5000000"
```

## 3. Calibrate the line (headless)
```bash
set -a; . ./.env; set +a
python -m edge_agent.tools.calibrate snapshot --config config.yaml --out frame.png
```
Open `frame.png` (grid every 0.1 in normalized coordinates). Put the line **on the floor at the threshold**, spanning slightly wider than the door. Edit `line:` in `config.yaml`, then:
```bash
python -m edge_agent.tools.calibrate preview --config config.yaml --out preview.png
```
The cyan arrow is the line direction a→b; the **green arrow points to the ENTER side**. If it points outside, flip `enter_side`.
Anchor is `bottom_center` (feet). If the camera is nearly top-down, switch to `anchor: center`.

## 4. Dry run on a recording first
Record 5–10 minutes from the camera (`ffmpeg -rtsp_transport tcp -i "$EDGE_RTSP_URL" -c copy -t 600 sample.mp4`), set `source.kind: file`, then:
```bash
python -m edge_agent.tools.annotate --config config.yaml --out review.avi --events events.jsonl
```
Watch `review.avi`: boxes should stick to people with stable `#id`s across the line; each crossing should flash IN/OUT exactly once. Typical fixes:
| Symptom | Knob |
|---|---|
| Double counts when someone hesitates on the line | raise `counter.hysteresis` (0.03–0.05), `min_confirm_frames: 3` |
| Missed counts, ids change mid-crossing | lower `tracker.min_iou` (0.2), raise `tracker.max_age`, reduce `frame_stride` |
| Ghost boxes on posters/mannequins | raise `detector.conf_threshold` (0.5) |
| Counting people walking past outside | shorten the line to the door width |

## 5. Throughput check
`annotate` prints `fps_processed`. It must be ≥ camera fps / `frame_stride`. If not: increase `frame_stride` (2–3), lower camera sub-stream fps, or use a smaller input (`detector.input_size: [416, 416]` — YOLOX-S export is 640; re-export for other sizes) / YOLOX-Tiny/Nano. Keep `tracker.max_age` and `counter.track_ttl_frames` in *processed* frames.

## 6. Run as a service
```bash
sudo cp deploy/edge-agent.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now edge-agent
journalctl -u edge-agent -f          # logs are redacted (no key, no RTSP credentials)
cat edge_health.json                  # status must be "ok"; "buffer_full"/"auth_failed" are outages
```
Dashboard: device shows **Aktif** once the first batch is acknowledged.

## 7. Ground truth protocol (the only source of accuracy numbers)
1. Pick two sessions of ≥ 30 min at different traffic levels. Start the agent (or a recording) and the observer at the same wall-clock second.
2. Observer tallies **each** enter and exit with the time (phone stopwatch synced to video start), into `truth.csv`:
   ```csv
   t_seconds,event_type
   12.4,enter
   47.0,exit
   ```
   Rules: a person counts when their feet cross the threshold; staff count too; strollers/children count as persons (the model detects them); do not "correct" for the agent.
3. Evaluate:
   ```bash
   python -m edge_agent.tools.evaluate --truth truth.csv --events events.jsonl --fps <video fps / frame_stride adjusted: use the source fps> --tolerance 2 --json report.json
   ```
4. Paste the markdown table into **Measured results** below and into `docs/STATUS.md` with date, camera, config hash (`sha256sum config.yaml`) and clip length.

## 8. Acceptance for the pilot (proposal, agree with the customer)
Per direction over both sessions: recall ≥ 0.90 and precision ≥ 0.90, |count error| ≤ 10 %. If not met, iterate step 4 knobs first, then placement, then model (ADR-003 alternatives).

## Measured results
_None yet. Do not write estimates here._
