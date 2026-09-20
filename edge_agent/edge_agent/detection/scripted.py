from __future__ import annotations

from typing import Mapping, Sequence

from ..video.base import Frame
from .base import Detection


class ScriptedDetector:
    """Test fixture: returns pre-scripted detections per frame index. No model involved."""

    name = "scripted"

    def __init__(self, script: Mapping[int, Sequence[Detection]]) -> None:
        self._script = dict(script)

    def detect(self, frame: Frame) -> Sequence[Detection]:
        return list(self._script.get(frame.index, ()))
