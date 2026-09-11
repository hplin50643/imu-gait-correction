import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from walking_heading import stabilize_leg_heading


def heading(rotation):
    x = rotation.apply([1, 0, 0])
    return np.unwrap(np.arctan2(-x[:, 2], x[:, 0]))


class WalkingHeadingTests(unittest.TestCase):
    def setUp(self):
        self.dt = 0.02
        self.time = np.arange(0, 100, self.dt)
        self.calibration = self.time < 5
        self.drift = np.deg2rad(1.3 * np.maximum(self.time - 5, 0))
        self.fast = np.deg2rad(6 * np.sin(2 * np.pi * self.time))
        self.turn = np.deg2rad(100 * np.sin(self.time / 22))
        self.pitch = np.deg2rad(20 * np.sin(2 * np.pi * self.time))
        chest = Rotation.from_euler("Y", self.turn)
        leg = (Rotation.from_euler("Y", self.turn + self.drift + self.fast)
               * Rotation.from_euler("X", self.pitch))
        self.orientations = {"chest": chest, "left_thigh": leg, "left_upper_arm": leg}

    def test_common_time_varying_turn_equivariance(self):
        corrected, _ = stabilize_leg_heading(self.orientations, self.time, self.calibration)
        common = Rotation.from_euler("Y", np.deg2rad(170 * np.sin(self.time / 13)))
        moved = {name: common * rotation for name, rotation in self.orientations.items()}
        moved_corrected, _ = stabilize_leg_heading(moved, self.time, self.calibration)
        error = (moved_corrected["left_thigh"].inv() * common * corrected["left_thigh"]).magnitude()
        self.assertLess(np.max(error), 1e-10)

    def test_high_frequency_yaw_amplitude_preserved_and_slow_drift_reduced(self):
        corrected, _ = stabilize_leg_heading(self.orientations, self.time, self.calibration)
        relative = heading(corrected["left_thigh"]) - heading(corrected["chest"])
        middle = (self.time > 10) & (self.time < 90)
        basis = np.column_stack([np.sin(2 * np.pi * self.time[middle]),
                                 np.cos(2 * np.pi * self.time[middle]),
                                 self.time[middle], np.ones(middle.sum())])
        coefficients = np.linalg.lstsq(basis, relative[middle], rcond=None)[0]
        self.assertGreater(np.hypot(*coefficients[:2]) / np.deg2rad(6), 0.95)
        self.assertLess(abs(np.rad2deg(coefficients[2])), 0.13)

    def test_tilt_is_unchanged_and_unsupported_segments_unchanged(self):
        corrected, report = stabilize_leg_heading(self.orientations, self.time, self.calibration)
        before = self.orientations["left_thigh"].as_matrix()[:, 1, 1]
        after = corrected["left_thigh"].as_matrix()[:, 1, 1]
        np.testing.assert_allclose(after, before, atol=1e-14)
        np.testing.assert_array_equal(corrected["left_upper_arm"].as_quat(), self.orientations["left_upper_arm"].as_quat())
        self.assertEqual(report["segments"]["left_thigh"]["baseline_source"], "reliable_calibration_samples")

    def test_long_invalid_interval_holds_correction_and_recovers_without_jump(self):
        invalid = (self.time >= 30) & (self.time < 40)
        quats = self.orientations["left_thigh"].as_quat()
        corrupt = (Rotation.from_euler("Y", 50 * self.time[invalid])
                   * Rotation.from_euler("X", np.full(invalid.sum(), 110), degrees=True))
        quats[invalid] = corrupt.as_quat()
        source = {**self.orientations, "left_thigh": Rotation.from_quat(quats)}
        corrected, report = stabilize_leg_heading(source, self.time, self.calibration)
        delta = corrected["left_thigh"] * source["left_thigh"].inv()
        correction = heading(delta)
        self.assertTrue(np.isfinite(corrected["left_thigh"].as_quat()).all())
        self.assertLess(np.ptp(correction[invalid]), 1e-12)
        self.assertLessEqual(np.max(np.abs(np.rad2deg(np.diff(correction)))), 45 * self.dt + 1e-8)
        self.assertEqual(len(report["segments"]["left_thigh"]["long_invalid_intervals"]), 1)

    def test_short_invalid_interval_interpolates_and_all_invalid_remains_unchanged(self):
        quats = self.orientations["left_thigh"].as_quat()
        short = (self.time >= 30) & (self.time < 30.2)
        quats[short] = Rotation.from_euler("X", np.full(short.sum(), 100), degrees=True).as_quat()
        bad = Rotation.from_euler("X", np.full(len(self.time), 110), degrees=True)
        source = {**self.orientations, "left_thigh": Rotation.from_quat(quats), "right_foot": bad}
        corrected, report = stabilize_leg_heading(source, self.time, self.calibration)
        self.assertEqual(report["segments"]["left_thigh"]["interpolated_short_gap_count"], 1)
        np.testing.assert_array_equal(corrected["right_foot"].as_quat(), bad.as_quat())

    def test_missing_calibration_is_reported_and_invalid_chest_is_excluded(self):
        corrected, report = stabilize_leg_heading(self.orientations, self.time, np.zeros(len(self.time), dtype=bool))
        self.assertEqual(report["segments"]["left_thigh"]["baseline_source"], "first_reliable_two_seconds_fallback")
        chest = Rotation.from_euler("X", np.full(len(self.time), 30), degrees=True)
        corrected, report = stabilize_leg_heading({**self.orientations, "chest": chest}, self.time, self.calibration)
        self.assertEqual(report["segments"]["left_thigh"]["status"], "unchanged_no_reliable_observations")


if __name__ == "__main__":
    unittest.main()
