"""Synthetic HRV generator for Alion development.

Until the Polar H10 arrives (2026-05-16), this stands in for real
RR-interval data. Produces a realistic boxing-session HRV trace:
- Rest baseline ~70 bpm with high RMSSD (~50 ms)
- Rounds drive HR up exponentially toward ~170 bpm with low RMSSD
- Rest periods recover toward a fatigue-adjusted baseline

Output is the same CSV shape `parse_rr_csv` already accepts:
    t_ms,rr_ms

Usage:
    python -m scripts.synth.hrv --rounds 3 --round-s 180 --rest-s 60 \
        --out data/raw/hrv/synthetic.csv
"""

from __future__ import annotations

import argparse
import math
import random
from pathlib import Path


def _hr_target(elapsed_s: float, *, rounds: int, round_s: int, rest_s: int,
               hr_rest: float, hr_peak: float, fatigue_drift: float = 5.0) -> float:
    """Piecewise HR target: ramps up during rounds, drops during rest."""
    seg = round_s + rest_s
    cycle_idx = int(elapsed_s // seg)
    in_seg = elapsed_s - cycle_idx * seg
    fatigue = min(fatigue_drift, fatigue_drift * cycle_idx / max(rounds, 1))
    if in_seg < round_s:
        # Round: exponential rise toward (hr_peak + fatigue)
        tau = 30.0  # 30s rise time-constant
        target = (hr_peak + fatigue) - (hr_peak + fatigue - hr_rest) * math.exp(-in_seg / tau)
    else:
        # Rest: exponential decay toward (hr_rest + fatigue)
        rest_in = in_seg - round_s
        tau = 25.0
        peak_at_round_end = (hr_peak + fatigue) - (hr_peak + fatigue - hr_rest) * math.exp(-round_s / tau)
        target = (hr_rest + fatigue) + (peak_at_round_end - (hr_rest + fatigue)) * math.exp(-rest_in / tau)
    return target


def generate(*, rounds: int, round_s: int, rest_s: int,
             hr_rest: float = 70.0, hr_peak: float = 170.0,
             rmssd_rest_ms: float = 50.0, rmssd_peak_ms: float = 6.0,
             seed: int | None = None) -> list[tuple[float, float]]:
    rng = random.Random(seed)
    total_s = rounds * round_s + max(0, rounds - 1) * rest_s
    samples: list[tuple[float, float]] = []
    t_ms = 0.0
    while t_ms / 1000.0 < total_s:
        elapsed_s = t_ms / 1000.0
        hr = _hr_target(
            elapsed_s, rounds=rounds, round_s=round_s, rest_s=rest_s,
            hr_rest=hr_rest, hr_peak=hr_peak,
        )
        # RMSSD shrinks as HR rises (linear interpolation between rest/peak)
        f = max(0.0, min(1.0, (hr - hr_rest) / max(hr_peak - hr_rest, 1e-3)))
        sigma_rr = (1.0 - f) * rmssd_rest_ms + f * rmssd_peak_ms
        # RR = 60000 / HR plus Gaussian jitter scaled by sigma
        rr = 60000.0 / hr + rng.gauss(0.0, sigma_rr * 0.5)
        rr = max(300.0, min(1500.0, rr))  # clip to physiological range
        t_ms += rr
        samples.append((t_ms, rr))
    return samples


def write_csv(samples: list[tuple[float, float]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        f.write("t_ms,rr_ms\n")
        for t, rr in samples:
            f.write(f"{t:.1f},{rr:.1f}\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--round-s", type=int, default=180)
    ap.add_argument("--rest-s", type=int, default=60)
    ap.add_argument("--hr-rest", type=float, default=70.0)
    ap.add_argument("--hr-peak", type=float, default=170.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    samples = generate(
        rounds=args.rounds, round_s=args.round_s, rest_s=args.rest_s,
        hr_rest=args.hr_rest, hr_peak=args.hr_peak, seed=args.seed,
    )
    write_csv(samples, args.out)
    print(f"wrote {len(samples)} RR samples to {args.out}")


if __name__ == "__main__":
    main()
