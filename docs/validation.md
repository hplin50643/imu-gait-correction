# Validation and interpretation

**English** | [繁體中文](validation.zh-TW.md) · [Home](../README.md)

## Scope of the evidence

The checks establish file validity, implementation behavior, reproducibility and internal consistency under walking assumptions. There is no synchronized optical motion capture or other independent joint-angle ground truth. A smaller inclination or a more upright skeleton is not a measurement of anatomical accuracy. Pelvis substitution is an estimate, and no absolute heading reference, position reconstruction or foot-contact correction is available.

## Recomputed v1 → v3 comparison

The results below were recomputed directly from [the released v1 and v3 examples](../examples/README.md). They are not the older local v2 → v3 comparison. The v1 file has only a +100 cm display translation on root X; this does not affect these rotation-based metrics.

For global joint rotation $R_j(t)$, the reported inclination is

$$\theta_j(t)=\cos^{-1}\!\left(\operatorname{clip}(R_{j,yy}(t),-1,1)\right).$$

It measures the angle between the joint frame's global +Y axis and world vertical. This is not a parent-relative joint angle or error against ground truth. Anatomical alignment, swing phase and bone-frame conventions affect the values, so lower values are not universally better.

| Joint | v1: last 10 s median (°) | v3: last 10 s median (°) |
| --- | ---: | ---: |
| Hips | 104.94 | 2.65 |
| LeftUpLeg | 19.55 | 19.25 |
| RightUpLeg | 17.61 | 17.14 |
| LeftLeg | 16.46 | 16.42 |
| RightLeg | 143.49 | 17.91 |
| LeftFoot | 87.06 | 17.82 |
| RightFoot | 91.91 | 15.42 |

The large changes in the pelvis, right shank and feet are consistent with suppression of visible collapse and orientation drift in this recording. They combine several changes between v1 and v3 and do not isolate the benefit of any single algorithm. The [machine-readable summary](validation/v1-v3.json) also includes the first 10 seconds. Its `before` / `after` keys are stable dataset identifiers; `labels` describes the compared versions. Timing is elapsed time from the first exported frame. The first window uses `t < 10`; the last uses `t > t_last - 10`.

The comparison plot additionally shows heading relative to the chest, computed from the horizontal projection of each joint's local +X axis and unwrapped after subtracting chest heading. It uses the same axis convention as the correction algorithm, but the plot does not apply that algorithm's reliability gates before unwrapping. Near-vertical axis projections can make this plot unreliable.

To recompute:

```sh
python compare_bvh.py examples/before_v1_x100.bvh examples/after_v3.bvh --before-label "v1 before correction" --after-label "v3 corrected" --output outputs/v1_v3_comparison.png
```

Frame counts and frame times must match. Equal sampling does not prove that two arbitrary files represent the same original motion interval; BVH has no absolute recording timestamp.

## Why the foot filter uses 0.5 seconds

The retained local foot-fusion experiment compared candidate `tauAcc` settings using one common quasi-static mask selected from measurements, without selecting on output orientations. Angular rates were locally repaired and calibration-bias corrected first. A 17-sample window at 200 Hz supplied rate RMS, mean acceleration and vector standard deviation. Candidate intervals required rate RMS below 0.6 rad/s, mean-acceleration magnitude within 0.75 m/s² of calibration gravity, acceleration-vector standard deviation below 0.7 m/s², and at least 10 samples (50 ms) after calibration.

The consistency measure is the angle between world vertical and the averaged acceleration transformed through the initial mounting and estimated foot rotation. It is distinct from the bone-frame tilt above. The existing diagnostic report gives:

| Foot | offlineVQF `tauAcc=3 s`: median discrepancy (°) | offlineVQF `tauAcc=0.5 s`: median discrepancy (°) |
| --- | ---: | ---: |
| Left | 42.67 | 11.91 |
| Right | 25.36 | 6.71 |

The 0.2 s candidate reduced this discrepancy further but noticeably compressed foot-lift dynamics; 0.5 s was retained as the compromise. The reference uses the same accelerometers as fusion, and the mask does not prove foot contact. This supports internal consistency only. These values come from the retained parameter-selection experiment, not the v1 → v3 BVH comparison or a new independent accuracy study. The complete experimental report and scripts remain under local `outputs/diagnostics/` and are excluded from publication.

## Automated checks

```sh
python -m unittest discover -v
python validate_bvh.py examples/before_v1_x100.bvh
python validate_bvh.py examples/after_v3.bvh
python imu_to_bvh.py
python validate_bvh.py outputs/Edward_field1_v3.bvh
```

All **42 tests** passed locally: 36 original tests, 3 comparison regression tests and 3 release-scope tests. They cover gravity/mounting transforms, known yaw and bias, noncommuting BVH parent-child round trips, Euler continuity, gaps and frozen tails, paired rate-wrap repair, corroborated pelvis faults and recovery, shared-turn preservation, heading reliability and recovery, and comparison labels/sampling/display-translation invariance. Release tests verify that the 14 approved CSV filenames preserve their original bytes and that unapproved CSV files, other data and local artifacts remain excluded. These are synthetic, structural and packaging checks, not clinical validation.

The independent validator composes explicit axis matrices without using SciPy's rotation conversion. Both examples contain 5,259 finite frames, 66 channels and 21 joints. Their nominal rate is 60 FPS; first-to-last duration is 87.633333 s. Root translation range is zero on every axis. Maximum bone-length variation is below $3\times10^{-14}$ cm and rotation orthogonality residual is below $2\times10^{-15}$, consistent with floating-point round-off.

The [14 original CSV files](../data/Edward_field1_raw/) are now included in the repository and release ZIP. Run the commands above from an extracted project or clone; the default converter reads that bundled recording and writes a new BVH and report under `outputs/`. No separate data download or path editing is needed.

Running the full default converter against this recording produced a BVH **byte-for-byte identical** to the existing v3 file in the tested NHRI Python 3.10 environment. Its SHA-256 is `9d18f032fe36eced0d87cefcd67037027857158377931d3025de560efd86da5f`. This is a check of this environment and recording, not a guarantee of identical floating-point serialization on every dependency version or operating system.

GitHub Actions installs dependencies and runs the tests, both existing example validators, the full default raw-data conversion and validation of the generated BVH on Python 3.10 under Ubuntu and Windows. The [Actions page](https://github.com/root50643/imu-gait-correction/actions) records results for each published commit; local success alone does not establish a hosted run's result. CSV files keep their original line endings and bytes; generated reports and outputs remain local.

## Screenshots and viewer checks

The four supplied screenshots compare teal v3 with yellow v1. They share an exact **780 × 580** center crop, with no resizing or redrawing. [Crop metadata](images/crops.json) records the original dimensions and crop boxes, and [image documentation](images/README.md) explains the provenance. The screenshots have no independently verified frame timestamps.

The [BVHView page](https://theorangeduck.com/media/uploads/BVHView/bvhview.html) was opened successfully and displayed its 3D canvas and drag-and-drop instructions during preparation. The available browser automation could not perform a local-file drag-and-drop, so a fresh playback session with the packaged files was not independently verified in that check. The provided screenshots illustrate the existing playback; both packaged files passed the independent parser and kinematic checks. Follow the [viewer instructions](../examples/README.md) to play them interactively.

## Reading a new conversion report

The converter writes a JSON report next to its BVH output. Review it together with the motion:

1. Check input units, calibration statistics, selected common interval, clipping reasons and output frame count.
2. Inspect gyro-repair counts and the estimated wrap period for each sensor. A large repair count is a prompt to inspect the raw signal, not proof of successful recovery.
3. Check fusion choices and foot `tauAcc`; faster gravity correction is a trade-off under dynamic acceleration.
4. Inspect pelvis fault intervals, backtracking, transition weights, recovery and rejected/unreliable torso references. Substituted motion cannot recover independent pelvis movement.
5. Inspect heading correction magnitude and reliability. Long invalid intervals hold correction. Missing reliable calibration triggers a reported first-reliable-two-seconds fallback; a segment with no reliable observation remains unchanged.
6. Compare corrected and ablated outputs, including turns and late frames. The report records algorithm decisions, not external accuracy.

See [parameters and report keys](parameters.md) for exact field names and adjustment locations. Full reports can contain local paths and experimental details, so they remain local. The published comparison summary uses filenames only.
