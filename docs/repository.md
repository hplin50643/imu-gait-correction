# Repository layout and release contents

**English** | [繁體中文](repository.zh-TW.md) · [Home](../README.md)

The public repository is [root50643/imu-gait-correction](https://github.com/root50643/imu-gait-correction). The project is a set of Python scripts. It has no PyPI package configuration, and this preparation does not add a license or grant new usage rights.

```text
README.md / README.zh-TW.md     English home / complete Traditional Chinese
imu_to_bvh.py                   Main converter
gyro_repair.py                  Local angular-rate repair
walking_constraints.py         Pelvis substitution
walking_heading.py             Relative leg-heading stabilization
validate_bvh.py                 Independent BVH reader and validator
compare_bvh.py                  Labeled before/after comparison
mounting.json                  Fixed mounting assumptions
requirements.txt               Python dependencies
environment.yml                Python 3.10 conda environment
tests/                         Synthetic and regression tests
docs/                          Paired explanations, images, comparison summary
examples/                      v1 / v3 BVH files and paired viewing instructions
data/Edward_field1_raw/         14 original CSV files for the runnable example
tools/build_release.py         ZIP builder using an explicit file list
release-files.txt              Reviewed release file list
.github/workflows/tests.yml    Ubuntu / Windows test workflow
```

## Included raw-data example

The release includes all **14 original CSV files** in `data/Edward_field1_raw/`, totaling **33,663,479 bytes (approximately 33.7 MB)**. Their original bytes are preserved. After cloning or downloading the project and installing the environment, `python imu_to_bvh.py` reads this directory by default; the [quick start](../README.md#install-and-run) provides the full commands and output paths.

This is an explicit file-by-file exception to the data exclusion rules. Only these reviewed CSV paths are included; adding a different file to this directory or another `data/` directory does not automatically include it in Git or the release ZIP.

## Local-only material

| Location | Contents and treatment |
| --- | --- |
| Other `data/` contents | Recordings outside the 14-file example, processed data and source archives; retained locally. |
| `outputs/` | Existing v1/v2/v3 outputs, experimental comparisons, previews and full reports; retained locally. |
| `tools/bvhview/` | Existing BVHView executable and archive, moved here from the project root. The Python converter does not require them. |
| `.local/` | Original screenshot backups, previous README backup, preparation scripts and local verification outputs. |
| `dist/` | Generated release ZIP and its checksum manifest. |
| Caches / environments | Python bytecode, editor state, virtual environments and local environment settings. |

These local-only materials are excluded by [`.gitignore`](../.gitignore), with only the 14 reviewed raw CSV paths allowed under `data/`. `*.report.json` is also ignored outside `outputs/`, because reports include absolute local paths. The source data and existing outputs are preserved; the earlier directory cleanup moved only the four existing root test files and the viewer executable/archive. Two example BVHs were copied into `examples/`. No environment directory is included.

## Build and audit the ZIP

```sh
python tools/build_release.py
```

The builder uses only the exact files listed in [release-files.txt](../release-files.txt), never a recursive archive of the project. It rejects missing, duplicate, excluded or external paths. The output is `dist/imu-to-bvh-github.zip`, containing one `imu-to-bvh/` directory. `dist/imu-to-bvh-github.manifest.json` lists each file's byte count and SHA-256, plus the ZIP's checksum. The builder uses fixed entry timestamps and permissions; identical file bytes with the same Python/zlib environment produce the same ZIP bytes. The ZIP and its manifest are local delivery artifacts and are not added to the source release.

Review the file list before rebuilding. The release includes scripts, tests, installation/CI configuration, complete English and Traditional Chinese documentation, four cropped screenshots with metadata, a path-free v1/v3 numeric summary, two example BVHs, and the 14 original CSV files in `data/Edward_field1_raw/`. It excludes all other raw or processed data, source archives, experimental reports, environments, the local viewer executable and screenshot originals.

The file list is also the review boundary for Git publication. Creating a ZIP does not commit, upload or push anything. The public source release is maintained in the repository linked above.
