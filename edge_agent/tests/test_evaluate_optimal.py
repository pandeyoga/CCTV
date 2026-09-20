"""Finding 6: matching must maximise valid pairs (then minimise total |dt|), verified against brute force."""
import itertools
import random

import pytest

from edge_agent.tools.evaluate import TimedEvent, evaluate, match_direction, optimal_pairs


def brute_force(truth, agent, tol):
    """Oracle: best (pairs, -total_dt) over all injective partial assignments."""
    best = (0, 0.0)
    n, m = len(truth), len(agent)
    for k in range(min(n, m), -1, -1):
        for ti in itertools.combinations(range(n), k):
            for aj in itertools.permutations(range(m), k):
                if all(abs(truth[i] - agent[j]) <= tol for i, j in zip(ti, aj)):
                    total = sum(abs(truth[i] - agent[j]) for i, j in zip(ti, aj))
                    if (k, -total) > best:
                        best = (k, -total)
        if best[0] == k and k > 0:
            break
    return best[0], -best[1]


def test_reproduction_from_review_two_pairs_not_one():
    r = match_direction(truth=[1.0, 2.0], agent=[0.0, 1.1], tolerance=1.0)
    assert (r.matched, r.false_positive, r.missed, r.count_error) == (2, 0, 0, 0)
    assert r.total_abs_dt_s == pytest.approx(1.9)


def test_empty_inputs():
    assert match_direction([], [], 1.0).matched == 0
    assert match_direction([1.0], [], 1.0).recall == 0.0 and match_direction([1.0], [], 1.0).precision is None
    assert match_direction([], [1.0], 1.0).precision == 0.0 and match_direction([], [1.0], 1.0).recall is None


def test_unequal_sizes_repeated_timestamps_and_unsorted_input():
    r = match_direction(truth=[5.0, 5.0, 5.0, 20.0], agent=[5.2, 4.9, 30.0], tolerance=1.0)
    assert (r.matched, r.false_positive, r.missed, r.count_error) == (2, 1, 2, -1)
    r2 = match_direction(truth=[20.0, 5.0, 5.0, 5.0], agent=[30.0, 4.9, 5.2], tolerance=1.0)
    assert (r2.matched, r2.total_abs_dt_s) == (r.matched, r.total_abs_dt_s)  # order-independent


def test_pair_exactly_on_tolerance_boundary_is_matched():
    assert match_direction([10.0], [12.0], tolerance=2.0).matched == 1
    assert match_direction([10.0], [12.0001], tolerance=2.0).matched == 0


def test_enter_and_exit_are_never_cross_matched():
    rep = evaluate([TimedEvent(1.0, "enter")], [TimedEvent(1.0, "exit")], tolerance=5.0)
    assert rep["directions"]["enter"]["matched"] == 0 and rep["directions"]["exit"]["matched"] == 0
    assert rep["directions"]["enter"]["missed"] == 1 and rep["directions"]["exit"]["false_positive"] == 1


def test_each_event_used_at_most_once():
    pairs = optimal_pairs([10.0, 10.5], [10.2], tolerance=2.0)
    assert len(pairs) == 1
    pairs = optimal_pairs([10.0], [9.9, 10.1, 10.2], tolerance=2.0)
    assert len(pairs) == 1 and len({j for _, j in pairs}) == 1


def test_min_total_dt_among_max_cardinality_solutions():
    # both assignments give 2 pairs; the optimum pairs (0->0.1, 1->1.0) with total 0.1 rather than 1.9
    pairs = optimal_pairs([0.0, 1.0], [0.1, 1.0], tolerance=1.0)
    assert sorted(pairs) == [(0, 0), (1, 1)]


def test_deterministic_on_ties():
    a = optimal_pairs([0.0, 2.0], [1.0, 1.0], tolerance=1.0)
    for _ in range(5):
        assert optimal_pairs([0.0, 2.0], [1.0, 1.0], tolerance=1.0) == a


@pytest.mark.parametrize("seed", range(40))
def test_matches_exhaustive_oracle_on_small_random_cases(seed):
    rng = random.Random(seed)
    n, m = rng.randint(0, 5), rng.randint(0, 5)
    truth = sorted(round(rng.uniform(0, 10), 1) for _ in range(n))
    agent = sorted(round(rng.uniform(0, 10), 1) for _ in range(m))
    tol = rng.choice([0.5, 1.0, 2.0])
    r = match_direction(truth, agent, tol)
    k, total = brute_force(truth, agent, tol)
    assert r.matched == k
    assert r.total_abs_dt_s == pytest.approx(total, abs=1e-6)


def test_invalid_tolerance_and_timestamps_rejected(tmp_path):
    from edge_agent.tools.evaluate import load_agent_jsonl, load_truth
    with pytest.raises(ValueError):
        match_direction([1.0], [1.0], tolerance=float("nan"))
    with pytest.raises(ValueError):
        match_direction([1.0], [1.0], tolerance=-1.0)
    bad = tmp_path / "t.csv"
    bad.write_text("t_seconds,event_type\n-3,enter\n")
    with pytest.raises(ValueError):
        load_truth(bad)
    ev = tmp_path / "e.jsonl"
    ev.write_text('{"frame_index": 10, "event_type": "enter"}\n')
    with pytest.raises(ValueError):
        load_agent_jsonl(ev, fps=0)
