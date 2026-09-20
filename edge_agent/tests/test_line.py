import pytest

from edge_agent.counting import DirectedLine, Side

# horizontal line left->right at y=0.5: below (y>0.5) is RIGHT on screen (y-down), above is LEFT
H = DirectedLine("l", 0.0, 0.5, 1.0, 0.5)


def test_side_of_horizontal_line():
    assert H.side(0.5, 0.8, 0.02) is Side.RIGHT
    assert H.side(0.5, 0.2, 0.02) is Side.LEFT
    assert H.side(0.5, 0.505, 0.02) is Side.DEADBAND


def test_signed_distance_is_resolution_independent_and_perpendicular():
    diag = DirectedLine("d", 0.0, 0.0, 1.0, 1.0)
    assert diag.signed_distance(1.0, 0.0) == pytest.approx(-1 / 2 ** 0.5)
    assert diag.signed_distance(0.0, 1.0) == pytest.approx(1 / 2 ** 0.5)
    assert diag.signed_distance(0.3, 0.3) == pytest.approx(0.0)


def test_reversed_direction_flips_sides():
    rev = DirectedLine("r", 1.0, 0.5, 0.0, 0.5)
    assert rev.side(0.5, 0.8, 0.0) is Side.LEFT


def test_enter_side_mapping():
    assert H.is_enter(Side.LEFT) and not H.is_enter(Side.RIGHT)
    assert DirectedLine("x", 0, 0.5, 1, 0.5, enter_side="right").is_enter(Side.RIGHT)


@pytest.mark.parametrize("coords", [(0, 0, 0, 0), (-0.1, 0, 1, 1), (0, 0, 1.2, 1)])
def test_invalid_lines_rejected(coords):
    with pytest.raises(ValueError):
        DirectedLine("bad", *coords)
