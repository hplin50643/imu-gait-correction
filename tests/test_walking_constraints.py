"""Behavioral tests for conservative walking pelvis substitution."""
import json
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from walking_constraints import correct_pelvis, PelvisCorrectionSettings


class PelvisCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.times = np.arange(0.0, 20.0, 1 / 60)
        self.n = len(self.times)

    def rotation(self, axis, degrees):
        return Rotation.from_euler(axis, np.broadcast_to(degrees, self.n), degrees=True)

    def data(self, pelvis=None, chest=None, back=None):
        zero = self.rotation("Y", 0)
        orientations = {"pelvis": pelvis if pelvis is not None else zero,
                        "chest": chest if chest is not None else zero,
                        "upper_back": back if back is not None else zero,
                        "left_foot": self.rotation("X", 17)}
        gravity = {name: value.inv().apply([0, 1, 0]) for name, value in orientations.items()}
        return orientations, gravity

    def assert_unchanged(self, orientations, gravity):
        after, report = correct_pelvis(orientations, self.times, gravity)
        self.assertEqual(report["replaced_frames"], 0)
        self.assertIs(after["pelvis"], orientations["pelvis"])
        return after, report

    def test_shared_turn_and_independent_yaw_do_not_trigger(self):
        turn = self.rotation("Y", 180 * self.times / self.times[-1])
        for values in ((turn, turn, turn), (turn, None, None)):
            with self.subTest(shared=values[1] is not None):
                self.assert_unchanged(*self.data(*values))

    def test_common_deep_bend_and_normal_bow_do_not_trigger(self):
        bend = self.rotation("X", 70)
        self.assert_unchanged(*self.data(bend, bend, bend))
        self.assert_unchanged(*self.data(self.rotation("X", 40),
                                       self.rotation("X", 65), self.rotation("X", 65)))

    def test_single_failed_torso_does_not_trigger(self):
        self.assert_unchanged(*self.data(chest=self.rotation("Z", 90)))
        self.assert_unchanged(*self.data(pelvis=self.rotation("Z", 90),
                                       chest=self.rotation("Z", 70)))

    def test_brief_anomaly_does_not_trigger(self):
        angle = np.where((self.times >= 5) & (self.times < 5.2), 90, 0)
        self.assert_unchanged(*self.data(pelvis=self.rotation("X", angle)))

    def test_no_raw_evidence_or_contradictory_raw_evidence_prevents_substitution(self):
        orientations, _ = self.data(pelvis=self.rotation("X", 90))
        _, report = self.assert_unchanged(orientations, None)
        self.assertEqual(report["status"], "skipped")
        _, stationary_gravity = self.data()
        self.assert_unchanged(orientations, stationary_gravity)

    def slipped_data(self):
        # Smooth physical sensor slip after a healthy interval; torso keeps
        # turning after the slip. Every segment has a small normal pitch.
        phase = np.clip((self.times - 7.0) / 2.0, 0, 1)
        slip = 90 * phase * phase * (3 - 2 * phase)
        turn = self.rotation("Y", np.clip((self.times - 10) / 8, 0, 1) * 180)
        chest = turn * self.rotation("X", 5)
        pelvis = self.rotation("Y", 12) * chest * self.rotation("Z", slip)
        return self.data(pelvis, chest, chest), self.rotation("Y", 12) * chest

    def test_sustained_slip_substitutes_smoothly_and_preserves_turns(self):
        (orientations, gravity), expected = self.slipped_data()
        after, report = correct_pelvis(orientations, self.times, gravity)
        self.assertEqual(report["status"], "substituted")
        self.assertEqual(report["max_weight"], 1.0)
        self.assertTrue(report["suspect_intervals"])
        self.assertTrue(report["replaced_intervals"])
        fully_replaced = np.asarray(report["weight_by_frame"]) == 1
        error = (expected[fully_replaced].inv() * after["pelvis"][fully_replaced]).magnitude()
        self.assertLess(float(np.max(error)), 1e-10)
        self.assertLess(report["max_output_frame_step_deg"], 3.0)
        for name in ("chest", "upper_back", "left_foot"):
            self.assertIs(after[name], orientations[name])
        # Reports are persisted as JSON by the converter.
        json.dumps(report, allow_nan=False)

    def test_common_time_varying_heading_is_retained(self):
        (original, gravity), _ = self.slipped_data()
        extra_turn = self.rotation("Y", 70 * np.sin(self.times / 8))
        turned = {name: extra_turn * value for name, value in original.items()}
        a, ra = correct_pelvis(original, self.times, gravity)
        b, rb = correct_pelvis(turned, self.times, gravity)
        np.testing.assert_allclose(ra["weight_by_frame"], rb["weight_by_frame"], atol=1e-12)
        expected = extra_turn * a["pelvis"]
        self.assertLess(np.max((expected.inv() * b["pelvis"]).magnitude()), 1e-10)

    def test_quaternion_signs_do_not_change_correction(self):
        (original, gravity), _ = self.slipped_data()
        flipped = {name: Rotation.from_quat(value.as_quat() * np.where(np.arange(self.n)[:, None] % 2, -1, 1))
                   for name, value in original.items()}
        a, ra = correct_pelvis(original, self.times, gravity)
        b, rb = correct_pelvis(flipped, self.times, gravity)
        np.testing.assert_allclose(ra["weight_by_frame"], rb["weight_by_frame"])
        self.assertLess(np.max((a["pelvis"].inv() * b["pelvis"]).magnitude()), 1e-10)

    def test_entry_threshold_dips_do_not_end_confirmed_fault(self):
        angle = np.where(self.times >= 4, 90.0, 0.0)
        # Still an abnormal posture, but repeatedly below the entry threshold.
        angle[(self.times >= 10) & (self.times < 10.8)] = 50
        angle[(self.times >= 14) & (self.times < 15)] = 45
        data, gravity = self.data(pelvis=self.rotation("Z", angle))
        _, report = correct_pelvis(data, self.times, gravity)
        self.assertEqual(len(report["suspect_intervals"]), 1)
        weights = np.asarray(report["weight_by_frame"])
        self.assertTrue(np.all(weights[self.times >= 9] == 1))
        self.assertFalse(report["recovery_confirmations"])

    def test_sustained_genuine_recovery_exits_fault(self):
        angle = np.where((self.times >= 4) & (self.times < 11), 90, 0)
        data, gravity = self.data(pelvis=self.rotation("Z", angle))
        after, report = correct_pelvis(data, self.times, gravity)
        self.assertEqual(len(report["recovery_confirmations"]), 1)
        self.assertAlmostEqual(report["recovery_confirmations"][0]["confirmed_time"], 13 - 1 / 60)
        weights = np.asarray(report["weight_by_frame"])
        self.assertTrue(np.all(weights[self.times >= 13] == 0))
        self.assertLess(np.max((data["pelvis"][self.times >= 13].inv()
                               * after["pelvis"][self.times >= 13]).magnitude()), 1e-10)

    def test_later_shared_deep_bend_is_recovery_not_permanent_substitution(self):
        pelvis_angle = np.where(self.times < 4, 0, np.where(self.times < 11, 90, 70))
        torso_angle = np.where(self.times < 11, 0, 70)
        data, gravity = self.data(self.rotation("X", pelvis_angle),
                                  self.rotation("X", torso_angle), self.rotation("X", torso_angle))
        _, report = correct_pelvis(data, self.times, gravity)
        self.assertEqual(len(report["recovery_confirmations"]), 1)
        self.assertTrue(np.all(np.asarray(report["weight_by_frame"])[self.times >= 13] == 0))

    def test_unreliable_torso_fades_out_and_is_never_used(self):
        pelvis = self.rotation("Z", np.where(self.times >= 4, 90, 0))
        chest = self.rotation("X", np.where(self.times >= 12, 90, 0))
        data, gravity = self.data(pelvis, chest)
        after, report = correct_pelvis(data, self.times, gravity)
        weights = np.asarray(report["weight_by_frame"])
        self.assertTrue(report["reference_unavailable_intervals"])
        self.assertGreater(weights[np.flatnonzero(self.times >= 10.5)[0]], .9)
        self.assertTrue(np.all(weights[self.times >= 12] == 0))
        self.assertLess(np.max((data["pelvis"][self.times >= 12].inv()
                               * after["pelvis"][self.times >= 12]).magnitude()), 1e-10)

    def test_faulty_spin_crossing_180_does_not_reenter_transition(self):
        # Independent gravity indicates a displaced sensor; its gyro-driven
        # heading spins repeatedly across the shortest-quaternion boundary.
        common_turn = self.rotation("Y", 15 * np.clip(self.times - 5, 0, None))
        slip = self.rotation("Z", np.where(self.times >= 4, 80, 0))
        spin = self.rotation("Y", 900 * np.clip(self.times - 4, 0, None))
        data, gravity = self.data(common_turn * spin * slip, common_turn, common_turn)
        after, report = correct_pelvis(data, self.times, gravity)
        output = after["pelvis"]
        steps = np.rad2deg((output[:-1].inv() * output[1:]).magnitude())
        transition = (self.times[:-1] >= 4) & (self.times[:-1] < 5.5)
        self.assertLess(float(np.max(steps[transition])), 1.6)
        start = np.flatnonzero(self.times >= 4)[0]
        self.assertLess((data["pelvis"][start].inv() * output[start]).magnitude(), 1e-10)
        fully_replaced = np.asarray(report["weight_by_frame"]) == 1
        self.assertLess(np.max((common_turn[fully_replaced].inv()
                               * output[fully_replaced]).magnitude()), 1e-10)

    def test_backtracking_is_bounded_and_requires_continuous_raw_corroboration(self):
        pelvis = self.rotation("Z", np.where(self.times >= 6, 90, 0))
        data, gravity = self.data(pelvis)
        raw_angle = np.where(self.times >= 6, 90, np.where(self.times >= 3.5, 40, 0))
        gravity["pelvis"] = self.rotation("Z", raw_angle).inv().apply([0, 1, 0])
        after, report = correct_pelvis(data, self.times, gravity)
        interval = report["backtracked_intervals"][0]
        self.assertAlmostEqual(interval["start_time"], 4)
        self.assertAlmostEqual(interval["backtracked_seconds"], 2)
        np.testing.assert_allclose(after["pelvis"][self.times < 4].as_quat(),
                                   data["pelvis"][self.times < 4].as_quat())
        # A short evidence break prevents reaching older passing samples.
        raw_angle[(self.times >= 4.7) & (self.times < 4.9)] = 0
        gravity["pelvis"] = self.rotation("Z", raw_angle).inv().apply([0, 1, 0])
        _, report = correct_pelvis(data, self.times, gravity)
        self.assertAlmostEqual(report["backtracked_intervals"][0]["start_time"], 4.9)

    def test_raw_lead_without_confirmed_fault_cannot_backtrack(self):
        angle = np.where((self.times >= 6) & (self.times < 6.5), 90, 0)
        data, gravity = self.data(pelvis=self.rotation("Z", angle))
        gravity["pelvis"] = self.rotation("Z", np.where(self.times >= 4, 90, 0)).inv().apply([0, 1, 0])
        _, report = self.assert_unchanged(data, gravity)
        self.assertFalse(report["backtracked_intervals"])
        # All segments subsequently bending together is also not a fault.
        bend = self.rotation("Z", np.where(self.times >= 6, 70, 0))
        data, gravity = self.data(bend, bend, bend)
        _, report = self.assert_unchanged(data, gravity)
        self.assertFalse(report["backtracked_intervals"])

    def test_invalid_times_and_settings_are_rejected(self):
        data, gravity = self.data()
        with self.assertRaises(ValueError):
            correct_pelvis(data, self.times[::-1], gravity)
        with self.assertRaises(ValueError):
            correct_pelvis(data, self.times, gravity, settings=PelvisCorrectionSettings(blend_seconds=0))


if __name__ == "__main__":
    unittest.main()
