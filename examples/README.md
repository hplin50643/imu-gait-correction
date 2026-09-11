# Example BVH files

**English** | [繁體中文](README.zh-TW.md) · [Home](../README.md)

These two reconstructions cover the same recorded walking interval. Raw IMU CSV files are kept locally and are not included in the release.

| File | Version and purpose |
| --- | --- |
| [before_v1_x100.bvh](before_v1_x100.bvh) | Existing v1 reconstruction before the arm mounting and walking corrections; root X is shifted by **+100 cm** for side-by-side display. |
| [after_v3.bvh](after_v3.bvh) | v3 reconstruction with the current arm mounting, rate-wrap repair, foot fusion settings, pelvis substitution and relative leg-heading correction. |

The +100 cm offset changes only v1 root X position. All rotations, other positions, skeleton offsets and frame timing are unchanged from the local v1 file. It is a display separation, not estimated walking displacement. Both files otherwise have fixed root positions; neither reconstructs a world-space walking trajectory.

## View the motion

1. Download the two `.bvh` files from this directory (use the raw/download button on GitHub), or extract the release ZIP.
2. Open the [BVHView online viewer](https://theorangeduck.com/media/uploads/BVHView/bvhview.html) in a browser.
3. Drag the `.bvh` files from your file manager onto the viewer canvas. Loading both files allows a side-by-side comparison.
4. Play the motion and compare corresponding frames, especially toward the end of the recording. The README screenshots show **teal = v3 corrected** and **yellow = v1 reconstruction from the original IMU**. Colors are viewer display settings; BVH files do not encode these colors.

Each file contains 5,259 frames, 21 joints and 66 channels at 60 FPS. The first-to-last-frame interval is about 87.6333 seconds. BVH positions and offsets are in centimeters, with +Y up and intrinsic Z-X-Y rotation channels. The skeleton uses an assumed height of 175 cm, rather than measured subject-specific bone lengths.

The screenshots are qualitative illustrations of stability and internal consistency. They do not establish agreement with independently measured joint angles. See the [validation results](../docs/validation.md) and [algorithm limitations](../docs/algorithms.md).

## Validate and compare locally

Run these commands from the repository root after installing the [Python environment](../README.md):

```sh
python validate_bvh.py examples/before_v1_x100.bvh
python validate_bvh.py examples/after_v3.bvh
python compare_bvh.py examples/before_v1_x100.bvh examples/after_v3.bvh --before-label "v1 before correction" --after-label "v3 corrected" --output outputs/v1_v3_comparison.png
```

The comparison command writes a plot and a JSON file under the same output stem. Labels affect presentation; JSON datasets always use the separate keys `before` and `after`. Root translation does not affect the orientation metrics. The tool requires matching frame counts and frame times, but BVH does not identify the original absolute start time: you must also ensure that the files cover the same motion interval.

The default converter creates v3 from local CSV data. Disabling the current corrections while keeping `mounting.json` is an ablation with the corrected arm mounting, not an exact reproduction of v1. See [parameters and ablation commands](../docs/parameters.md) for the distinction.
