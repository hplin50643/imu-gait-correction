"""Conservative repair of short, paired angular-rate wrap excursions.

The Edward data has repeated jumps from approximately +5.7 to -5.7 rad/s
and back. This is evidence of rate-value wrap, not proof of a particular
device encoding. The fallback period below is an empirical data assumption.
No cumulative unwrapping is performed: ambiguous or unpaired events remain
unchanged, and every accepted repair returns exactly to the original series.
"""
from __future__ import annotations

import numpy as np


EMPIRICAL_PERIOD_RAD_S = 11.45
MAX_PAIR_SECONDS = 0.5
MIN_SAMPLE_RATE_HZ = 50.0


def _candidate_edges(values: np.ndarray, period: float) -> np.ndarray:
    delta = np.diff(values)
    return np.flatnonzero(
        (np.abs(delta) > 0.70 * period)
        & (values[:-1] * values[1:] < 0)
        & (np.minimum(np.abs(values[:-1]), np.abs(values[1:])) > 0.35 * period)
    )


def _estimate_period(gyro: np.ndarray) -> tuple[float, dict]:
    """Estimate jump height after subtracting the local physical rate slope."""
    estimates = []
    for values in gyro.T:
        delta = np.diff(values)
        edges = _candidate_edges(values, EMPIRICAL_PERIOD_RAD_S)
        edges = edges[(edges > 0) & (edges < len(delta) - 1)]
        if not len(edges):
            continue
        before, after = delta[edges - 1], delta[edges + 1]
        valid = ((np.abs(before) < 0.6) & (np.abs(after) < 0.6)
                 & (np.abs(before) > 0.005) & (np.abs(after) > 0.005)
                 & (before * after > 0))
        estimates.extend(np.abs(delta[edges[valid]]
                                - (before[valid] + after[valid]) / 2).tolist())
    candidates = np.asarray(estimates)
    candidates = candidates[(candidates > 10.5) & (candidates < 12.0)]
    metadata = {"estimation_samples": len(candidates), "fallback_period_rad_s": EMPIRICAL_PERIOD_RAD_S}
    if len(candidates) >= 12:
        q25, median, q75 = np.quantile(candidates, [0.25, 0.5, 0.75])
        metadata["estimated_period_iqr_rad_s"] = [float(q25), float(q75)]
        if q75 - q25 <= 0.25:
            return float(median), {**metadata, "period_source": "robust_local_jump_estimate"}
    return EMPIRICAL_PERIOD_RAD_S, {**metadata, "period_source": "empirical_Edward_data_fallback"}


def repair_gyro_wrap(gyro: np.ndarray, dt: float, period: float | None = None
                     ) -> tuple[np.ndarray, dict]:
    """Repair isolated, paired wrap intervals in an N x 3 rad/s series.

    Only adjacent candidate edges of opposite sign, at most 0.5 s apart,
    are eligible. The correction must substantially reduce both boundary
    jumps, remain plausible in magnitude, and need no correction outside
    those two edges. Samples at less than 50 Hz are left unchanged because
    boundary continuity is less informative at those sample rates.

    ``period`` overrides the inferred full wrap span (not the half range).
    Diagnostics distinguish accepted intervals from unresolved candidates.
    These checks cannot recover information destroyed by clipping, missing
    samples, or arbitrary corruption, nor estimate IMU heading or bias.
    """
    original = np.asarray(gyro, dtype=float)
    if original.ndim != 2 or original.shape[1] != 3 or len(original) < 3:
        raise ValueError("gyro must be a finite N x 3 array with N >= 3")
    if not np.isfinite(original).all() or not np.isfinite(dt) or dt <= 0:
        raise ValueError("gyro and dt must be finite and dt must be positive")
    if period is not None and (not np.isfinite(period) or period <= 0):
        raise ValueError("period must be finite and positive")
    if period is None:
        span, details = _estimate_period(original)
    else:
        span, details = float(period), {"period_source": "manual_override", "estimation_samples": 0}
    repaired = original.copy()
    report = {
        "method": "paired_local_rate_wrap_repair",
        "period_rad_s": span,
        **details,
        "max_pair_seconds": MAX_PAIR_SECONDS,
        "accepted_intervals": [],
        "accepted_pair_count": 0,
        "candidate_edges_by_axis": [],
        "unresolved_edges_by_axis": [],
        "unresolved_edge_count": 0,
        "changed_samples_by_axis": [0, 0, 0],
        "assumption": "Angular-rate wrap is inferred from this dataset; the device encoding is unverified.",
    }
    if 1.0 / dt < MIN_SAMPLE_RATE_HZ - 1e-8:
        for values in original.T:
            edges = _candidate_edges(values, span).tolist()
            report["candidate_edges_by_axis"].append(len(edges))
            report["unresolved_edges_by_axis"].append(edges)
        report["unresolved_edge_count"] = sum(report["candidate_edges_by_axis"])
        report["status"] = "unchanged_low_sample_rate"
        return repaired, report
    max_samples = max(1, int(np.floor(MAX_PAIR_SECONDS / dt + 1e-8)))
    # Rate changes larger than this at an edge are ambiguous even after adding
    # a wrap period. At 200 Hz this permits up to 1.5 rad/s per sample.
    max_boundary_change = min(0.20 * span, max(1.5, 300.0 * dt))
    for axis in range(3):
        values = original[:, axis]
        delta = np.diff(values)
        edges = _candidate_edges(values, span)
        report["candidate_edges_by_axis"].append(int(len(edges)))
        used = set()
        i = 0
        while i < len(edges) - 1:
            first, last = map(int, edges[i:i + 2])
            opposite = delta[first] * delta[last] < 0
            correction = -float(np.sign(delta[first])) * span
            start_jump, end_jump = delta[first] + correction, delta[last] - correction
            boundary_ok = (max(abs(start_jump), abs(end_jump)) <= max_boundary_change
                           and abs(start_jump) < 0.25 * abs(delta[first])
                           and abs(end_jump) < 0.25 * abs(delta[last]))
            interval = values[first + 1:last + 1] + correction
            magnitude_ok = (np.max(np.abs(interval)) <= 1.35 * span)
            if opposite and last - first <= max_samples and boundary_ok and magnitude_ok:
                repaired[first + 1:last + 1, axis] = interval
                used.update((first, last))
                report["accepted_intervals"].append({
                    "axis": "xyz"[axis], "first_sample": first + 1,
                    "last_sample": last, "duration_s": (last - first) * dt,
                    "added_rate_rad_s": correction,
                    "max_repaired_boundary_jump_rad_s": max(abs(start_jump), abs(end_jump)),
                })
                i += 2
            else:
                i += 1
        report["unresolved_edges_by_axis"].append([int(edge) for edge in edges if int(edge) not in used])
        report["changed_samples_by_axis"][axis] = int(np.count_nonzero(repaired[:, axis] != values))
    report["accepted_pair_count"] = len(report["accepted_intervals"])
    report["unresolved_edge_count"] = sum(map(len, report["unresolved_edges_by_axis"]))
    report["status"] = "repaired" if report["accepted_pair_count"] else "unchanged_no_confident_pair"
    return repaired, report
