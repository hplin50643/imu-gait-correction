"""Build a deterministic source ZIP from release-files.txt; see docs/repository.md."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {"data", "outputs", ".local", "dist", ".git", "__pycache__",
                  ".venv", "venv", "env", "bvhview"}
RAW_EXAMPLE_FILES = frozenset(
    f"data/Edward_field1_raw/Edward_field1_{sensor}.csv"
    for sensor in (
        "pelvis", "upper_back", "chest", "head",
        "left_upper_arm", "left_forearm", "right_upper_arm", "right_forearm",
        "left_thigh", "left_shank", "left_foot",
        "right_thigh", "right_shank", "right_foot",
    )
)


def release_entries(root: Path):
    """Read explicit file paths and refuse missing, unsafe, or duplicate entries."""
    entries, seen = [], set()
    for raw in (root / "release-files.txt").read_text(encoding="utf-8").splitlines():
        name = raw.strip()
        if not name or name.startswith("#"):
            continue
        relative = PurePosixPath(name)
        approved_raw_example = name in RAW_EXAMPLE_FILES
        if (relative.is_absolute() or "\\" in name or ":" in name
                or any(part in {".", ".."} for part in name.split("/"))
                or (any(part in EXCLUDED_PARTS for part in relative.parts)
                    and not approved_raw_example)
                or (relative.suffix.lower() == ".csv" and not approved_raw_example)
                or name.endswith((".report.json", ".zip", ".exe"))):
            raise ValueError(f"Unsafe or excluded release entry: {name}")
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError(f"Missing or external release file: {name}")
        if name.casefold() in seen:
            raise ValueError(f"Duplicate release entry: {name}")
        seen.add(name.casefold())
        entries.append((name, path.read_bytes()))
    if not entries:
        raise ValueError("Release list is empty")
    return sorted(entries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/imu-to-bvh-github.zip")
    args = parser.parse_args()
    try:
        entries = release_entries(ROOT)
        output = args.output.resolve()
        if output.suffix.lower() != ".zip":
            raise ValueError("Output must have a .zip suffix")
        manifest = output.with_suffix(".manifest.json")
        protected = {(ROOT / name).resolve() for name, _ in entries}
        if output in protected or manifest in protected:
            raise ValueError("Output would overwrite a release input")
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, contents in entries:
                info = zipfile.ZipInfo("imu-to-bvh/" + name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, contents, compresslevel=9)
        summary = {
            "archive": output.name,
            "archive_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "file_count": len(entries),
            "files": [{"path": name, "bytes": len(contents),
                       "sha256": hashlib.sha256(contents).hexdigest()}
                      for name, contents in entries],
        }
        manifest.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"Created {output.name}: {len(entries)} files, {output.stat().st_size:,} bytes")
        print(f"Manifest: {manifest.name}")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
