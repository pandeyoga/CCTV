# Edge Agent (people counter)

Pipeline: `VideoSource -> Detector -> Tracker -> CrossingCounter -> SQLite (durable) -> EventSender (HTTPS)`.

## Run

```bash
cd edge_agent
pip install -e ".[dev]"            # add ",onnx" to use the YOLOX ONNX detector
cp config.example.yaml config.yaml # edit line coords, camera_id, backend url
cp .env.example .env               # fill EDGE_API_KEY / EDGE_RTSP_URL; never commit .env
set -a; source .env; set +a
python -m edge_agent.cli run --config config.yaml            # send to backend
python -m edge_agent.cli run --config config.yaml --no-send  # offline; events buffered in SQLite
python -m edge_agent.cli status --config config.yaml         # pending/sent/rejected counts
python -m edge_agent.cli schema                              # print event contract JSON schema
```

Health is written to `health_file` (default `./edge_health.json`). `status` values:
`ok | degraded | source_down | auth_failed | buffer_full`. `buffer_full` means events were lost —
this is intentionally loud (ERROR log + `events_lost_buffer_full` counter), never silent.

## Model weights

Not bundled. Official YOLOX-S ONNX export: `curl -L -o models/yolox_s.onnx https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx` (input 1×3×640×640). License notes: `docs/DECISIONS.md` ADR-003.

## Field-pilot tools (`edge_agent/tools/`, see `docs/PILOT_RUNBOOK.md`)

```bash
python -m edge_agent.tools.calibrate snapshot --config config.yaml --out frame.png     # grid for reading line coords
python -m edge_agent.tools.calibrate preview  --config config.yaml --out preview.png   # verify line + ENTER arrow
python -m edge_agent.tools.annotate --config config.yaml --out review.avi --events events.jsonl   # annotated review video
python -m edge_agent.tools.evaluate --truth truth.csv --events events.jsonl --fps 10 --tolerance 2  # vs manual tally
```
`deploy/edge-agent.service` is a systemd unit for running on the edge box.

## Tests

```bash
cd edge_agent && python -m pytest -q
```

All tests use synthetic fixtures (scripted detections). Field accuracy on real video has NOT been measured.
