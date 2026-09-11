"""Keep the public raw-data exception restricted to the approved recording."""
from pathlib import Path
import tempfile
import unittest

from tools.build_release import RAW_EXAMPLE_FILES, release_entries


class ReleaseRawExampleTests(unittest.TestCase):
    def test_approved_csv_files_preserve_original_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = sorted(RAW_EXAMPLE_FILES)
            self.assertEqual(len(names), 14)
            original = b"Timestamp,ax\r\n0.0,9.81\r\n"
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original)
            (root / "release-files.txt").write_text("\n".join(names), encoding="utf-8")
            self.assertEqual(release_entries(root), [(name, original) for name in names])

    def test_unapproved_csv_files_are_rejected_even_when_listed(self):
        names = (
            "data/Edward_field1_raw/another_recording.csv",
            "data/another_trial/Edward_field1_pelvis.csv",
            "examples/Edward_field1_pelvis.csv",
            "examples/unapproved.CSV",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in names:
                with self.subTest(name=name):
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("unapproved sample", encoding="utf-8")
                    (root / "release-files.txt").write_text(name, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Unsafe or excluded"):
                        release_entries(root)

    def test_other_data_and_local_artifacts_remain_excluded(self):
        names = (
            "data/Edward_field1_raw.7z",
            "data/Edward_field1_raw/notes.txt",
            "outputs/diagnostic.json",
            ".local/Edward_field1_pelvis.csv",
            "data/Edward_field1_raw/../Edward_field1_pelvis.csv",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in names:
                with self.subTest(name=name):
                    (root / "release-files.txt").write_text(name, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Unsafe or excluded"):
                        release_entries(root)


if __name__ == "__main__":
    unittest.main()
