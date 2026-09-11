"""Compare exported BVH orientations; these metrics are not ground-truth errors."""
import argparse
import json
from pathlib import Path

import numpy as np

from validate_bvh import read_bvh, forward_kinematics


SUMMARY_JOINTS = ("Hips", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg", "LeftFoot", "RightFoot")


def measurements(path):
    nodes, values, dt = read_bvh(path)
    _, rotations = forward_kinematics(nodes, values)
    time = np.arange(len(values)) * dt
    result = {}
    names = {node.name for node in nodes}
    missing = {"Chest", *SUMMARY_JOINTS} - names
    if missing:
        raise ValueError(f"{path.name}: missing comparison joints: {', '.join(sorted(missing))}")
    chest = next(i for i, node in enumerate(nodes) if node.name == "Chest")
    chest_heading = np.arctan2(-rotations[:, chest, 2, 0], rotations[:, chest, 0, 0])
    for i, node in enumerate(nodes):
        tilt = np.rad2deg(np.arccos(np.clip(rotations[:, i, 1, 1], -1, 1)))
        heading = np.arctan2(-rotations[:, i, 2, 0], rotations[:, i, 0, 0])
        relative = np.rad2deg(np.unwrap(np.angle(np.exp(1j * (heading - chest_heading)))))
        result[node.name] = {"tilt": tilt, "relative_heading": relative}
    return time, result, dt


def build_comparison(before, after, before_label="Before", after_label="After"):
    """Compare matched motion windows without using display labels as data keys."""
    data = {"before": measurements(before), "after": measurements(after)}
    before_time, _, before_dt = data["before"]
    after_time, _, after_dt = data["after"]
    if len(before_time) != len(after_time):
        raise ValueError("Comparison requires equal frame counts and matching motion windows.")
    if not np.isclose(before_dt, after_dt, rtol=0, atol=1e-10):
        raise ValueError("Comparison requires equal frame times; resample to a common time grid first.")
    summary = {
        "meaning": "Tilt is global bone +Y vs vertical, not error relative to measured ground truth.",
        "files": {"before": before.name, "after": after.name},
        "labels": {"before": before_label, "after": after_label},
        "frames": len(before_time),
        "frame_time_s": before_dt,
        "duration_first_to_last_s": float(before_time[-1]),
        "metrics": {},
    }
    for version, (time, values, _) in data.items():
        summary["metrics"][version] = {}
        for name in SUMMARY_JOINTS:
            tilt = values[name]["tilt"]
            summary["metrics"][version][name] = {
                "first_10s_median_tilt_deg": float(np.median(tilt[time < 10])),
                "last_10s_median_tilt_deg": float(np.median(tilt[time > time[-1] - 10])),
            }
    return data, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--before-label", default="Before", help="Display label for the first BVH")
    parser.add_argument("--after-label", default="After", help="Display label for the second BVH")
    parser.add_argument("--output", type=Path, default=Path("outputs/comparison.png"))
    args = parser.parse_args()
    try:
        data, summary = build_comparison(args.before, args.after, args.before_label, args.after_label)
    except ValueError as exc:
        parser.error(str(exc))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    panels = [("Hips", "tilt", "Pelvis inclination"),
              ("RightLeg", "tilt", "Right shank inclination"),
              ("LeftUpLeg", "relative_heading", "Left thigh heading relative to chest")]
    for ax, (name, metric, title) in zip(axes, panels):
        for version, color in [("before", "#d49a00"), ("after", "#127588")]:
            time, values, _ = data[version]
            ax.plot(time, values[name][metric], color=color, alpha=.85, lw=.8,
                    label=summary["labels"][version])
        ax.set(title=title, ylabel="Degrees")
        ax.grid(alpha=.18)
        ax.legend(loc="upper left")
    axes[-1].set_xlabel("Elapsed motion time (s)")
    fig.suptitle("Walking reconstruction: before / after", fontsize=16)
    fig.text(.5, .012, "Pelvis substitution and leg heading use walking assumptions. Lower curves do not prove physical accuracy.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .035, 1, .96))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
