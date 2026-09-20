"""Regenerate /contracts/*.schema.json from edge_agent.contracts (the SSOT)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edge_agent.contracts import event_batch_json_schema, heartbeat_json_schema  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[2] / "contracts"
OUT_DIR.mkdir(parents=True, exist_ok=True)
for name, schema in (("event_v1.schema.json", event_batch_json_schema()), ("heartbeat_v1.schema.json", heartbeat_json_schema())):
    (OUT_DIR / name).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT_DIR / name}")
