import unittest

import numpy as np

from gyro_repair import repair_gyro_wrap


class GyroRepairTests(unittest.TestCase):
    def test_known_wrapped_walking_rate_and_multiple_axes(self):
        dt, period = 0.005, 11.45
        t = np.arange(0, 12, dt)
        truth = np.column_stack([7.2 * np.sin(2 * np.pi * t),
                                 7.8 * np.sin(2 * np.pi * t + 0.3),
                                 2 * np.sin(2 * np.pi * t)])
        wrapped = (truth + period / 2) % period - period / 2
        fixed, diagnostics = repair_gyro_wrap(wrapped, dt, period)
        np.testing.assert_allclose(fixed, truth, atol=1e-12)
        self.assertGreater(diagnostics["accepted_pair_count"], 40)
        self.assertEqual(diagnostics["changed_samples_by_axis"][2], 0)

    def test_below_range_unchanged_and_input_not_mutated(self):
        rng = np.random.default_rng(4)
        gyro = rng.normal(0, 0.1, (2000, 3))
        copy = gyro.copy()
        fixed, diagnostics = repair_gyro_wrap(gyro, 0.005)
        np.testing.assert_array_equal(fixed, gyro)
        np.testing.assert_array_equal(copy, gyro)
        self.assertEqual(diagnostics["accepted_pair_count"], 0)

    def test_isolated_jump_does_not_carry(self):
        gyro = np.zeros((500, 3))
        gyro[30:60, 0], gyro[60:90, 0] = 5.6, -5.6
        fixed, diagnostics = repair_gyro_wrap(gyro, 0.005, 11.45)
        np.testing.assert_array_equal(fixed, gyro)
        self.assertEqual(diagnostics["unresolved_edge_count"], 1)

    def test_long_ambiguous_pair_is_not_repaired(self):
        gyro = np.zeros((600, 3))
        gyro[30:60, 0], gyro[60:300, 0], gyro[300:340, 0] = 5.6, -5.6, 5.6
        fixed, diagnostics = repair_gyro_wrap(gyro, 0.005, 11.45)
        np.testing.assert_array_equal(fixed, gyro)
        self.assertEqual(diagnostics["unresolved_edge_count"], 2)

    def test_low_sample_rate_is_reported_and_left_unchanged(self):
        gyro = np.zeros((50, 3))
        gyro[10:12, 0], gyro[12:14, 0], gyro[14:16, 0] = 5.6, -5.6, 5.6
        fixed, diagnostics = repair_gyro_wrap(gyro, 0.1, 11.45)
        np.testing.assert_array_equal(fixed, gyro)
        self.assertEqual(diagnostics["status"], "unchanged_low_sample_rate")

    def test_default_robust_estimate_tracks_known_period(self):
        dt, period = 0.005, 11.45
        t = np.arange(0, 20, dt)
        truth = 7.2 * np.sin(2 * np.pi * t)
        wrapped = (truth + period / 2) % period - period / 2
        gyro = np.column_stack([wrapped, np.zeros_like(wrapped), np.zeros_like(wrapped)])
        fixed, diagnostics = repair_gyro_wrap(gyro, dt)
        self.assertEqual(diagnostics["period_source"], "robust_local_jump_estimate")
        self.assertAlmostEqual(diagnostics["period_rad_s"], period, delta=0.002)
        np.testing.assert_allclose(fixed[:, 0], truth, atol=0.002)

    def test_repaired_excursion_returns_exactly_to_original_baseline(self):
        gyro = np.zeros((500, 3))
        gyro[30:60, 0], gyro[60:80, 0], gyro[80:100, 0] = 5.6, -5.6, 5.6
        fixed, diagnostics = repair_gyro_wrap(gyro, 0.005, 11.45)
        np.testing.assert_array_equal(fixed[:60], gyro[:60])
        np.testing.assert_array_equal(fixed[80:], gyro[80:])
        self.assertEqual(diagnostics["accepted_pair_count"], 1)

    def test_invalid_input(self):
        for dt in [0, -1, np.nan]:
            with self.assertRaises(ValueError):
                repair_gyro_wrap(np.zeros((10, 3)), dt)
        with self.assertRaises(ValueError):
            repair_gyro_wrap(np.zeros((10, 2)), 0.005)
        with self.assertRaises(ValueError):
            repair_gyro_wrap(np.zeros((10, 3)), 0.005, -1)


if __name__ == "__main__":
    unittest.main()
