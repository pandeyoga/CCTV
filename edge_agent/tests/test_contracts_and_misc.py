import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from edge_agent.contracts import CountEventV1, event_batch_json_schema
from edge_agent.detection.yolox_onnx import letterbox, nms, postprocess
from edge_agent.redact import redact_secret, redact_text, redact_url

SCHEMA_FILE = Path(__file__).resolve().parents[2] / "contracts" / "event_v1.schema.json"


def test_committed_schema_matches_models():
    """SSOT guard: contracts/event_v1.schema.json must be regenerated when models change."""
    assert json.loads(SCHEMA_FILE.read_text()) == json.loads(json.dumps(event_batch_json_schema(), sort_keys=True))


def test_event_requires_tz_aware_ts_and_forbids_identity_fields():
    with pytest.raises(ValueError):
        CountEventV1(event_id=uuid4(), event_type="enter", event_ts=datetime(2026, 1, 1), camera_id="c",
                     line_id="l", track_id=1, frame_index=0, source_kind="file")
    with pytest.raises(ValueError):
        CountEventV1(event_id=uuid4(), event_type="enter", event_ts=datetime.now(timezone.utc), camera_id="c",
                     line_id="l", track_id=1, frame_index=0, source_kind="file", tenant_id="spoofed")


def test_redaction():
    assert redact_url("rtsp://admin:P%40ss@10.0.0.5:554/live") == "rtsp://***:***@10.0.0.5:554/live"
    assert redact_url("rtsp://10.0.0.5/live") == "rtsp://10.0.0.5/live"
    assert redact_secret("abcdef") == "***"
    assert redact_text("Authorization: Bearer abc.def") == "Authorization: Bearer ***"


def test_nms_suppresses_overlaps():
    boxes = np.array([[0, 0, 10, 10], [1, 1, 10, 10], [50, 50, 60, 60]], dtype=np.float32)
    scores = np.array([0.9, 0.8, 0.7], dtype=np.float32)
    assert nms(boxes, scores, 0.5) == [0, 2]


def test_letterbox_ratio_and_shape():
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    blob, ratio = letterbox(img, (640, 640))
    assert blob.shape == (3, 640, 640) and ratio == pytest.approx(1.0)
    blob, ratio = letterbox(np.zeros((1080, 1920, 3), dtype=np.uint8), (640, 640))
    assert ratio == pytest.approx(640 / 1920)


def test_postprocess_filters_person_and_normalizes():
    # cx, cy, w, h, obj, cls0(person), cls1
    raw = np.array([
        [320, 320, 100, 200, 0.9, 0.9, 0.1],   # person
        [100, 100, 50, 50, 0.9, 0.1, 0.9],     # not a person
        [320, 320, 100, 200, 0.2, 0.9, 0.1],   # low objectness
    ], dtype=np.float32)
    dets = postprocess(raw, ratio=1.0, frame_w=640, frame_h=640, conf_threshold=0.4, nms_threshold=0.45)
    assert len(dets) == 1
    x1, y1, x2, y2 = dets[0].bbox
    assert (x1, y1, x2, y2) == pytest.approx((270 / 640, 220 / 640, 370 / 640, 420 / 640))


def test_committed_heartbeat_schema_matches_models():
    from edge_agent.contracts import heartbeat_json_schema
    hb_file = SCHEMA_FILE.with_name("heartbeat_v1.schema.json")
    assert json.loads(hb_file.read_text()) == json.loads(json.dumps(heartbeat_json_schema(), sort_keys=True))


def test_tracking_session_id_is_optional_and_non_negative():
    from datetime import datetime, timezone
    from uuid import uuid4
    import pytest
    base = dict(event_id=uuid4(), event_type="enter", event_ts=datetime(2026, 6, 1, tzinfo=timezone.utc), camera_id="c",
                line_id="l", track_id=1, frame_index=1, source_kind="synthetic")
    assert CountEventV1(**base).tracking_session_id is None
    assert CountEventV1(**base, tracking_session_id=3).tracking_session_id == 3
    with pytest.raises(Exception):
        CountEventV1(**base, tracking_session_id=-1)
