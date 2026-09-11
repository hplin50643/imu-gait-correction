"""Meaningful synthetic checks for mounting, time limits, fusion, and BVH order."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial.transform import Rotation

from imu_to_bvh import (Joint, Sensor, choose_window, continuous_euler,
                        estimate_orientations, initial_sensor_rotation,
                        local_rotations, prepare_gyroscope, read_sensor, regular_grid, write_bvh)
from validate_bvh import forward_kinematics, read_bvh


class ConversionTests(unittest.TestCase):
    def test_gravity_and_forward_mapping(self):
        gravity = np.array([9.81, 0, 0])
        rotation = initial_sensor_rotation(gravity, {"forward_axis": "+z"})
        np.testing.assert_allclose(rotation.apply(gravity), [0, 9.81, 0], atol=1e-10)
        np.testing.assert_allclose(rotation.apply([0, 0, 1]), [0, 0, 1], atol=1e-10)
        with self.assertRaises(ValueError):
            initial_sensor_rotation(gravity, {"forward_axis": "+x"})

    def test_euler_branches_preserve_rotation_across_singularity(self):
        source = np.column_stack([np.linspace(160, 210, 81), np.linspace(70, 110, 81), np.linspace(-30, 15, 81)])
        rotations = Rotation.from_euler("ZXY", source, degrees=True)
        result, _ = continuous_euler(rotations)
        error = (Rotation.from_euler("ZXY", result, degrees=True).inv() * rotations).magnitude()
        self.assertLess(float(error.max()), 1e-10)
        self.assertLess(float(np.max(np.abs(np.diff(result, axis=0)))), 60)

    def test_noncommuting_parent_child_bvh_roundtrip(self):
        joints = [Joint("Hips", -1, np.zeros(3), "root"),
                  Joint("Child", 0, np.array([0., 20, 0]), "child", np.array([0., 10, 0]))]
        root = Rotation.from_euler("xyz", [[35, 20, -40], [-12, 85, 13]], degrees=True)
        child = Rotation.from_euler("xyz", [[-21, 55, 70], [65, -33, -120]], degrees=True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.bvh"
            write_bvh(path, joints, local_rotations(joints, {"root": root, "child": child}), np.array([0., 100, 0]), 60)
            nodes, values, _ = read_bvh(path)
            positions, matrices = forward_kinematics(nodes, values)
            np.testing.assert_allclose(matrices[:, 0], root.as_matrix(), atol=1e-8)
            np.testing.assert_allclose(matrices[:, 1], child.as_matrix(), atol=1e-8)
            expected = np.array([0, 100, 0]) + root.apply([0, 20, 0])
            np.testing.assert_allclose(positions[:, 1], expected, atol=1e-8)

    def test_raw_tail_and_long_gap_are_not_extrapolated(self):
        with tempfile.TemporaryDirectory() as directory:
            t = np.r_[np.arange(301) * .005, 5.0]
            signal = np.zeros((len(t), 6))
            signal[:, 0] = 9.81
            signal[:, 1] = .01 * np.sin(t)
            signal[280:] = [-.2, -1.7, -.4, .005, .025, .01]
            df = pd.DataFrame(signal, columns=["ax", "ay", "az", "gx", "gy", "gz"])
            df.insert(0, "Timestamp", t)
            df["is_calibration"] = np.arange(len(t)) < 201
            path = Path(directory) / "sensor.csv"
            df.to_csv(path, index=False)
            sensor = read_sensor(path, "test", .05, "rad/s", "m/s2")
            self.assertAlmostEqual(sensor.safe_end, 1.395)
            _, end, _, _ = choose_window({"test": sensor}, None, None)
            self.assertAlmostEqual(end, 1.395)
            with self.assertRaises(ValueError):
                choose_window({"test": sensor}, None, 4.0)
            df.loc[20, "Timestamp"] = df.loc[19, "Timestamp"]
            df.to_csv(path, index=False)
            with self.assertRaises(ValueError):
                read_sensor(path, "test", .05, "rad/s", "m/s2")

    def test_known_yaw_from_six_axis_data_and_bias(self):
        t = regular_grid(0, 7, .005)
        cal = t < 5
        r0 = initial_sensor_rotation(np.array([9.81, 0, 0]), {"forward_axis": "+z"})
        rate = .7
        theta = np.maximum(t - 5, 0) * rate
        truth = Rotation.from_euler("Y", theta)
        sensors_to_world = truth * r0
        acc = sensors_to_world.inv().apply(np.tile([0., 9.81, 0], (len(t), 1)))
        gyro = np.tile(r0.inv().apply([0., rate, 0]), (len(t), 1))
        gyro[cal] = 0
        gyro += np.array([.05, -.03, .02])
        sensor = Sensor("synthetic", Path("synthetic.csv"), t, acc, gyro, cal, .005, 7, {})
        for fusion in ["online", "offline"]:
            with self.subTest(fusion=fusion):
                recovered = estimate_orientations(sensor, t, cal, t, {"forward_axis": "+z"}, "calibration", [], fusion=fusion)
                error = np.rad2deg((recovered.inv() * truth).magnitude())
                self.assertLess(float(error.max()), 1.0)
                np.testing.assert_allclose(sensor.details["subtracted_initial_bias_rad_s"], [.05, -.03, .02], atol=1e-12)

    def test_rate_repair_does_not_pair_across_missing_samples(self):
        time = np.arange(500) * .005
        time[70:] += .015  # A short interpolatable gap inside a possible wrap.
        gyro = np.zeros((500, 3))
        gyro[30:60, 0], gyro[60:80, 0], gyro[80:100, 0] = 5.6, -5.6, 5.6
        sensor = Sensor("test", Path("test.csv"), time, np.zeros_like(gyro), gyro,
                        time < .2, .005, time[-1], {})
        prepared, report = prepare_gyroscope(sensor, time, "paired", 11.45)
        np.testing.assert_array_equal(prepared, gyro)
        self.assertEqual(report["accepted_pair_count"], 0)
        self.assertEqual(len(report["continuous_blocks"]), 2)


if __name__ == "__main__":
    unittest.main()
