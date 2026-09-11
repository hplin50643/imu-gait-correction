"""Slow relative-heading stabilization under a forward-walking assumption.

This is a motion prior, not an observable magnetic/global heading estimate.
Sustained sideways walking or persistent hip/foot external rotation can be
mistaken for drift. Rotations are corrected only about world +Y; gravity tilt,
measured fast motions, and turns shared with the chest are retained.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d, label
from scipy.spatial.transform import Rotation


LEG_SEGMENTS = (
    "left_thigh", "left_shank", "left_foot",
    "right_thigh", "right_shank", "right_foot",
)
SIGMA_SECONDS = 2.0
SHORT_GAP_SECONDS = 0.5
RECOVERY_SECONDS = 1.0
MAX_CORRECTION_RATE_DEG_S = 45.0


def _runs(mask: np.ndarray):
    labels, count = label(mask)
    for number in range(1, count + 1):
        indices = np.flatnonzero(labels == number)
        yield int(indices[0]), int(indices[-1])


def _heading_and_quality(rotation: Rotation):
    matrix = rotation.as_matrix()
    x_axis = matrix[:, :, 0]
    horizontal = np.hypot(x_axis[:, 0], x_axis[:, 2])
    phase = np.arctan2(-x_axis[:, 2], x_axis[:, 0])
    tilt = np.arccos(np.clip(matrix[:, 1, 1], -1, 1))
    return phase, horizontal, tilt


def stabilize_leg_heading(orientations: dict[str, Rotation], times: np.ndarray,
                          calibration_mask: np.ndarray) -> tuple[dict[str, Rotation], dict]:
    """Suppress slow leg-to-chest yaw drift without altering segment tilt.

    Inputs must share a regular time grid. A reliable calibration interval
    anchors each segment's relative heading. When no such interval is
    available, the first reliable two seconds provide an explicitly reported
    fallback. Invalid observations are excluded before phase unwrapping.
    Only bounded internal gaps <=0.5 s are interpolated. Longer gaps split
    Gaussian smoothing regions; correction is held throughout those gaps
    and eases back over a second when observations return.
    """
    time = np.asarray(times, dtype=float)
    calibration = np.asarray(calibration_mask, dtype=bool)
    if time.ndim != 1 or len(time) < 3 or calibration.shape != time.shape:
        raise ValueError("times and calibration_mask must be matching 1D arrays, length >= 3")
    delta = np.diff(time)
    if not np.isfinite(time).all() or np.any(delta <= 0):
        raise ValueError("times must be finite and strictly increasing")
    dt = float(np.median(delta))
    if not np.allclose(delta, dt, rtol=1e-5, atol=1e-8):
        raise ValueError("heading stabilization requires a regular time grid")
    if "chest" not in orientations:
        raise ValueError("chest orientation is required as the common heading reference")
    if any(len(rotation) != len(time) for rotation in orientations.values()):
        raise ValueError("all orientation arrays must match times")
    output = dict(orientations)
    chest_phase, chest_horizontal, chest_tilt = _heading_and_quality(orientations["chest"])
    chest_ok = (chest_horizontal >= 0.65) & (chest_tilt <= np.deg2rad(25))
    report = {
        "method": "slow_relative_leg_heading_to_chest",
        "gaussian_sigma_seconds": SIGMA_SECONDS,
        "short_gap_seconds": SHORT_GAP_SECONDS,
        "recovery_seconds": RECOVERY_SECONDS,
        "max_correction_rate_deg_s": MAX_CORRECTION_RATE_DEG_S,
        "reference": "chest",
        "assumption": "Forward walking; sustained sideways walking or external rotation may be treated as drift.",
        "segments": {},
    }
    for name in LEG_SEGMENTS:
        if name not in orientations:
            continue
        rotation = orientations[name]
        phase, horizontal, tilt = _heading_and_quality(rotation)
        valid = chest_ok & (horizontal >= 0.65) & (tilt <= np.deg2rad(70))
        relative = np.arctan2(np.sin(phase - chest_phase), np.cos(phase - chest_phase))
        detail = {"valid_observation_fraction": float(valid.mean()), "invalid_intervals": [],
                  "long_invalid_intervals": [], "interpolated_short_gap_count": 0}
        for first, last in _runs(~valid):
            interval = [float(time[first]), float(time[last]), float((last - first + 1) * dt)]
            detail["invalid_intervals"].append(interval)
        if not np.any(valid):
            detail.update({"status": "unchanged_no_reliable_observations", "baseline_source": "unavailable",
                           "max_abs_correction_deg": 0.0, "max_correction_step_deg": 0.0})
            report["segments"][name] = detail
            continue
        # Invalid phase values never participate in unwrap or filtering.
        trend_input = np.full(len(time), np.nan)
        trend_input[valid] = np.unwrap(relative[valid])
        for first, last in _runs(~valid):
            bounded = first > 0 and last < len(time) - 1
            short = (last - first + 1) * dt <= SHORT_GAP_SECONDS + 1e-8
            if bounded and short:
                trend_input[first:last + 1] = np.interp(
                    time[first:last + 1], time[[first - 1, last + 1]], trend_input[[first - 1, last + 1]])
                detail["interpolated_short_gap_count"] += 1
            else:
                detail["long_invalid_intervals"].append(
                    [float(time[first]), float(time[last]), float((last - first + 1) * dt)])
        supported = np.isfinite(trend_input)
        smoothed = np.full(len(time), np.nan)
        for first, last in _runs(supported):
            smoothed[first:last + 1] = gaussian_filter1d(
                trend_input[first:last + 1], sigma=SIGMA_SECONDS / dt,
                mode="nearest", truncate=2.0)
        anchor = valid & calibration
        if np.any(anchor):
            detail["baseline_source"] = "reliable_calibration_samples"
        else:
            first_reliable = int(np.flatnonzero(valid)[0])
            anchor = valid & (time <= time[first_reliable] + 2.0)
            detail["baseline_source"] = "first_reliable_two_seconds_fallback"
        # Use measured reliable calibration phase, rather than future-contaminated
        # smoothed phase, for the initial alignment reference.
        baseline = float(np.median(trend_input[anchor]))
        desired = smoothed - baseline
        correction = np.zeros(len(time))
        previous, recovery_start, held_value = 0.0, None, 0.0
        max_step = np.deg2rad(MAX_CORRECTION_RATE_DEG_S) * dt
        for index in range(len(time)):
            if not supported[index]:
                correction[index] = previous
                recovery_start = None
                continue
            if index > 0 and not supported[index - 1]:
                recovery_start, held_value = float(time[index]), previous
            target = desired[index]
            if recovery_start is not None:
                fraction = min(1.0, (time[index] - recovery_start) / RECOVERY_SECONDS)
                ease = fraction * fraction * (3.0 - 2.0 * fraction)
                target = held_value + ease * (target - held_value)
                if fraction >= 1:
                    recovery_start = None
            previous += float(np.clip(target - previous, -max_step, max_step))
            correction[index] = previous
        output[name] = Rotation.from_euler("Y", -correction) * rotation
        measured_tilt = output[name].as_matrix()[:, 1, 1]
        detail.update({
            "status": "corrected",
            "baseline_relative_heading_deg": float(np.rad2deg(baseline)),
            "max_abs_correction_deg": float(np.max(np.abs(np.rad2deg(correction)))),
            "first_last_correction_deg": np.rad2deg(correction[[0, -1]]).tolist(),
            "max_correction_step_deg": float(np.max(np.abs(np.rad2deg(np.diff(correction))))),
            "max_gravity_tilt_cosine_change": float(np.max(np.abs(measured_tilt - rotation.as_matrix()[:, 1, 1]))),
        })
        report["segments"][name] = detail
    return output, report
