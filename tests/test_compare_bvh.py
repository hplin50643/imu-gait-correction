"""Regression checks for paired BVH comparisons and presentation offsets."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from compare_bvh import build_comparison, SUMMARY_JOINTS


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def fixture(self, name, tilt=0, x=0, frames=3, dt=.02):
        joints = ("Chest", *SUMMARY_JOINTS[1:])
        hierarchy = ["HIERARCHY", "ROOT Hips", "{", "OFFSET 0 0 0",
                     "CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation"]
        for joint in joints:
            hierarchy += [f"JOINT {joint}", "{", "OFFSET 0 -10 0",
                          "CHANNELS 3 Zrotation Xrotation Yrotation", "}"]
        hierarchy += ["}", "MOTION", f"Frames: {frames}", f"Frame Time: {dt}"]
        row = [x, 100, 0, tilt, 0, 0] + [0] * (3 * len(joints))
        path = self.root / name
        path.write_text("\n".join(hierarchy + [" ".join(map(str, row))] * frames) + "\n",
                        encoding="ascii")
        return path

    def test_identical_labels_keep_both_distinct_datasets(self):
        before = self.fixture("before.bvh", tilt=35)
        after = self.fixture("after.bvh", tilt=5)
        _, summary = build_comparison(before, after, "Trial", "Trial")
        self.assertEqual(summary["labels"], {"before": "Trial", "after": "Trial"})
        self.assertEqual(set(summary["metrics"]), {"before", "after"})
        self.assertAlmostEqual(summary["metrics"]["before"]["Hips"]["last_10s_median_tilt_deg"], 35)
        self.assertAlmostEqual(summary["metrics"]["after"]["Hips"]["last_10s_median_tilt_deg"], 5)
        self.assertEqual(summary["files"], {"before": "before.bvh", "after": "after.bvh"})

    def test_display_translation_does_not_change_orientation_metrics(self):
        before = self.fixture("original.bvh", tilt=25)
        after = self.fixture("shifted.bvh", tilt=25, x=100)
        data, summary = build_comparison(before, after)
        self.assertEqual(summary["metrics"]["before"], summary["metrics"]["after"])
        for joint in SUMMARY_JOINTS:
            for metric in ("tilt", "relative_heading"):
                np.testing.assert_allclose(data["before"][1][joint][metric],
                                           data["after"][1][joint][metric])

    def test_incompatible_sampling_is_rejected_including_single_frame(self):
        for before_frames, after_frames, before_dt, after_dt in ((3, 2, .02, .02),
                                                               (3, 3, .02, .03),
                                                               (1, 1, .02, .03)):
            with self.subTest(frames=(before_frames, after_frames), dt=(before_dt, after_dt)):
                before = self.fixture("before.bvh", frames=before_frames, dt=before_dt)
                after = self.fixture("after.bvh", frames=after_frames, dt=after_dt)
                with self.assertRaisesRegex(ValueError, "equal frame"):
                    build_comparison(before, after)


if __name__ == "__main__":
    unittest.main()
