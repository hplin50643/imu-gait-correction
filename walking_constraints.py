"""Conservative, offline pelvis substitution for a predominantly walking trial.

This detects a sustained disagreement supported by independent accelerometer
data. It does not reconstruct a slipped sensor's true pelvis orientation.
The chest supplies an explicitly reported approximation; its measured turning
is retained. All other segment orientations are returned unchanged.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.spatial.transform import Rotation


UP = np.array([0.0, 1.0, 0.0])
REQUIRED = ("pelvis", "chest", "upper_back")


@dataclass(frozen=True)
class PelvisCorrectionSettings:
    """Angles are degrees; durations are seconds. These are walking priors."""

    pelvis_tilt_deg: float = 60.0
    pelvis_torso_difference_deg: float = 45.0
    torso_max_tilt_deg: float = 25.0
    torso_agreement_deg: float = 15.0
    acceleration_pelvis_tilt_deg: float = 50.0
    acceleration_difference_deg: float = 40.0
    minimum_suspect_seconds: float = 2.0
    minimum_recovery_seconds: float = 2.0
    recovery_pelvis_tilt_deg: float = 30.0
    recovery_upright_difference_deg: float = 25.0
    recovery_common_pose_difference_deg: float = 20.0
    active_torso_agreement_deg: float = 20.0
    active_torso_acceleration_agreement_deg: float = 35.0
    maximum_backtrack_seconds: float = 2.0
    backtrack_acceleration_pelvis_tilt_deg: float = 30.0
    backtrack_acceleration_difference_deg: float = 25.0
    blend_seconds: float = 1.5
    alignment_window_seconds: float = 10.0
    alignment_guard_seconds: float = 3.0
    alignment_max_pelvis_tilt_deg: float = 30.0


def _angle(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.rad2deg(np.arccos(np.clip(np.sum(a * b, axis=-1), -1.0, 1.0)))


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    changes = np.diff(np.r_[False, mask, False].astype(int))
    return list(zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)))


def _intervals(mask: np.ndarray, times: np.ndarray, dt: float) -> list[dict]:
    return [{"start_time": float(times[a]), "end_time_inclusive": float(times[b - 1]),
             "samples": int(b - a), "duration_seconds": float(times[b - 1] - times[a] + dt)}
            for a, b in _runs(mask)]


def _heading(rotation: Rotation) -> np.ndarray:
    forward = rotation.apply([0.0, 0.0, 1.0])
    return np.arctan2(forward[:, 0], forward[:, 2])


def _smoothstep(value: np.ndarray) -> np.ndarray:
    value = np.clip(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def correct_pelvis(orientations: dict[str, Rotation], times: np.ndarray,
                   gravity_evidence: dict[str, np.ndarray] | None,
                   *, settings: PelvisCorrectionSettings | None = None
                   ) -> tuple[dict[str, Rotation], dict]:
    """Return corrected orientations and a JSON-serializable audit report.

    ``gravity_evidence`` must contain pelvis/chest/upper_back unit gravity
    vectors in each segment's calibration bone frame, at ``times``. The caller
    obtains these independently from approximately three-second low-pass raw
    acceleration followed by the fixed initial sensor-to-bone rotation.
    Missing evidence disables substitution. This operation is offline: an
    entire sustained interval is identified before its transition is blended.
    """
    cfg = settings or PelvisCorrectionSettings()
    for name, value in asdict(cfg).items():
        if name == "maximum_backtrack_seconds":
            if not np.isfinite(value) or not 0 <= value <= 2:
                raise ValueError("maximum_backtrack_seconds must be between zero and two")
            continue
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    times = np.asarray(times, dtype=float)
    if times.ndim != 1 or len(times) < 2 or not np.isfinite(times).all() or (np.diff(times) <= 0).any():
        raise ValueError("times must contain at least two finite, increasing timestamps")
    count = len(times)
    dt = float(np.median(np.diff(times)))
    result = dict(orientations)
    weights = np.zeros(count)
    report = {
        "method": "walking_pelvis_acceleration_confirmed_torso_substitution",
        "status": "unchanged", "settings": asdict(cfg),
        "reference_sensor": "chest", "confirming_sensor": "upper_back",
        "suspect_intervals": [], "replaced_intervals": [],
        "backtracked_intervals": [],
        "weight_by_frame": weights.tolist(), "max_weight": 0.0,
        "yaw_alignments": [], "replaced_frames": 0,
        "limitations": [
            "Walking-specific heuristic; chest orientation is an approximation of pelvis motion.",
            "Sensor slip and unusual genuine posture cannot be distinguished with certainty.",
            "Chest heading retains measured turning but has no absolute heading reference.",
        ],
    }
    missing = set(REQUIRED) - set(orientations)
    if missing:
        report.update(status="skipped", reason=f"Missing orientations: {sorted(missing)}")
        return result, report
    for name in REQUIRED:
        if len(orientations[name]) != count:
            raise ValueError(f"{name}: orientation count does not match times")
    if gravity_evidence is None or set(REQUIRED) - set(gravity_evidence):
        report.update(status="skipped", reason="Independent raw-acceleration evidence is required")
        return result, report

    gravity = {}
    for name in REQUIRED:
        array = np.asarray(gravity_evidence[name], dtype=float)
        if array.shape != (count, 3):
            raise ValueError(f"{name}: gravity evidence must have shape ({count}, 3)")
        norm = np.linalg.norm(array, axis=1)
        if not np.isfinite(array).all() or (norm < 1e-6).any():
            report.update(status="skipped", reason=f"Invalid independent gravity evidence for {name}")
            return result, report
        gravity[name] = array / norm[:, None]

    # R^-1 * vertical is invariant to an arbitrary left-multiplied world yaw.
    # Thus an individual yaw drift or a real turn cannot alone trigger fallback.
    pose_gravity = {name: orientations[name].inv().apply(UP) for name in REQUIRED}
    tilt = {name: _angle(pose_gravity[name], UP) for name in REQUIRED}
    accel_tilt = {name: _angle(gravity[name], UP) for name in REQUIRED}
    torso_ok = (tilt["chest"] < cfg.torso_max_tilt_deg) & (tilt["upper_back"] < cfg.torso_max_tilt_deg)
    torso_ok &= _angle(pose_gravity["chest"], pose_gravity["upper_back"]) < cfg.torso_agreement_deg
    accel_torso_ok = (accel_tilt["chest"] < cfg.torso_max_tilt_deg) & (accel_tilt["upper_back"] < cfg.torso_max_tilt_deg)
    accel_torso_ok &= _angle(gravity["chest"], gravity["upper_back"]) < cfg.torso_agreement_deg
    suspicious = torso_ok & accel_torso_ok & (tilt["pelvis"] > cfg.pelvis_tilt_deg)
    suspicious &= accel_tilt["pelvis"] > cfg.acceleration_pelvis_tilt_deg
    for name in ("chest", "upper_back"):
        suspicious &= _angle(pose_gravity["pelvis"], pose_gravity[name]) > cfg.pelvis_torso_difference_deg
        suspicious &= _angle(gravity["pelvis"], gravity[name]) > cfg.acceleration_difference_deg
    # Once mounting failure is supported, a brief crossing below an entry
    # threshold is not evidence that the mounting was restored. Keep a latch
    # until both acceleration and fused orientation show sustained recovery.
    # Agreement during a shared bend is also recovery: requiring an upright
    # pelvis alone would otherwise permanently flag a genuine common posture.
    reference_ok = (_angle(pose_gravity["chest"], pose_gravity["upper_back"])
                    < cfg.active_torso_agreement_deg)
    reference_ok &= (_angle(gravity["chest"], gravity["upper_back"])
                     < cfg.active_torso_agreement_deg)
    for name in ("chest", "upper_back"):
        reference_ok &= (_angle(pose_gravity[name], gravity[name])
                         < cfg.active_torso_acceleration_agreement_deg)
    upright_recovery = (tilt["pelvis"] < cfg.recovery_pelvis_tilt_deg)
    upright_recovery &= accel_tilt["pelvis"] < cfg.recovery_pelvis_tilt_deg
    common_pose_recovery = np.ones(count, dtype=bool)
    for name in ("chest", "upper_back"):
        orientation_difference = _angle(pose_gravity["pelvis"], pose_gravity[name])
        acceleration_difference = _angle(gravity["pelvis"], gravity[name])
        upright_recovery &= orientation_difference < cfg.recovery_upright_difference_deg
        upright_recovery &= acceleration_difference < cfg.recovery_upright_difference_deg
        common_pose_recovery &= orientation_difference < cfg.recovery_common_pose_difference_deg
        common_pose_recovery &= acceleration_difference < cfg.recovery_common_pose_difference_deg
    recovered = reference_ok & (upright_recovery | common_pose_recovery)
    confirmed = np.zeros(count, dtype=bool)
    entry_start = recovery_start = None
    active = False
    recovery_confirmations = []
    for i in range(count):
        if not active:
            entry_start = (i if entry_start is None else entry_start) if suspicious[i] else None
            if entry_start is not None and times[i] - times[entry_start] + dt >= cfg.minimum_suspect_seconds - 1e-8:
                active = True
                confirmed[entry_start:i + 1] = True
                recovery_start = None
        else:
            confirmed[i] = True
            recovery_start = (i if recovery_start is None else recovery_start) if recovered[i] else None
            if recovery_start is not None and times[i] - times[recovery_start] + dt >= cfg.minimum_recovery_seconds - 1e-8:
                recovery_confirmations.append({"evidence_start_time": float(times[recovery_start]),
                                               "confirmed_time": float(times[i])})
                active = False
                entry_start = recovery_start = None

    # A confirmed fault may have started while the causal orientation filter
    # was still catching up. Only extend backward through continuous independent
    # raw-acceleration corroboration, with two healthy torso references, and
    # never more than two seconds. A transient with no confirmed fault does
    # not activate this path. The acceleration mean itself is acausal.
    strict_fault_intervals = _intervals(confirmed, times, dt)
    corroboration = torso_ok & accel_torso_ok & reference_ok
    corroboration &= accel_tilt["pelvis"] > cfg.backtrack_acceleration_pelvis_tilt_deg
    for name in ("chest", "upper_back"):
        corroboration &= (_angle(gravity["pelvis"], gravity[name])
                          > cfg.backtrack_acceleration_difference_deg)
    extended = confirmed.copy()
    for a, b in _runs(confirmed):
        j = a
        while (j > 0 and times[a] - times[j - 1] <= cfg.maximum_backtrack_seconds + 1e-8
               and corroboration[j - 1] and not extended[j - 1]):
            j -= 1
        if j < a:
            extended[j:a] = True
            report["backtracked_intervals"].append({
                "start_time": float(times[j]), "end_time_inclusive": float(times[a - 1]),
                "confirmed_fault_start_time": float(times[a]),
                "backtracked_seconds": float(times[a] - times[j]), "samples": int(a - j),
                "source_orientation_tilt_deg": float(tilt["pelvis"][j]),
                "source_independent_acceleration_tilt_deg": float(accel_tilt["pelvis"][j]),
                "reason": "Continuous independent acceleration corroboration immediately before a confirmed fault; bounded offline extension",
            })
    confirmed = extended

    # The torso may bend while the pelvis is faulty, but it must still agree
    # with the second torso sensor and independent raw acceleration. As this is
    # offline processing, fade out *before* an unreliable-reference interval;
    # never apply a newly invalid chest orientation even during the transition.
    reference_weights = np.ones(count)
    for a, b in _runs(~reference_ok):
        reference_weights[a:b] = 0.0
        before = (times < times[a]) & (times > times[a] - cfg.blend_seconds)
        reference_weights[before] = np.minimum(reference_weights[before],
            _smoothstep((times[a] - times[before]) / cfg.blend_seconds))
        if b < count:
            after = (times >= times[b]) & (times < times[b] + cfg.blend_seconds)
            reference_weights[after] = np.minimum(reference_weights[after],
                _smoothstep((times[after] - times[b]) / cfg.blend_seconds))
    report["candidate_intervals"] = _intervals(suspicious, times, dt)
    report["confirmed_fault_intervals_before_backtracking"] = strict_fault_intervals
    report["suspect_intervals"] = _intervals(confirmed, times, dt)
    report["recovery_confirmations"] = recovery_confirmations
    report["reference_unavailable_intervals"] = _intervals(confirmed & ~reference_ok, times, dt)
    report["hysteresis"] = "Confirmed faults remain active until sustained raw-acceleration and orientation recovery; shared normal bends can recover."
    report["pelvis_tilt_max_before_deg"] = float(np.max(tilt["pelvis"]))
    report["independent_pelvis_tilt_max_deg"] = float(np.max(accel_tilt["pelvis"]))
    if not confirmed.any():
        report["reason"] = "No sustained pelvis disagreement confirmed by both torso sensors and raw acceleration"
        return result, report

    healthy = torso_ok & accel_torso_ok
    healthy &= (tilt["pelvis"] < cfg.alignment_max_pelvis_tilt_deg)
    healthy &= (accel_tilt["pelvis"] < cfg.alignment_max_pelvis_tilt_deg)
    original = orientations["pelvis"]
    chest = orientations["chest"]
    heading_difference = _heading(original) - _heading(chest)
    output_quaternions = original.as_quat().copy()
    for a, b in _runs(confirmed):
        # Only evidence before the fault is allowed to align the reference yaw.
        # A constant alignment follows the chest's turns throughout the fault.
        latest = times[a] - cfg.alignment_guard_seconds
        alignment_mask = healthy & (times <= latest) & (times >= latest - cfg.alignment_window_seconds)
        if not alignment_mask.any():
            alignment_mask = healthy & (times < times[a])
        if alignment_mask.any():
            phase = heading_difference[alignment_mask]
            center = np.angle(np.mean(np.exp(1j * phase)))
            residual = np.angle(np.exp(1j * (phase - center)))
            delta = float(center + np.median(residual))
            alignment_source = "healthy_pre_fault_samples"
        else:
            delta = 0.0
            alignment_source = "shared_identity_calibration_assumption_no_healthy_samples"
        report["yaw_alignments"].append({
            "suspect_start_time": float(times[a]), "constant_heading_offset_deg": float(np.rad2deg(delta)),
            "source": alignment_source, "healthy_samples": int(alignment_mask.sum()),
        })
        current_times = times[a:b]
        entry_weight = _smoothstep((current_times - times[a]) / cfg.blend_seconds)
        current_weights = entry_weight.copy()
        target = Rotation.from_euler("Y", delta) * chest[a:b]
        # Stop consuming the faulty pelvis immediately after the fault onset.
        # Blending every new faulty sample can reintroduce its rapid spin and
        # can jump when its relative shortest quaternion path crosses 180 deg.
        # A fixed chest-relative offset gives exactly the original orientation
        # at entry and then follows chest turning while that offset decays.
        entry_offset = (target[0].inv() * original[a]).as_rotvec()
        blended = target * Rotation.from_rotvec((1.0 - entry_weight)[:, None] * entry_offset)
        # A finite fault interval ends only after sustained confirmed recovery.
        # Its last blend_seconds lie within that recovery evidence when the
        # default recovery duration exceeds blend_seconds. Follow the recovered
        # pelvis with a fixed offset instead of recomputing a shortest path.
        if b < count:
            exit_duration = min(cfg.blend_seconds, cfg.minimum_recovery_seconds)
            exit_weight = _smoothstep((current_times - times[b - 1] + exit_duration) / exit_duration)
            exit_indices = np.flatnonzero(current_times >= times[b - 1] - exit_duration)
            e = int(exit_indices[0])
            exit_offset = (original[a + e].inv() * blended[e]).as_rotvec()
            exit_blended = original[a + e:b] * Rotation.from_rotvec(
                (1.0 - exit_weight[e:])[:, None] * exit_offset)
            quaternions = blended.as_quat()
            quaternions[e:] = exit_blended.as_quat()
            blended = Rotation.from_quat(quaternions)
            current_weights[e:] = current_weights[e] * (1.0 - exit_weight[e:])
        availability = reference_weights[a:b]
        if np.any(availability < 1):
            difference = (original[a:b].inv() * blended).as_rotvec()
            blended = original[a:b] * Rotation.from_rotvec(difference * availability[:, None])
        current_weights *= availability
        weights[a:b] = current_weights
        output_quaternions[a:b] = blended.as_quat()
    corrected = Rotation.from_quat(output_quaternions)
    result["pelvis"] = corrected
    replaced = weights > 1e-8
    report.update({
        "status": "substituted", "reason": "Persistent pelvis tilt disagreement supported by independent raw acceleration",
        "transition_method": "Fixed pelvis-to-chest offset at fault entry; fixed recovered-pelvis offset at exit. Faulty pelvis spin is not reused during entry.",
        "weight_definition": "Progress toward the torso approximation, reduced during confirmed recovery and reference unavailability; entry uses a fixed source offset.",
        "weight_by_frame": weights.tolist(), "max_weight": float(weights.max()),
        "replaced_frames": int(replaced.sum()), "replaced_intervals": _intervals(replaced, times, dt),
        "pelvis_tilt_max_after_deg": float(np.max(_angle(corrected.inv().apply(UP), UP))),
        "max_output_frame_step_deg": float(np.rad2deg(np.max((corrected[:-1].inv() * corrected[1:]).magnitude()))),
    })
    return result, report
