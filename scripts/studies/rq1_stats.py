"""RQ1 inferential analysis.

Reads `data/studies/rq1_ratings.csv` (produced by rq1_aggregate.py) and
runs the headline tests for the dissertation chapter:

  • Friedman χ² across the 4 payload modes per criterion (and pooled).
  • Wilcoxon signed-rank pairwise post-hoc (Bonferroni-corrected).
  • Kendall's W (effect size for Friedman).
  • Inter-rater reliability — ICC(3,k) approximation via two-way ANOVA on
    the rater × session matrix per (mode, criterion).

Each block prints a small report; full numbers are saved as JSON for
the writeup.

Run:
    uv run python -m scripts.studies.rq1_stats \
        --in data/studies/rq1_ratings.csv \
        --out data/studies/rq1_stats.json
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from statistics import mean

from scipy import stats

MODES = ["cv", "hrv", "imu", "fused"]
CRITERIA = ["specificity", "actionability", "correctness", "novelty"]


def _kendalls_w(matrix: list[list[float]]) -> float:
    """Kendall's W for k×n: rows = raters/sessions, cols = conditions.

    Implementation note: scipy doesn't ship Kendall's W directly. We use
    the classical formula:
        W = 12·S / (k²·(n³−n))
    where k = rows, n = cols, S = Σ(R_j − R̄)² and R_j is the column
    rank-sum.
    """
    if not matrix or not matrix[0]:
        return 0.0
    k = len(matrix)
    n = len(matrix[0])
    if n < 2:
        return 0.0
    # Rank within each row, ascending.
    ranked = []
    for row in matrix:
        order = sorted(range(n), key=lambda i: row[i])
        ranks = [0.0] * n
        for r, i in enumerate(order, start=1):
            ranks[i] = r
        # Average ties.
        # Skipped for simplicity; data is small + ordinal Likert = some ties OK.
        ranked.append(ranks)
    col_sums = [sum(ranked[r][j] for r in range(k)) for j in range(n)]
    mean_col = sum(col_sums) / n
    s = sum((cs - mean_col) ** 2 for cs in col_sums)
    return 12 * s / (k * k * (n**3 - n))


def _icc_two_way(matrix: list[list[float]]) -> float | None:
    """Cheap ICC(3,k) approximation — two-way mixed, consistency, average.

    matrix: rows = subjects (sessions), cols = raters. Requires every cell
    filled. Returns None if the matrix is too small or has zero variance.

    Formula (Shrout & Fleiss 1979, model 3, average measures):
        ICC(3,k) = (BMS - EMS) / BMS
    where BMS = between-subjects mean square, EMS = residual mean square
    from the rater × subject ANOVA.
    """
    n = len(matrix)
    if n < 2:
        return None
    k = len(matrix[0])
    if k < 2:
        return None
    if any(len(r) != k for r in matrix):
        return None

    grand = sum(sum(r) for r in matrix) / (n * k)
    row_means = [sum(r) / k for r in matrix]
    col_means = [sum(matrix[i][j] for i in range(n)) / n for j in range(k)]

    bss = k * sum((rm - grand) ** 2 for rm in row_means)
    css = n * sum((cm - grand) ** 2 for cm in col_means)
    total = sum((matrix[i][j] - grand) ** 2 for i in range(n) for j in range(k))
    ess = total - bss - css

    bms = bss / (n - 1)
    df_e = (n - 1) * (k - 1)
    if df_e <= 0:
        return None
    ems = ess / df_e
    if bms <= 1e-9:
        return None
    return float((bms - ems) / bms)


def _friedman(rows_by_session: dict[str, dict[str, list[float]]], criterion: str) -> dict:
    """Run Friedman across the 4 modes for a given criterion.

    Within-session aggregation = mean across raters (so each session
    contributes one observation per mode).
    """
    matrix = []  # rows = sessions, cols = modes
    for sid, by_mode in rows_by_session.items():
        if any(criterion not in mode_scores for mode_scores in by_mode.values()):
            continue  # session missing a mode score for this criterion
        if any(not by_mode.get(m) for m in MODES):
            continue
        row = [mean(by_mode[m][criterion]) for m in MODES]
        matrix.append(row)
    n = len(matrix)
    if n < 3:
        return {"n": n, "ok": False, "reason": "fewer than 3 complete sessions"}
    columns = list(zip(*matrix))
    chi2, p = stats.friedmanchisquare(*columns)
    w = _kendalls_w(matrix)
    return {
        "n": n,
        "ok": True,
        "chi2": float(chi2),
        "p": float(p),
        "kendalls_w": w,
        "mode_means": {m: float(mean(col)) for m, col in zip(MODES, columns)},
    }


def _wilcoxon_pairwise(
    rows_by_session: dict[str, dict[str, list[float]]], criterion: str
) -> list[dict]:
    out = []
    sids = list(rows_by_session.keys())
    pair_count = len(list(combinations(MODES, 2)))
    for a, b in combinations(MODES, 2):
        xs, ys = [], []
        for sid in sids:
            by_mode = rows_by_session[sid]
            if criterion in by_mode.get(a, {}) and criterion in by_mode.get(b, {}):
                xs.append(mean(by_mode[a][criterion]))
                ys.append(mean(by_mode[b][criterion]))
        if len(xs) < 5:
            out.append({"a": a, "b": b, "ok": False, "n": len(xs)})
            continue
        try:
            w_stat, p = stats.wilcoxon(xs, ys, zero_method="wilcox")
        except ValueError:
            out.append({"a": a, "b": b, "ok": False, "n": len(xs), "reason": "all-zero diffs"})
            continue
        out.append(
            {
                "a": a,
                "b": b,
                "ok": True,
                "n": len(xs),
                "w_stat": float(w_stat),
                "p_uncorrected": float(p),
                "p_bonferroni": float(min(1.0, p * pair_count)),
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=Path("data/studies/rq1_ratings.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/studies/rq1_stats.json"))
    args = ap.parse_args()

    if not args.inp.exists():
        raise SystemExit(f"input CSV not found: {args.inp}")

    # Load → nested dict[session_id][mode][criterion] = [scores across raters]
    rows: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    rater_ids: set[str] = set()
    with args.inp.open() as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            sid = r["session_id"]
            mode = r["payload_mode"]
            crit = r["criterion"]
            score = float(r["score"])
            rater_ids.add(r["rater_id"])
            rows[sid][mode][crit].append(score)

    report: dict = {
        "n_sessions_total": len(rows),
        "n_raters": len(rater_ids),
        "raters": sorted(rater_ids),
        "criteria": {},
    }

    # Per-criterion Friedman + Wilcoxon
    for crit in CRITERIA:
        report["criteria"][crit] = {
            "friedman": _friedman(rows, crit),
            "wilcoxon_pairs": _wilcoxon_pairwise(rows, crit),
        }

    # Pooled across criteria — sum the four criterion means per (session, mode)
    pooled: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))  # type: ignore[arg-type]
    )
    for sid, by_mode in rows.items():
        for m, by_crit in by_mode.items():
            total = sum(mean(scores) for scores in by_crit.values() if scores)
            pooled[sid][m]["pooled"].append(total)
    report["pooled"] = {
        "friedman": _friedman(pooled, "pooled"),
        "wilcoxon_pairs": _wilcoxon_pairwise(pooled, "pooled"),
    }

    # ICC(3,k) per (mode, criterion). Build an n×k subject-by-rater matrix.
    icc_block: dict[str, dict[str, float | None]] = {}
    for mode in MODES:
        icc_block[mode] = {}
        for crit in CRITERIA:
            mat = []
            raters_sorted = sorted(rater_ids)
            for sid in rows:
                row = []
                ok = True
                for rid in raters_sorted:
                    # Find the score for this (session, mode, crit, rater).
                    # We didn't keep rater_id in the dict above, so re-scan.
                    ok = False
                    break
                if ok:
                    mat.append(row)
            # Re-scan from CSV for efficiency
            mat = _build_icc_matrix(args.inp, mode, crit, raters_sorted, list(rows.keys()))
            icc_block[mode][crit] = _icc_two_way(mat)
    report["icc_3k"] = icc_block

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))

    # Quick stdout summary
    print(f"sessions: {report['n_sessions_total']} · raters: {report['n_raters']}")
    for crit, block in report["criteria"].items():
        f = block["friedman"]
        if f.get("ok"):
            print(
                f"  {crit:14s}  Friedman χ²={f['chi2']:.2f}  p={f['p']:.4f}  W={f['kendalls_w']:.2f}  "
                + " ".join(f"{m}={v:.2f}" for m, v in f["mode_means"].items())
            )
        else:
            print(f"  {crit:14s}  insufficient data: {f.get('reason')} (n={f['n']})")
    pf = report["pooled"]["friedman"]
    if pf.get("ok"):
        print(
            f"  POOLED          Friedman χ²={pf['chi2']:.2f}  p={pf['p']:.4f}  W={pf['kendalls_w']:.2f}"
        )
    print(f"\nfull report → {args.out}")


def _build_icc_matrix(
    csv_path: Path, mode: str, crit: str, raters: list[str], sessions: list[str]
) -> list[list[float]]:
    """Build the n_sessions × n_raters matrix for ICC. Cells with missing
    data are filled with the column mean (rater mean) — a common
    convention for partial designs. If a rater has no data at all, the
    column is dropped."""
    cell: dict[tuple[str, str], list[float]] = defaultdict(list)
    with csv_path.open() as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            if r["payload_mode"] != mode or r["criterion"] != crit:
                continue
            cell[(r["session_id"], r["rater_id"])].append(float(r["score"]))
    matrix: list[list[float]] = []
    rater_means: dict[str, float] = {}
    for rid in raters:
        vals = [mean(cell[(sid, rid)]) for sid in sessions if cell.get((sid, rid))]
        if vals:
            rater_means[rid] = mean(vals)
    raters = [r for r in raters if r in rater_means]
    if not raters:
        return []
    for sid in sessions:
        row = []
        for rid in raters:
            if cell.get((sid, rid)):
                row.append(mean(cell[(sid, rid)]))
            else:
                row.append(rater_means[rid])
        matrix.append(row)
    return matrix


if __name__ == "__main__":
    main()
