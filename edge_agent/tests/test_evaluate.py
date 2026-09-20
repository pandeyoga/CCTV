import json

import pytest

from edge_agent.tools.evaluate import TimedEvent, evaluate, load_agent_jsonl, load_truth, match_direction, render_markdown


def test_exact_and_tolerant_matches():
    r = match_direction(truth=[10.0, 20.0, 30.0], agent=[10.5, 21.9, 45.0], tolerance=2.0)
    assert (r.matched, r.false_positive, r.missed, r.count_error) == (2, 1, 1, 0)
    assert r.precision == pytest.approx(2 / 3) and r.recall == pytest.approx(2 / 3)


def test_each_event_matched_once():
    r = match_direction(truth=[10.0, 10.5], agent=[10.2], tolerance=2.0)
    assert (r.matched, r.missed, r.false_positive) == (1, 1, 0)


def test_empty_sides_give_none_not_fake_numbers():
    r = match_direction(truth=[], agent=[5.0], tolerance=1.0)
    assert r.recall is None and r.precision == 0.0
    r2 = match_direction(truth=[5.0], agent=[], tolerance=1.0)
    assert r2.precision is None and r2.recall == 0.0


def test_directions_are_evaluated_separately_and_files_load(tmp_path):
    truth = tmp_path / "truth.csv"
    truth.write_text("t_seconds,event_type\n1.0,enter\n2.0,exit\n")
    ev = tmp_path / "events.jsonl"
    ev.write_text("\n".join(json.dumps({"frame_index": f, "event_type": t}) for f, t in [(10, "exit"), (20, "enter")]) + "\n")
    report = evaluate(load_truth(truth), load_agent_jsonl(ev, fps=10.0), tolerance=0.5)
    # agent 'exit' at 1.0s vs truth 'exit' at 2.0s -> no cross-direction matching
    assert report["directions"]["enter"]["matched"] == 0 and report["directions"]["exit"]["matched"] == 0
    md = render_markdown(report)
    assert "| enter | 1 | 1 | 0 | 1 | 1 | +0 |" in md


def test_bad_truth_type_rejected(tmp_path):
    truth = tmp_path / "t.csv"
    truth.write_text("t_seconds,event_type\n1.0,in\n")
    with pytest.raises(ValueError):
        load_truth(truth)


def test_timed_event_is_plain():
    assert TimedEvent(1.0, "enter").event_type == "enter"
