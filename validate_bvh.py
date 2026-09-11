"""Read a BVH independently, check its structure, and optionally render poses."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import io
import json
from pathlib import Path
import re

import numpy as np


@dataclass
class Node:
    name: str
    parent: int
    offset: np.ndarray
    channels: list[str]
    first_column: int
    end: np.ndarray | None = None


def read_bvh(path: Path) -> tuple[list[Node], np.ndarray, float]:
    hierarchy, motion_text = path.read_text(encoding="ascii").split("MOTION", 1)
    tokens = iter(re.findall(r"[{}]|[^\s{}]+", hierarchy))
    nodes = []
    channel_count = 0

    def expect(expected):
        actual = next(tokens)
        if actual != expected:
            raise ValueError(f"Expected {expected!r}, got {actual!r}")

    def vector():
        return np.array([float(next(tokens)) for _ in range(3)])

    def parse_node(parent):
        nonlocal channel_count
        name = next(tokens)
        expect("{")
        expect("OFFSET")
        offset = vector()
        expect("CHANNELS")
        count = int(next(tokens))
        channels = [next(tokens) for _ in range(count)]
        valid = {f"{axis}{kind}" for axis in "XYZ" for kind in ["rotation", "position"]}
        if not set(channels) <= valid or len(channels) != len(set(channels)):
            raise ValueError(f"Invalid channels on {name}")
        index = len(nodes)
        nodes.append(Node(name, parent, offset, channels, channel_count))
        channel_count += count
        while True:
            token = next(tokens)
            if token == "}":
                return
            if token == "JOINT":
                parse_node(index)
            elif token == "End":
                expect("Site")
                expect("{")
                expect("OFFSET")
                nodes[index].end = vector()
                expect("}")
            else:
                raise ValueError(f"Unexpected hierarchy token: {token}")

    expect("HIERARCHY")
    expect("ROOT")
    parse_node(-1)
    if list(tokens):
        raise ValueError("Unexpected data after root hierarchy")
    if len({node.name for node in nodes}) != len(nodes):
        raise ValueError("Duplicate joint names")
    lines = motion_text.strip().splitlines()
    frame_match = re.fullmatch(r"Frames:\s*(\d+)", lines[0].strip())
    time_match = re.fullmatch(r"Frame Time:\s*([0-9.eE+-]+)", lines[1].strip())
    if not frame_match or not time_match:
        raise ValueError("Missing Frames / Frame Time")
    frames = int(frame_match[1])
    dt = float(time_match[1])
    values = np.loadtxt(io.StringIO("\n".join(lines[2:])), ndmin=2)
    if values.shape != (frames, channel_count) or frames < 1:
        raise ValueError(f"Motion shape {values.shape} != {(frames, channel_count)}")
    if not np.isfinite(values).all() or not np.isfinite(dt) or dt <= 0:
        raise ValueError("Non-finite motion or invalid frame time")
    if not all(np.isfinite(n.offset).all() for n in nodes):
        raise ValueError("Invalid skeleton offsets")
    return nodes, values, dt


def axis_matrix(axis: str, degrees: np.ndarray) -> np.ndarray:
    angle = np.deg2rad(degrees)
    c, s = np.cos(angle), np.sin(angle)
    matrices = np.tile(np.eye(3), (len(angle), 1, 1))
    i, j = {"X": (1, 2), "Y": (2, 0), "Z": (0, 1)}[axis]
    matrices[:, i, i] = c
    matrices[:, j, j] = c
    matrices[:, i, j] = -s
    matrices[:, j, i] = s
    return matrices


def forward_kinematics(nodes: list[Node], values: np.ndarray):
    """Compose explicit axis matrices in declared BVH order; no SciPy dependency."""
    count = len(values)
    positions = np.zeros((count, len(nodes), 3))
    rotations = np.zeros((count, len(nodes), 3, 3))
    for index, node in enumerate(nodes):
        local = np.tile(np.eye(3), (count, 1, 1))
        position = np.tile(node.offset, (count, 1))
        for channel_index, channel in enumerate(node.channels):
            data = values[:, node.first_column + channel_index]
            if channel.endswith("rotation"):
                local = local @ axis_matrix(channel[0], data)
            else:
                position[:, "XYZ".index(channel[0])] += data
        if node.parent < 0:
            positions[:, index] = position
            rotations[:, index] = local
        else:
            parent_rotation = rotations[:, node.parent]
            positions[:, index] = positions[:, node.parent] + np.einsum("nij,nj->ni", parent_rotation, position)
            rotations[:, index] = parent_rotation @ local
    return positions, rotations


def render_preview(path: Path, nodes: list[Node], values: np.ndarray, dt: float,
                   output: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    positions, rotations = forward_kinematics(nodes, values)
    frames = np.linspace(0, len(values) - 1, 6, dtype=int)
    figure = plt.figure(figsize=(15, 9))
    figure.suptitle(f"{path.stem} | fixed root position | N/T calibration pose", fontsize=14)
    floor_size = 110
    for panel, frame in enumerate(frames, start=1):
        ax = figure.add_subplot(2, 3, panel, projection="3d")
        for i, node in enumerate(nodes):
            color = "#1b79b4" if node.name.startswith("Left") else "#cf6828" if node.name.startswith("Right") else "#485464"
            if node.parent >= 0:
                segment = positions[frame, [node.parent, i]]
                ax.plot(segment[:, 0], segment[:, 2], segment[:, 1], color=color, linewidth=2)
            if node.end is not None:
                end = positions[frame, i] + rotations[frame, i] @ node.end
                segment = np.stack([positions[frame, i], end])
                ax.plot(segment[:, 0], segment[:, 2], segment[:, 1], color=color, linewidth=2)
        ax.scatter(positions[frame, :, 0], positions[frame, :, 2], positions[frame, :, 1], s=9, c="#303b49")
        ax.plot([-floor_size, floor_size], [0, 0], [0, 0], color="#bbbbbb", linewidth=.7)
        ax.plot([0, 0], [-floor_size, floor_size], [0, 0], color="#bbbbbb", linewidth=.7)
        ax.set(xlim=(-floor_size, floor_size), ylim=(-floor_size, floor_size), zlim=(-25, 195),
               xlabel="X (cm)", ylabel="Z (cm)", zlabel="Y (cm)", title=f"Elapsed {frame * dt:.2f} s")
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=15, azim=-65)
    figure.text(.5, .015, "Blue: left | Orange: right | Format/geometry preview; physical accuracy has not been validated.",
                ha="center", fontsize=10)
    figure.tight_layout(rect=(0, .035, 1, .96))
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=140)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bvh", type=Path)
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()
    nodes, values, dt = read_bvh(args.bvh)
    positions, rotations = forward_kinematics(nodes, values)
    length_errors = []
    for i, node in enumerate(nodes):
        if node.parent >= 0 and not any(c.endswith("position") for c in node.channels):
            distance = np.linalg.norm(positions[:, i] - positions[:, node.parent], axis=1)
            length_errors.append(float(np.max(np.abs(distance - np.linalg.norm(node.offset)))))
    orthogonality = float(np.max(np.abs(np.swapaxes(rotations, -1, -2) @ rotations - np.eye(3))))
    if max(length_errors, default=0) > 1e-6 or orthogonality > 1e-8:
        raise ValueError("Forward-kinematics validation failed")
    print(json.dumps({"frames": len(values), "channels": values.shape[1], "joints": len(nodes),
                      "fps": 1 / dt, "duration_first_to_last_s": (len(values) - 1) * dt,
                      "root_translation_range_cm": np.ptp(positions[:, 0], axis=0).tolist(),
                      "max_bone_length_error_cm": max(length_errors, default=0),
                      "max_rotation_orthogonality_error": orthogonality}, indent=2))
    if args.preview:
        render_preview(args.bvh, nodes, values, dt, args.preview)


if __name__ == "__main__":
    main()
