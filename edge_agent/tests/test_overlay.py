import numpy as np

from edge_agent.contracts import EventType
from edge_agent.counting import DirectedLine
from edge_agent.counting.counter import Crossing
from edge_agent.tools.overlay import draw_counts, draw_crossings, draw_grid, draw_line, draw_tracks

from helpers import track


def test_overlays_draw_pixels_without_error():
    img = np.zeros((120, 160, 3), dtype=np.uint8)
    draw_grid(img)
    draw_line(img, DirectedLine("door", 0.1, 0.5, 0.9, 0.5, enter_side="right"))
    draw_tracks(img, [track(1, 0.5, 0.8)])
    draw_crossings(img, [Crossing(1, EventType.ENTER, "door", 3, 0.5, 0.5)])
    draw_counts(img, 1, 0, 3)
    assert img.sum() > 0
    # the counting line itself is drawn at y=0.5*120=60
    assert img[60, 80].sum() > 0
