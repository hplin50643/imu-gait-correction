# Input data format

**English** | [繁體中文](data-format.zh-TW.md) · [Home](../README.md)

## Files and sensor names

This repository includes all 14 original CSV files in [data/Edward_field1_raw/](../data/Edward_field1_raw/) as a runnable example, totaling 33,663,479 bytes (approximately 33.7 MB). The files retain their original bytes; preprocessing and corrections take place during conversion. Other recordings, processed-data directories and source archives are not distributed.

The converter reads one CSV per sensor, using `<trial>_<sensor>.csv` as the filename. The default trial is `Edward_field1` and the default directory is `data/Edward_field1_raw/`. After [installation](../README.md#install-and-run), run the included recording from the repository root:

```sh
python imu_to_bvh.py
python validate_bvh.py outputs/Edward_field1_v3.bvh
```

The default conversion also writes `outputs/Edward_field1_v3.report.json`. Generated files remain local and are ignored by Git.

| Sensor suffix | BVH joint | Meaning |
| --- | --- | --- |
| `pelvis` | Hips | Pelvis sensor |
| `upper_back` | Spine | Upper-back sensor; approximate serial torso mapping |
| `chest` | Chest | Chest sensor; heading reference and conditional pelvis substitute |
| `head` | Head | Head sensor |
| `left_upper_arm` | LeftArm | Left upper arm |
| `left_forearm` | LeftForeArm | Left forearm |
| `right_upper_arm` | RightArm | Right upper arm |
| `right_forearm` | RightForeArm | Right forearm |
| `left_thigh` | LeftUpLeg | Left thigh |
| `left_shank` | LeftLeg | Left shank |
| `left_foot` | LeftFoot | Left foot |
| `right_thigh` | RightUpLeg | Right thigh |
| `right_shank` | RightLeg | Right shank |
| `right_foot` | RightFoot | Right foot |

For example, the pelvis file is `data/Edward_field1_raw/Edward_field1_pelvis.csv`. All 14 files are required. The remaining joints inherit their parent's orientation; they do not represent additional measurements.

## Columns and units

```text
Timestamp,ax,ay,az,gx,gy,gz,is_calibration
```

| Column | Type / default unit | Meaning |
| --- | --- | --- |
| `Timestamp` | Finite number, seconds | Sample time on a shared time axis |
| `ax`, `ay`, `az` | Finite numbers, m/s² | Acceleration including the gravity reference, expressed in sensor axes |
| `gx`, `gy`, `gz` | Finite numbers, rad/s | Angular velocity around the sensor axes |
| `is_calibration` | Boolean marker | Whether this sample belongs to the initial calibration block |

Calibration markers accept `true` / `false` or `1` / `0`, ignoring case and surrounding spaces. Additional columns are ignored. Existing quaternion, gait-phase and ZUPT columns are not used by this conversion pipeline.

The default units are assumptions about this recording, not manufacturer-confirmed facts. Use `--gyro-unit deg/s` or `--accel-unit g` only when the source units have been verified. The converter changes those units internally to rad/s and m/s². It does not subtract the acceleration mean, because gravity is needed for inclination estimation.

## Calibration and timing requirements

- Timestamps must be strictly increasing, with no duplicates or non-finite values. All six measurement columns must also be finite.
- Each sensor must have one leading calibration block followed by motion. The calibration block and common overlap must each cover at least 0.5 seconds.
- Default calibration assumes standing with arms down (N-pose) and sufficient stillness to estimate angular-rate bias. Use `--pose t` only if the actual calibration pose was a T-pose.
- Sensor median sample intervals must agree. This recording is approximately 200 Hz; matching timestamps alone do not establish hardware synchronization.
- The common usable endpoint is limited by the first gap exceeding `--max-gap` (default 0.05 s), a sufficiently long exactly repeated six-axis tail, or the file end. Exact-tail detection is a data-quality heuristic, not a diagnosis of why a sensor stopped changing.
- Only short gaps inside the usable interval are interpolated. Rate-wrap repair is applied to original continuous blocks first and does not pair events across gaps.
- `--start` / `--end` are original timestamps. Processing still begins at calibration; the requested start does not reinitialize the filter or walking correction baseline. An earlier `--end` can change offline estimates because future observations are no longer available.

For the supplied example recording, calibration is `0–5.145 s`; usable motion is `5.15–92.795 s`. At 60 FPS, the last exported timestamp is `92.783333 s`, giving 5,259 frames. These are recording-specific observations, not hard-coded duration requirements.

## Using a different recording

```sh
python imu_to_bvh.py --input-dir data/my_trial_raw --trial my_trial --output outputs/my_trial.bvh
```

Provide all files using the `my_trial_<sensor>.csv` convention. Review [mounting and parameter settings](parameters.md) before interpreting the result: sensor-axis assumptions, initial posture, body proportions and the empirical rate-wrap model may differ for a new recording. The default output name does not automatically change with `--trial`, so specify `--output` as above.

The generated JSON report includes local input/output paths, timing, calibration statistics, correction events and assumptions. Keep the full report local; [validation documentation](validation.md) describes the path-free summaries used in this repository.
