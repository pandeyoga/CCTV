"""Compare agent events with a manually tallied ground truth. Never estimates; reports only what matches.

Ground truth CSV (header required): `t_seconds,event_type` — seconds from video start (frame 0), enter|exit.
Agent events: JSONL from `edge_agent.tools.annotate --events` (uses frame_index / fps) or a SQLite store.

  python -m edge_agent.tools.evaluate --truth truth.csv --events events.jsonl --fps 10 [--tolerance 2.0] [--json report.json]

Matching (per direction, one-to-one, each event used at most once):
  1. maximise the number of pairs with |t_truth - t_agent| <= tolerance (inclusive),
  2. among those, minimise the total absolute time difference,
  3. ties are broken deterministically by sorted input order.
Solved exactly with the Hungarian algorithm on a padded square cost matrix where infeasible pairs cost
BIG = (n + m + 1) * tolerance + 1 (> any feasible total), so rule 1 dominates rule 2. Complexity O(k^3),
k = max(n, m); fine for pilot sessions (hundreds of events per direction), not for whole-month logs.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class TimedEvent:
    t: float
    event_type: str


@dataclass
class DirectionReport:
    truth: int
    agent: int
    matched: int
    false_positive: int
    missed: int
    count_error: int  # agent - truth (signed)
    total_abs_dt_s: float = 0.0

    @property
    def precision(self) -> float | None:
        return self.matched / self.agent if self.agent else None

    @property
    def recall(self) -> float | None:
        return self.matched / self.truth if self.truth else None


def _check_time(t: float, what: str) -> float:
    if not math.isfinite(t) or t < 0:
        raise ValueError(f"invalid {what} timestamp: {t!r} (must be finite and >= 0 seconds)")
    return t


def load_truth(path: str | Path) -> list[TimedEvent]:
    out: list[TimedEvent] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            et = row["event_type"].strip().lower()
            if et not in ("enter", "exit"):
                raise ValueError(f"bad event_type in truth: {et!r}")
            out.append(TimedEvent(_check_time(float(row["t_seconds"]), "truth"), et))
    return out


def load_agent_jsonl(path: str | Path, fps: float) -> list[TimedEvent]:
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("fps must be a finite number > 0")
    out: list[TimedEvent] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                d = json.loads(line)
                if d["event_type"] not in ("enter", "exit"):
                    raise ValueError(f"bad event_type in agent events: {d['event_type']!r}")
                out.append(TimedEvent(_check_time(d["frame_index"] / fps, "agent"), d["event_type"]))
    return out


def _hungarian(cost: list[list[float]]) -> list[int]:
    """Min-cost assignment for a square matrix; returns col assigned to each row. O(n^3), deterministic."""
    n = len(cost)
    INF = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    p = [0] * (n + 1)  # p[j] = row assigned to column j (1-based), 0 = free
    way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta, j1 = INF, 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    assignment = [-1] * n
    for j in range(1, n + 1):
        if p[j]:
            assignment[p[j] - 1] = j - 1
    return assignment


def optimal_pairs(truth: list[float], agent: list[float], tolerance: float) -> list[tuple[int, int]]:
    """Indices (into the *sorted* inputs) of matched pairs: max cardinality, then min total |dt|."""
    n, m = len(truth), len(agent)
    if n == 0 or m == 0:
        return []
    k = max(n, m)
    big = (n + m + 1) * tolerance + 1.0
    cost = [[big] * k for _ in range(k)]
    for i, t in enumerate(truth):
        for j, a in enumerate(agent):
            d = abs(a - t)
            if d <= tolerance:
                cost[i][j] = d
    assignment = _hungarian(cost)
    return [(i, j) for i, j in enumerate(assignment) if i < n and 0 <= j < m and cost[i][j] < big]


def match_direction(truth: list[float], agent: list[float], tolerance: float) -> DirectionReport:
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be a finite number >= 0")
    truth_s, agent_s = sorted(truth), sorted(agent)
    pairs = optimal_pairs(truth_s, agent_s, tolerance)
    matched = len(pairs)
    return DirectionReport(truth=len(truth_s), agent=len(agent_s), matched=matched,
                           false_positive=len(agent_s) - matched, missed=len(truth_s) - matched,
                           count_error=len(agent_s) - len(truth_s),
                           total_abs_dt_s=round(sum(abs(agent_s[j] - truth_s[i]) for i, j in pairs), 6))


def evaluate(truth: list[TimedEvent], agent: list[TimedEvent], tolerance: float) -> dict:
    report: dict = {"tolerance_seconds": tolerance, "directions": {}}
    for et in ("enter", "exit"):
        r = match_direction([e.t for e in truth if e.event_type == et], [e.t for e in agent if e.event_type == et], tolerance)
        report["directions"][et] = {**asdict(r), "precision": r.precision, "recall": r.recall}
    report["total_truth"] = len(truth)
    report["total_agent"] = len(agent)
    return report


def render_markdown(report: dict) -> str:
    lines = [f"| direction | truth | agent | matched | false+ | missed | count error | precision | recall |",
             "|---|---|---|---|---|---|---|---|---|"]
    for et, r in report["directions"].items():
        pr = "n/a" if r["precision"] is None else f"{r['precision']:.2f}"
        rc = "n/a" if r["recall"] is None else f"{r['recall']:.2f}"
        lines.append(f"| {et} | {r['truth']} | {r['agent']} | {r['matched']} | {r['false_positive']} | {r['missed']} | {r['count_error']:+d} | {pr} | {rc} |")
    lines.append(f"\nTolerance ±{report['tolerance_seconds']}s. Ground truth events: {report['total_truth']}, agent events: {report['total_agent']}.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="edge_agent.tools.evaluate")
    p.add_argument("--truth", required=True)
    p.add_argument("--events", required=True, help="agent events JSONL")
    p.add_argument("--fps", type=float, required=True, help="source video fps (frame_index -> seconds)")
    p.add_argument("--tolerance", type=float, default=2.0)
    p.add_argument("--json", default=None)
    args = p.parse_args(argv)
    if not math.isfinite(args.tolerance) or args.tolerance < 0:
        p.error("--tolerance must be a finite number >= 0")
    report = evaluate(load_truth(args.truth), load_agent_jsonl(args.events, args.fps), args.tolerance)
    print(render_markdown(report))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
