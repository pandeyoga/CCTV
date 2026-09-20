"""YOLOX person detector via ONNX Runtime.

Code license: YOLOX (Megvii) Apache-2.0; onnxruntime MIT. Weights: see docs/DECISIONS.md ADR-003
(official YOLOX checkpoints are distributed from the Apache-2.0 repo; confirm with legal before
commercial release). No field accuracy has been measured yet for this project.

Pre/post-processing follows the official demo/ONNXRuntime/onnx_inference.py:
letterbox resize (pad 114), NO mean/std normalization, decode with strides 8/16/32.
"""
from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np

from ..video.base import Frame
from .base import Detection

PERSON_CLASS_ID = 0


def letterbox(image: np.ndarray, input_size: tuple[int, int]) -> tuple[np.ndarray, float]:
    h, w = image.shape[:2]
    ratio = min(input_size[0] / h, input_size[1] / w)
    padded = np.full((input_size[0], input_size[1], 3), 114, dtype=np.uint8)
    resized = cv2.resize(image, (int(w * ratio), int(h * ratio)), interpolation=cv2.INTER_LINEAR)
    padded[: resized.shape[0], : resized.shape[1]] = resized
    return padded.transpose(2, 0, 1).astype(np.float32), ratio


def decode_outputs(outputs: np.ndarray, input_size: tuple[int, int], strides=(8, 16, 32)) -> np.ndarray:
    grids, expanded_strides = [], []
    for stride in strides:
        hs, ws = input_size[0] // stride, input_size[1] // stride
        xv, yv = np.meshgrid(np.arange(ws), np.arange(hs))
        grid = np.stack((xv, yv), 2).reshape(1, -1, 2)
        grids.append(grid)
        expanded_strides.append(np.full((*grid.shape[:2], 1), stride))
    grids = np.concatenate(grids, 1)
    expanded_strides = np.concatenate(expanded_strides, 1)
    outputs = outputs.copy()
    outputs[..., :2] = (outputs[..., :2] + grids) * expanded_strides
    outputs[..., 2:4] = np.exp(outputs[..., 2:4]) * expanded_strides
    return outputs


def nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    """boxes: (N,4) x1y1x2y2. Returns kept indices sorted by score desc."""
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][iou <= iou_threshold]
    return keep


def postprocess(raw: np.ndarray, ratio: float, frame_w: int, frame_h: int, conf_threshold: float,
                nms_threshold: float, class_id: int = PERSON_CLASS_ID) -> list[Detection]:
    """raw: (N, 5+num_classes) decoded predictions in letterboxed pixel space (cx, cy, w, h, obj, cls...)."""
    cls_scores = raw[:, 5:]
    scores = raw[:, 4] * cls_scores[:, class_id]
    mask = (scores >= conf_threshold) & (cls_scores.argmax(1) == class_id)
    raw, scores = raw[mask], scores[mask]
    if len(raw) == 0:
        return []
    boxes = np.empty((len(raw), 4), dtype=np.float32)
    boxes[:, 0] = raw[:, 0] - raw[:, 2] / 2
    boxes[:, 1] = raw[:, 1] - raw[:, 3] / 2
    boxes[:, 2] = raw[:, 0] + raw[:, 2] / 2
    boxes[:, 3] = raw[:, 1] + raw[:, 3] / 2
    boxes /= ratio
    keep = nms(boxes, scores, nms_threshold)
    out: list[Detection] = []
    for i in keep:
        x1 = float(np.clip(boxes[i, 0] / frame_w, 0.0, 1.0))
        y1 = float(np.clip(boxes[i, 1] / frame_h, 0.0, 1.0))
        x2 = float(np.clip(boxes[i, 2] / frame_w, 0.0, 1.0))
        y2 = float(np.clip(boxes[i, 3] / frame_h, 0.0, 1.0))
        if x2 > x1 and y2 > y1:
            out.append(Detection(bbox=(x1, y1, x2, y2), confidence=float(scores[i]), class_id=class_id))
    return out


class YoloxOnnxDetector:
    name = "yolox_onnx"

    def __init__(self, model_path: str, input_size: tuple[int, int] = (640, 640),
                 conf_threshold: float = 0.4, nms_threshold: float = 0.45,
                 providers: Sequence[str] | None = None) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("install with: pip install 'edge-agent[onnx]'") from exc
        self.input_size = input_size
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold
        self._session = ort.InferenceSession(model_path, providers=list(providers or ["CPUExecutionProvider"]))
        self._input_name = self._session.get_inputs()[0].name

    def detect(self, frame: Frame) -> Sequence[Detection]:
        if frame.image is None:
            return []
        blob, ratio = letterbox(frame.image, self.input_size)
        raw = self._session.run(None, {self._input_name: blob[None, :, :, :]})[0]
        decoded = decode_outputs(raw, self.input_size)[0]
        return postprocess(decoded, ratio, frame.width, frame.height, self.conf_threshold, self.nms_threshold)
