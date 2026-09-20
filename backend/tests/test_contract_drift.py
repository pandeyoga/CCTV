"""ADR-002 guard: backend contract models == committed schema generated from the edge agent."""
import json
from pathlib import Path

from app.contracts import event_batch_json_schema

SCHEMA_FILE = Path(__file__).resolve().parents[2] / "contracts" / "event_v1.schema.json"


def test_backend_contract_matches_committed_schema():
    assert json.loads(SCHEMA_FILE.read_text()) == json.loads(json.dumps(event_batch_json_schema(), sort_keys=True))


def test_backend_heartbeat_contract_matches_committed_schema():
    from app.contracts import heartbeat_json_schema
    hb_file = SCHEMA_FILE.with_name("heartbeat_v1.schema.json")
    assert json.loads(hb_file.read_text()) == json.loads(json.dumps(heartbeat_json_schema(), sort_keys=True))
