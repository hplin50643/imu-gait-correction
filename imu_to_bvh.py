"""Six-axis IMU to BVH with auditable walking corrections. See README.md."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.metadata
import json
from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.spatial.transform import Rotation, Slerp
from scipy.ndimage import uniform_filter1d
from vqf import VQF, offlineVQF

from gyro_repair import repair_gyro_wrap
from walking_constraints import correct_pelvis


BASE = Path(__file__).resolve().parent
SENSORS = (
    "pelvis", "upper_back", "chest", "head",
    "left_upper_arm", "left_forearm", "right_upper_arm", "right_forearm",
    "left_thigh", "left_shank", "left_foot",
    "right_thigh", "right_shank", "right_foot",
)
AXES = ["ax", "ay", "az", "gx", "gy", "gz"]
ORDER = "ZXY"  # Intrinsic rotations; file CHANNELS use the same order.


@dataclass
class Sensor:
    name: str
    path: Path
    time: np.ndarray
    acceleration: np.ndarray
    gyroscope: np.ndarray
    calibration: np.ndarray
    dt: float
    safe_end: float
    details: dict


@dataclass
class Joint:
    name: str
    parent: int
    offset: np.ndarray
    sensor: str | None = None
    end: np.ndarray | None = None


def read_sensor(path: Path, name: str, max_gap: float,
                gyro_unit: str, accel_unit: str) -> Sensor:
    df = pd.read_csv(path)
    required = ["Timestamp", *AXES, "is_calibration"]
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}")
    if len(df) < 3:
        raise ValueError(f"{path.name}: too few samples")
    time = pd.to_numeric(df.Timestamp, errors="raise").to_numpy(dtype=float)
    values = df[AXES].apply(pd.to_numeric, errors="raise").to_numpy(dtype=float)
    if not np.isfinite(time).all() or not np.isfinite(values).all():
        raise ValueError(f"{path.name}: non-finite timestamps or measurements")
    delta = np.diff(time)
    if (delta <= 0).any():
        raise ValueError(f"{path.name}: timestamps must be strictly increasing")
    dt = float(np.median(delta))
    if max_gap < dt * 1.01:
        raise ValueError("--max-gap must exceed the normal sample interval")
    flags = df.is_calibration.astype(str).str.lower().str.strip()
    if not flags.isin(["true", "false", "1", "0"]).all():
        raise ValueError(f"{path.name}: invalid is_calibration values")
    calibration = flags.isin(["true", "1"]).to_numpy()
    count = int(calibration.sum())
    if count < 2 or count == len(df) or not calibration[:count].all() or calibration[count:].any():
        raise ValueError(f"{path.name}: requires one leading calibration block and subsequent motion")
    if time[count - 1] - time[0] < 0.5:
        raise ValueError(f"{path.name}: at least 0.5 seconds of calibration required")

    # Exactly repeated six-axis tail values are a data-quality heuristic, not a
    # stillness detector. Never remove genuine rest merely for having low variance.
    different = np.flatnonzero(np.any(values != values[-1], axis=1))
    tail_start = int(different[-1] + 1) if len(different) else 0
    tail_count = len(df) - tail_start
    limits = []
    if tail_count >= max(10, int(np.ceil(0.05 / dt))):
        if tail_start <= count:
            raise ValueError(f"{path.name}: no usable motion before constant tail")
        limits.append((float(time[tail_start - 1]), "exactly repeated six-axis tail"))
    long_gaps = np.flatnonzero(delta > max_gap + 1e-9)
    if len(long_gaps):
        first_gap = int(long_gaps[0])
        if first_gap < count:
            raise ValueError(f"{path.name}: long gap inside calibration")
        limits.append((float(time[first_gap]), "first gap exceeding --max-gap"))
    safe_end, reason = min(limits + [(float(time[-1]), "file end")])
    acceleration = values[:, :3] * (9.80665 if accel_unit == "g" else 1.0)
    gyroscope = values[:, 3:] * (np.pi / 180.0 if gyro_unit == "deg/s" else 1.0)
    details = {
        "path": str(path.resolve()), "rows": len(df),
        "first_timestamp": float(time[0]), "last_timestamp": float(time[-1]),
        "sample_rate_hz": 1.0 / dt,
        "calibration_rows": count, "calibration_end": float(time[count - 1]),
        "safe_end": safe_end, "safe_end_reason": reason,
        "exact_tail_rows": tail_count,
        "exact_tail_start": float(time[tail_start]),
        "long_gaps": [[float(time[i]), float(time[i + 1])] for i in long_gaps],
    }
    return Sensor(name, path, time, acceleration, gyroscope,
                  calibration, dt, safe_end, details)


def regular_grid(start: float, end: float, step: float) -> np.ndarray:
    if not np.isfinite([start, end, step]).all() or step <= 0 or end < start:
        raise ValueError("Invalid time range or frame/sample interval")
    return start + np.arange(int(np.floor((end - start) / step + 1e-8)) + 1) * step


def choose_window(sensors: dict[str, Sensor], start: float | None,
                  end: float | None) -> tuple[float, float, np.ndarray, np.ndarray]:
    dt = float(np.median([s.dt for s in sensors.values()]))
    if any(not np.isclose(s.dt, dt, rtol=1e-5, atol=1e-8) for s in sensors.values()):
        raise ValueError("Sensor sample rates differ; resample explicitly before conversion")
    first = max(float(s.time[0]) for s in sensors.values())
    calibration_end = min(float(s.time[s.calibration][-1]) for s in sensors.values())
    if calibration_end - first < 0.5:
        raise ValueError("No common calibration interval of at least 0.5 seconds")
    motion_start = max(float(s.time[np.flatnonzero(~s.calibration)[0]]) for s in sensors.values())
    safe_end = min(s.safe_end for s in sensors.values())
    start = motion_start if start is None else start
    end = safe_end if end is None else end
    if not np.isfinite([start, end]).all() or start < motion_start - 1e-8:
        raise ValueError(f"--start must be at least {motion_start:.6f}")
    if end > safe_end + 1e-8:
        limiting = [s.name for s in sensors.values() if np.isclose(s.safe_end, safe_end)]
        raise ValueError(f"Requested end exceeds safe common end {safe_end:.6f} ({', '.join(limiting)})")
    grid = regular_grid(first, end, dt)
    calibration_mask = grid <= calibration_end + 1e-8
    if end <= start or grid[-1] < start:
        raise ValueError("No motion remains in the selected interval")
    return float(start), float(grid[-1]), grid, calibration_mask


def load_mounting(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    mounts = config.get("sensors", {})
    unknown = set(mounts) - set(SENSORS)
    if unknown:
        raise ValueError(f"Unknown sensors in mounting config: {sorted(unknown)}")
    return mounts


def initial_sensor_rotation(acceleration: np.ndarray, mount: dict) -> Rotation:
    """Sensor-to-BVH-world at calibration; +Y up, +Z forward, +X left."""
    permitted = {"forward_axis", "heading_deg", "reference_sensor_to_world_wxyz"}
    if set(mount) - permitted:
        raise ValueError(f"Unknown mounting settings: {sorted(set(mount) - permitted)}")
    if "reference_sensor_to_world_wxyz" in mount:
        q = np.asarray(mount["reference_sensor_to_world_wxyz"], dtype=float)
        if q.shape != (4,) or not np.isfinite(q).all() or not np.isclose(np.linalg.norm(q), 1, atol=1e-4):
            raise ValueError("reference_sensor_to_world_wxyz must be a unit quaternion [w,x,y,z]")
        return Rotation.from_quat(q[[1, 2, 3, 0]])
    norm = np.linalg.norm(acceleration)
    if norm < 1e-3:
        raise ValueError("Calibration acceleration cannot define gravity")
    up = acceleration / norm
    label = mount.get("forward_axis", "+z").lower()
    if label not in ["+x", "-x", "+y", "-y", "+z", "-z"]:
        raise ValueError(f"Invalid forward_axis: {label}")
    forward = np.eye(3)["xyz".index(label[1])] * (1 if label[0] == "+" else -1)
    forward -= np.dot(forward, up) * up
    if np.linalg.norm(forward) < 0.05:
        raise ValueError("Chosen forward axis is parallel to gravity; edit mounting config")
    forward /= np.linalg.norm(forward)
    left = np.cross(up, forward)
    basis = Rotation.from_matrix(np.stack([left, up, forward]))
    heading = float(mount.get("heading_deg", 0))
    if not np.isfinite(heading):
        raise ValueError("heading_deg must be finite")
    return Rotation.from_euler("Y", heading, degrees=True) * basis


def prepare_gyroscope(sensor: Sensor, grid: np.ndarray, mode: str,
                      period: float | None = None) -> tuple[np.ndarray, dict]:
    """Repair original samples before interpolation; never pair across gaps."""
    if mode not in ("paired", "none"):
        raise ValueError("gyro repair must be paired or none")
    stop = min(len(sensor.time), int(np.searchsorted(sensor.time, grid[-1])) + 1)
    times = sensor.time[:stop]
    values = sensor.gyroscope[:stop].copy()
    report = {"mode": mode, "accepted_pair_count": 0, "changed_samples": 0,
              "unresolved_edge_count": 0, "continuous_blocks": []}
    if mode == "paired":
        edges = np.r_[0, np.flatnonzero(np.diff(times) > sensor.dt * 1.5) + 1, stop]
        for a, b in zip(edges[:-1], edges[1:]):
            if b - a < 3:
                continue
            values[a:b], detail = repair_gyro_wrap(values[a:b], sensor.dt, period)
            for event in detail["accepted_intervals"]:
                event["first_timestamp"] = float(times[a + event["first_sample"]])
                event["last_timestamp"] = float(times[a + event["last_sample"]])
            detail.update(first_timestamp=float(times[a]), last_timestamp=float(times[b - 1]),
                          first_original_row=int(a))
            report["continuous_blocks"].append(detail)
            report["accepted_pair_count"] += detail["accepted_pair_count"]
            report["unresolved_edge_count"] += detail["unresolved_edge_count"]
        report["changed_samples"] = int(np.count_nonzero(np.any(values != sensor.gyroscope[:stop], axis=1)))
    result = np.ascontiguousarray(np.column_stack([
        np.interp(grid, times, values[:, i]) for i in range(3)]))
    return result, report


def raw_gravity_evidence(sensor: Sensor, grid: np.ndarray, calibration_mask: np.ndarray,
                         mount: dict) -> np.ndarray:
    """Independent three-second acceleration mean in the initial bone frame."""
    acc = np.column_stack([np.interp(grid, sensor.time, sensor.acceleration[:, i]) for i in range(3)])
    r0 = initial_sensor_rotation(acc[calibration_mask].mean(axis=0), mount)
    width = max(1, int(round(3.0 / (grid[1] - grid[0]))))
    return r0.apply(uniform_filter1d(acc, size=width, axis=0, mode="nearest"))


def orientation_summary(rotation: Rotation, times: np.ndarray, motion_start: float) -> dict:
    tilt = np.rad2deg(np.arccos(np.clip(rotation.as_matrix()[:, 1, 1], -1, 1)))
    early = (times >= motion_start) & (times < motion_start + 10)
    late = (times >= max(motion_start, times[-1] - 10))
    return {"first_10s_median_tilt_deg": float(np.median(tilt[early])),
            "last_10s_median_tilt_deg": float(np.median(tilt[late])),
            "max_tilt_deg": float(tilt[times >= motion_start].max())}


def estimate_orientations(sensor: Sensor, grid: np.ndarray, calibration_mask: np.ndarray,
                          output_times: np.ndarray, mount: dict, initial_bias: str,
                          messages: list[str], *, gyro_repair: str = "none",
                          wrap_period: float | None = None, fusion: str = "online",
                          tau_acc: float = 3.0) -> Rotation:
    acc = np.ascontiguousarray(np.column_stack([
        np.interp(grid, sensor.time, sensor.acceleration[:, i]) for i in range(3)]))
    gyro, repair_report = prepare_gyroscope(sensor, grid, gyro_repair, wrap_period)
    cal_acc, cal_gyro = acc[calibration_mask], gyro[calibration_mask]
    mean_gyro = cal_gyro.mean(axis=0)
    bias = mean_gyro if initial_bias == "calibration" else np.zeros(3)
    if np.linalg.norm(mean_gyro) > np.deg2rad(5):
        messages.append(f"{sensor.name}: calibration mean angular-rate vector is "
                        f"{np.rad2deg(np.linalg.norm(mean_gyro)):.2f} deg/s; "
                        "verify stillness, units and bias before trusting motion")
    corrected = np.ascontiguousarray(gyro - bias)
    dt = float(grid[1] - grid[0])
    if not np.isfinite(tau_acc) or tau_acc <= 0:
        raise ValueError("tau_acc must be finite and positive")
    if fusion == "offline":
        result = offlineVQF(corrected, acc, None, dt, {"tauAcc": tau_acc})
    elif fusion == "online":
        result = VQF(dt, tauAcc=tau_acc).updateBatch(corrected, acc)
    else:
        raise ValueError("fusion must be online or offline")
    q_wxyz = result["quat6D"]
    if not np.isfinite(q_wxyz).all():
        raise ValueError(f"{sensor.name}: orientation estimation produced non-finite values")
    estimated = Rotation.from_quat(q_wxyz[:, [1, 2, 3, 0]])
    # Use the final calibration second, after the filter has had time to settle.
    ref_mask = calibration_mask & (grid >= grid[calibration_mask][-1] - 1.0)
    reference = estimated[ref_mask].mean()
    r0 = initial_sensor_rotation(cal_acc.mean(axis=0), mount)
    sampled = Slerp(grid, estimated)(output_times)
    # r0 maps the initial sensor axes into BVH world. Right multiplication by
    # r0^-1 applies the fixed sensor-to-bone mounting correction. In the assumed
    # calibration pose every BVH joint has identity rotation; offsets define pose.
    bones = r0 * reference.inv() * sampled * r0.inv()
    calibration_bones = r0 * reference.inv() * estimated[ref_mask] * r0.inv()
    sensor.details.update({
        "gyro_repair": repair_report,
        "fusion": {"method": fusion, "tau_acc_seconds": tau_acc},
        "mounting_assumption": mount,
        "calibration_mean_acceleration_m_s2": cal_acc.mean(axis=0).tolist(),
        "calibration_acceleration_std_m_s2": cal_acc.std(axis=0).tolist(),
        "calibration_mean_gyroscope_rad_s": mean_gyro.tolist(),
        "subtracted_initial_bias_rad_s": bias.tolist(),
        "final_vqf_residual_bias_rad_s": result["bias"][-1].tolist(),
        "calibration_reference_deviation_p95_deg": float(np.quantile(
            np.rad2deg(calibration_bones.magnitude()), 0.95)),
        "short_gaps_in_fusion_window": int(np.sum(
            (np.diff(sensor.time) > sensor.dt * 1.5) &
            (sensor.time[1:] <= grid[-1] + 1e-8) & (sensor.time[:-1] >= grid[0]))),
    })
    return bones


def make_skeleton(height_cm: float, pose: str) -> tuple[list[Joint], np.ndarray]:
    joints: list[Joint] = []

    def add(name, parent, offset, sensor=None, end=None):
        index = len(joints)
        joints.append(Joint(name, parent, np.array(offset, dtype=float), sensor,
                            None if end is None else np.array(end, dtype=float)))
        return index

    hips = add("Hips", -1, [0, 0, 0], "pelvis")
    spine = add("Spine", hips, [0, .10, 0], "upper_back")
    chest = add("Chest", spine, [0, .12, 0], "chest")
    neck = add("Neck", chest, [0, .08, 0])
    add("Head", neck, [0, .05, 0], "head", [0, .08, 0])
    for side, sign in [("Left", 1), ("Right", -1)]:
        lower = side.lower()
        shoulder = add(f"{side}Shoulder", chest, [sign * .08, .035, 0])
        arm = add(f"{side}Arm", shoulder, [sign * .025, 0, 0], f"{lower}_upper_arm")
        direction = np.array([sign, 0, 0]) if pose == "t" else np.array([0, -1, 0])
        forearm = add(f"{side}ForeArm", arm, direction * .18, f"{lower}_forearm")
        add(f"{side}Hand", forearm, direction * .15, end=direction * .055)
    for side, sign in [("Left", 1), ("Right", -1)]:
        lower = side.lower()
        thigh = add(f"{side}UpLeg", hips, [sign * .055, -.025, 0], f"{lower}_thigh")
        shank = add(f"{side}Leg", thigh, [0, -.245, 0], f"{lower}_shank")
        foot = add(f"{side}Foot", shank, [0, -.245, 0], f"{lower}_foot")
        add(f"{side}ToeBase", foot, [0, -.035, .095], end=[0, 0, .04])
    rest = []
    extrema = []
    for joint in joints:
        p = joint.offset + (rest[joint.parent] if joint.parent >= 0 else 0)
        rest.append(p)
        extrema.append(p[1])
        if joint.end is not None:
            extrema.append((p + joint.end)[1])
    scale = height_cm / (max(extrema) - min(extrema))
    for joint in joints:
        joint.offset *= scale
        if joint.end is not None:
            joint.end *= scale
    root_position = np.array([0, -min(extrema) * scale, 0])
    return joints, root_position


def local_rotations(joints: list[Joint], orientations: dict[str, Rotation]) -> list[Rotation]:
    global_rotations = []
    local = []
    for joint in joints:
        parent = global_rotations[joint.parent] if joint.parent >= 0 else None
        current = orientations[joint.sensor] if joint.sensor else parent
        if current is None:
            raise ValueError("Root joint needs a sensor")
        global_rotations.append(current)
        local.append(parent.inv() * current if parent is not None else current)
    return local


def continuous_euler(rotations: Rotation) -> tuple[np.ndarray, int]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        angles = rotations.as_euler(ORDER, degrees=True)
    # A Tait-Bryan rotation has two equivalent Euler branches. Select the branch
    # nearest the previous frame, then unwrap full turns. Frame orientations stay exact.
    for i in range(1, len(angles)):
        a, b, c = angles[i]
        candidates = np.array([[a, b, c], [a + 180, 180 - b, c + 180]])
        candidates += 360 * np.round((angles[i - 1] - candidates) / 360)
        angles[i] = candidates[np.argmin(np.sum((candidates - angles[i - 1]) ** 2, axis=1))]
    return angles, sum("Gimbal lock" in str(w.message) for w in caught)


def write_bvh(path: Path, joints: list[Joint], rotations: list[Rotation],
              root_position: np.ndarray, fps: float) -> dict:
    children = {i: [] for i in range(len(joints))}
    for i, joint in enumerate(joints):
        if joint.parent >= 0:
            children[joint.parent].append(i)
    lines = ["HIERARCHY"]
    order = []

    def vec(value):
        return " ".join(f"{x:.8f}" for x in value)

    def emit(index, depth):
        joint = joints[index]
        order.append(index)
        tab = "\t" * depth
        lines.extend([f"{tab}{'ROOT' if joint.parent < 0 else 'JOINT'} {joint.name}", f"{tab}{{",
                      f"{tab}\tOFFSET {vec(joint.offset)}"])
        rotation_channels = " ".join(f"{axis}rotation" for axis in ORDER)
        channels = f"6 Xposition Yposition Zposition {rotation_channels}" if joint.parent < 0 else f"3 {rotation_channels}"
        lines.append(f"{tab}\tCHANNELS {channels}")
        for child in children[index]:
            emit(child, depth + 1)
        if not children[index]:
            if joint.end is None:
                raise ValueError(f"Leaf joint {joint.name} requires End Site")
            lines.extend([f"{tab}\tEnd Site", f"{tab}\t{{", f"{tab}\t\tOFFSET {vec(joint.end)}", f"{tab}\t}}"])
        lines.append(f"{tab}}}")

    emit(0, 0)
    frame_count = len(rotations[0])
    blocks = [np.tile(root_position, (frame_count, 1))]
    errors, jumps, gimbal_warnings = [], {}, 0
    for index in order:
        angles, count = continuous_euler(rotations[index])
        angles = np.round(angles, 8)
        restored = Rotation.from_euler(ORDER, angles, degrees=True)
        errors.append(float(np.max((restored.inv() * rotations[index]).magnitude())))
        jumps[joints[index].name] = float(np.max(np.abs(np.diff(angles, axis=0))))
        gimbal_warnings += count
        blocks.append(angles)
    motion = np.column_stack(blocks)
    if not np.isfinite(motion).all() or max(errors) > 1e-6:
        raise ValueError("BVH rotation round-trip verification failed")
    lines.extend(["MOTION", f"Frames: {frame_count}", f"Frame Time: {1 / fps:.12f}"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as output:
        output.write("\n".join(lines) + "\n")
        np.savetxt(output, motion, fmt="%.8f")
    return {"frames": frame_count, "channels": motion.shape[1], "joints": len(joints),
            "euler_order_intrinsic": ORDER, "gimbal_lock_warning_batches": gimbal_warnings,
            "max_rotation_roundtrip_error_rad": max(errors),
            "max_euler_component_step_deg_by_joint": jumps}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--input-dir", type=Path, default=BASE / "data" / "Edward_field1_raw")
    parser.add_argument("--trial", default="Edward_field1", help="CSV filename prefix")
    parser.add_argument("--output", type=Path, default=BASE / "outputs" / "Edward_field1_v3.bvh")
    parser.add_argument("--mounting", type=Path, default=BASE / "mounting.json")
    parser.add_argument("--fps", type=float, default=60)
    parser.add_argument("--height-cm", type=float, default=175)
    parser.add_argument("--pose", choices=["n", "t"], default="n", help="Assumed calibration pose: n=arms down, t=arms horizontal")
    parser.add_argument("--start", type=float, help="Original timestamp; default is end of calibration")
    parser.add_argument("--end", type=float, help="Original timestamp; default is earliest usable sensor end")
    parser.add_argument("--max-gap", type=float, default=.05, help="Maximum gap to interpolate, in seconds")
    parser.add_argument("--gyro-unit", choices=["rad/s", "deg/s"], default="rad/s")
    parser.add_argument("--accel-unit", choices=["m/s2", "g"], default="m/s2")
    parser.add_argument("--initial-bias", choices=["calibration", "none"], default="calibration",
                        help="Subtract calibration gyro mean (assumes rest); VQF also estimates residual bias")
    parser.add_argument("--gyro-repair", choices=["paired", "none"], default="paired",
                        help="Locally repair supported paired rate-wrap events before fusion")
    parser.add_argument("--gyro-wrap-period", type=float, help="Override empirical wrap period, in rad/s")
    parser.add_argument("--fusion", choices=["auto", "online", "offline"], default="auto",
                        help="auto: online pelvis to isolate later faults; offline VQF for other sensors")
    parser.add_argument("--foot-tau-acc", type=float, default=.5,
                        help="Foot gravity-correction time constant, seconds; other sensors use 3 s")
    parser.add_argument("--walking-correction", choices=["full", "pelvis", "none"], default="full",
                        help="full: pelvis fault substitution and slow leg heading correction; pelvis: substitution only")
    args = parser.parse_args(argv)
    for name in ["fps", "height_cm", "max_gap", "foot_tau_acc"]:
        if not np.isfinite(getattr(args, name)) or getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be finite and positive")
    if args.gyro_wrap_period is not None and (not np.isfinite(args.gyro_wrap_period) or args.gyro_wrap_period <= 0):
        parser.error("--gyro-wrap-period must be finite and positive")
    if args.output.suffix.lower() != ".bvh":
        parser.error("--output must end in .bvh")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    messages = [
        "Experimental reconstruction: sensor units and physical synchronization are assumed, not independently verified.",
        f"Calibration pose assumed: {'standing, arms down' if args.pose == 'n' else 'T-pose'}; sensor headings use mounting.json assumptions.",
        "Six-axis orientation has no absolute heading reference; relative heading drift remains possible.",
        "Root translation is fixed. Standard body proportions are assumed; wrists and toes inherit parent orientation.",
        "upper_back and chest drive two serial torso joints; this mapping is an approximation.",
    ]
    sensors = {name: read_sensor(args.input_dir / f"{args.trial}_{name}.csv", name,
                                args.max_gap, args.gyro_unit, args.accel_unit) for name in SENSORS}
    start, end, grid, cal_mask = choose_window(sensors, args.start, args.end)
    output_times = regular_grid(start, end, 1 / args.fps)
    if len(output_times) < 2:
        raise ValueError("At least two output frames are required")
    mounts = load_mounting(args.mounting)
    for name in SENSORS:
        mounts.setdefault(name, {"forward_axis": "+x" if name.endswith("foot") else "+z", "heading_deg": 0})
    print(f"Fusion: {1 / (grid[1] - grid[0]):.3f} Hz; output: {len(output_times)} frames at {args.fps:g} fps")
    print(f"Motion timestamps: {output_times[0]:.6f} to {output_times[-1]:.6f}; usable input ends at {end:.6f}")
    orientations = {}
    for name, sensor in sensors.items():
        print(f"  Estimating {name} ...", flush=True)
        fusion = ("online" if name == "pelvis" else "offline") if args.fusion == "auto" else args.fusion
        orientations[name] = estimate_orientations(
            sensor, grid, cal_mask, grid, mounts[name], args.initial_bias, messages,
            gyro_repair=args.gyro_repair, wrap_period=args.gyro_wrap_period, fusion=fusion,
            tau_acc=args.foot_tau_acc if name.endswith("foot") else 3.0)
    # Correct on the original grid including calibration, then resample. A --start
    # crop must not redefine the gait baseline or forget an earlier pelvis fault.
    motion_start = max(float(s.time[np.flatnonzero(~s.calibration)[0]]) for s in sensors.values())
    before = {name: orientation_summary(r, grid, motion_start) for name, r in orientations.items()}
    correction_report = {"mode": args.walking_correction}
    if args.walking_correction in ("full", "pelvis"):
        evidence = {name: raw_gravity_evidence(sensors[name], grid, cal_mask, mounts[name])
                    for name in ("pelvis", "chest", "upper_back")}
        orientations, correction_report["pelvis"] = correct_pelvis(orientations, grid, evidence)
        if correction_report["pelvis"]["status"] == "substituted":
            messages.append("Sustained pelvis disagreement was replaced with a torso-based approximation; see correction intervals in report.")
    if args.walking_correction == "full":
        from walking_heading import stabilize_leg_heading
        orientations, correction_report["leg_heading"] = stabilize_leg_heading(orientations, grid, cal_mask)
        messages.append("Slow leg heading relative to chest is regularized under a walking assumption; sustained sideways walking or hip rotation can be suppressed.")
    after = {name: orientation_summary(r, grid, motion_start) for name, r in orientations.items()}
    orientations = {name: Slerp(grid, r)(output_times) for name, r in orientations.items()}
    joints, root_position = make_skeleton(args.height_cm, args.pose)
    verification = write_bvh(args.output, joints, local_rotations(joints, orientations), root_position, args.fps)
    report = {
        "output": str(args.output.resolve()), "python": sys.executable,
        "versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scipy", "vqf"]},
        "source_units_assumed": {"time": "s", "acceleration": args.accel_unit, "gyroscope": args.gyro_unit},
        "calibration_time_range": [float(grid[cal_mask][0]), float(grid[cal_mask][-1])],
        "usable_motion_time_range": [start, end],
        "exported_motion_time_range": [float(output_times[0]), float(output_times[-1])],
        "fps": args.fps, "height_cm": args.height_cm, "calibration_pose": args.pose,
        "bvh_axes": "+Y up, +Z forward, +X character left", "bvh_length_unit": "cm",
        "fixed_root_position_cm": root_position.tolist(), "initial_bias": args.initial_bias,
        "max_interpolated_gap_seconds": args.max_gap,
        "processing_time_range": [float(grid[0]), float(grid[-1])],
        "gyro_repair_mode": args.gyro_repair, "fusion_mode": args.fusion,
        "walking_corrections": correction_report,
        "orientation_diagnostics": {"definition": "Global bone +Y tilt from world +Y; not an error against ground truth.",
                                    "before_walking_constraints": before, "after_walking_constraints": after},
        "warnings": messages, "verification": verification,
        "skeleton": [{"name": j.name, "parent": joints[j.parent].name if j.parent >= 0 else None,
                      "sensor": j.sensor, "offset_cm": j.offset.tolist()} for j in joints],
        "sensors": {name: sensor.details for name, sensor in sensors.items()},
    }
    report_path = args.output.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(f"BVH: {args.output.resolve()}")
    print(f"Report: {report_path.resolve()}")
    for message in messages:
        print(f"NOTE: {message}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
