# Parameters, comparison runs, and reports

[English](parameters.md) | [繁體中文](parameters.zh-TW.md) · [Home](../README.md)

Run commands from the project root in an environment containing [requirements.txt](../requirements.txt). Private input CSV files are not included in the release. See [data format](data-format.md) for the required files and [algorithms](algorithms.md) for the meaning of each correction.

## Command-line options

```shell
python imu_to_bvh.py --help
```

Default input, output, and mounting paths are relative to the directory containing `imu_to_bvh.py`. Paths explicitly supplied on the command line resolve from the current working directory. Reusing an output path overwrites its BVH and companion `.report.json`; raw input files are not modified.

| Option | Default | Meaning |
| --- | --- | --- |
| `--input-dir` | `data/Edward_field1_raw` | Directory containing all 14 sensor CSV files. |
| `--trial` | `Edward_field1` | Shared filename prefix: `<trial>_<sensor>.csv`. |
| `--output` | `outputs/Edward_field1_v3.bvh` | BVH destination; suffix must be `.bvh`. The report uses the same stem. |
| `--mounting` | `mounting.json` | JSON sensor-to-bone mounting assumptions. |
| `--fps` | `60` | Positive finite output frames per second. At least two frames must fit in the selected interval. |
| `--height-cm` | `175` | Positive finite standing skeleton height in centimeters; proportions remain generic. |
| `--pose` | `n` | Assumed actual calibration pose: `n` = standing with arms down; `t` = arms horizontal. This is not a cosmetic output-pose switch. |
| `--start` | First common motion timestamp | Original timestamp in seconds; cannot precede motion. Earlier calibration and motion are still processed. |
| `--end` | Earliest safe sensor endpoint | Original timestamp in seconds; cannot exceed the common safe endpoint. Actual grids end on their preceding sample/frame. Must be later than `--start`. |
| `--max-gap` | `0.05` | Positive finite maximum timestamp interval to interpolate, seconds. Must be at least `1.01 ×` the normal interval. Processing stops before the first larger gap. |
| `--gyro-unit` | `rad/s` | Source angular-rate units: `rad/s` or `deg/s`. Conversion to rad/s happens before repair. |
| `--accel-unit` | `m/s2` | Source acceleration units: `m/s2` or `g`; `g` is multiplied by 9.80665. |
| `--initial-bias` | `calibration` | `calibration` subtracts the common calibration mean rate; `none` skips initial subtraction. VQF residual-bias estimation remains enabled in both cases. |
| `--gyro-repair` | `paired` | `paired` repairs supported local rate-wrap intervals; `none` leaves rates unchanged before bias subtraction and fusion. |
| `--gyro-wrap-period` | Per-block estimate or 11.45 rad/s fallback | Positive finite full wrap span, always in rad/s. Only takes effect with `--gyro-repair paired`. |
| `--fusion` | `auto` | `auto`: forward VQF for pelvis, offlineVQF elsewhere. `online` or `offline` forces that filter mode for all sensors. The complete converter remains offline. |
| `--foot-tau-acc` | `0.5` | Positive finite foot accelerometer time constant in seconds. Other sensors use 3 seconds. |
| `--walking-correction` | `full` | `full`: pelvis substitution plus relative leg heading; `pelvis`: substitution only; `none`: neither. Gyroscope repair and fusion retain their own settings. |

Source time is assumed to be seconds. Source units and physical synchronization have not been verified from device documentation. Change unit flags only when the source units are known; a plausible-looking animation is insufficient evidence.

## Mounting configuration

The JSON root contains a `sensors` object keyed by the sensor names in the [data format](data-format.md). Unknown sensor names or unknown per-sensor settings cause an error. Missing sensor entries use `forward_axis: "+x"` for feet and `"+z"` elsewhere, with zero heading; retain the supplied complete configuration when the arm correction is intended.

| Setting | Meaning |
| --- | --- |
| `forward_axis` | One of `+x`, `-x`, `+y`, `-y`, `+z`, `-z`. Its horizontal projection during calibration is assumed to indicate body forward. The projection must not be nearly parallel to gravity. |
| `heading_deg` | Finite right-handed rotation in degrees about BVH world +Y, applied to the initial sensor-to-world transform. Defaults to zero. |
| `reference_sensor_to_world_wxyz` | Complete unit quaternion `[w,x,y,z]`, checked with `np.isclose(norm, 1, atol=1e-4)`. Overrides the axis/heading construction for that sensor. |

The supplied file uses `heading_deg: 90` for `left_upper_arm` and `left_forearm`, and `-90` for `right_upper_arm` and `right_forearm`. It retains `+x` forward axes for feet and `+z` elsewhere. A full quaternion is reordered to SciPy's `[x,y,z,w]` convention internally; do not store a SciPy scalar-last quaternion directly in the scalar-first JSON field.

## Settings exposed through Python, not CLI flags

The following names describe current code settings. They are **not additional command-line options**. Change them in a separate experiment, record the change, and rerun the relevant synthetic tests. The default settings are walking assumptions for this dataset, not universal human-motion thresholds.

### Data and fusion settings

| Location / setting | Value | Purpose |
| --- | --- | --- |
| `imu_to_bvh.py`: minimum common calibration duration | 0.5 s | Require a leading common reference interval. |
| `read_sensor`: constant-tail minimum | `max(10, ceil(0.05 / dt))` samples | Exclude a sufficiently long, exactly repeated final six-axis vector. |
| `prepare_gyroscope`: continuous-block split | Gap `> 1.5 × dt` | Prevent paired repair across missing sensor samples, even when later interpolation is permitted. |
| `estimate_orientations`: mean-rate warning | Norm `> 5 deg/s` | Flag possible calibration motion, unit error, or large bias. |
| `estimate_orientations`: reference rotation window | Final 1 s of common calibration | Use a settled rotation reference. |
| `main`: non-foot `tauAcc` | 3 s | Accelerometer filtering for pelvis, torso, head, arms, thighs, and shanks. |
| `raw_gravity_evidence`: moving mean | 3 s, nearest boundary extension | Independent-of-gyro acceleration evidence, transformed by the initial mounting rotation; normalized inside the pelvis detector. |

VQF parameters other than `tauAcc` are library defaults. The low-level `estimate_orientations` function defaults to `gyro_repair="none"`, `fusion="online"`, and `tau_acc=3.0`; the CLI's `main` explicitly passes its different selected defaults. Calling that function directly is not equivalent to invoking the CLI defaults.

### Gyroscope repair settings

| Name or rule in `gyro_repair.py` | Value |
| --- | --- |
| `EMPIRICAL_PERIOD_RAD_S` | 11.45 rad/s fallback full span |
| `MAX_PAIR_SECONDS` | 0.5 s maximum separation of opposite candidate edges |
| `MIN_SAMPLE_RATE_HZ` | 50 Hz; lower-rate samples are left unchanged |
| Candidate jump / endpoint magnitudes | `> 0.70 × P` / both `> 0.35 × P`, with opposite sample signs |
| Neighbor slopes used to estimate span | Same sign; magnitudes strictly between 0.005 and 0.6 rad/s per sample |
| Span estimation support | At least 12 spans strictly between 10.5 and 12.0 rad/s, with IQR `≤ 0.25 rad/s` |
| Corrected boundary jump | `≤ min(0.20 × P, max(1.5, 300 × dt))` rad/s and `< 25%` of each original jump |
| Corrected interval magnitude | `≤ 1.35 × P` |

### Pelvis settings

All fields belong to `PelvisCorrectionSettings` in `walking_constraints.py`. Angles are degrees and durations are seconds. The detector uses both fused-gravity and normalized raw-acceleration directions; the [algorithm description](algorithms.md) explains how the conditions are combined.

| Field | Default | Role |
| --- | ---: | --- |
| `pelvis_tilt_deg` | 60 | Fused pelvis tilt must exceed this for entry. |
| `pelvis_torso_difference_deg` | 45 | Fused pelvis direction must differ this much from each torso direction for entry. |
| `torso_max_tilt_deg` | 25 | Each torso reference must be below this tilt for entry, in both signal paths. |
| `torso_agreement_deg` | 15 | Chest and back must differ by less than this for entry, in both paths. |
| `acceleration_pelvis_tilt_deg` | 50 | Raw-acceleration pelvis tilt must exceed this for entry. |
| `acceleration_difference_deg` | 40 | Raw-acceleration pelvis direction must differ this much from each torso direction for entry. |
| `minimum_suspect_seconds` | 2 | Required continuous entry evidence. |
| `minimum_recovery_seconds` | 2 | Required continuous recovery evidence before clearing the fault latch. |
| `recovery_pelvis_tilt_deg` | 30 | Upright-recovery pelvis tilt must be below this in both paths. |
| `recovery_upright_difference_deg` | 25 | Upright recovery also requires pelvis-to-each-torso differences below this in both paths. |
| `recovery_common_pose_difference_deg` | 20 | Alternative common-pose recovery: all pelvis-to-torso differences below this in both paths, even during a shared bend. |
| `active_torso_agreement_deg` | 20 | Chest/back agreement required while using the reference, in both paths. |
| `active_torso_acceleration_agreement_deg` | 35 | Each torso fused-gravity direction must agree with its own acceleration evidence below this angle. |
| `maximum_backtrack_seconds` | 2 | Maximum extension before a confirmed fault; allowed range is 0–2 inclusive. |
| `backtrack_acceleration_pelvis_tilt_deg` | 30 | Pelvis acceleration tilt threshold for backward corroboration. |
| `backtrack_acceleration_difference_deg` | 25 | Pelvis-to-each-torso acceleration difference threshold for backward corroboration. |
| `blend_seconds` | 1.5 | Entry transition and reference availability fades; exit duration is capped by recovery duration. |
| `alignment_window_seconds` | 10 | Preferred healthy pre-fault yaw-alignment window. |
| `alignment_guard_seconds` | 3 | Exclude these seconds immediately before fault onset from the preferred alignment window. |
| `alignment_max_pelvis_tilt_deg` | 30 | Healthy alignment pelvis tilt limit, in both paths. |

Except the 0–2 second backtrack setting, these values must be finite and positive. There is no CLI flag or JSON file for this dataclass. For custom processing, pass it explicitly after constructing rotations and raw-acceleration evidence on the complete fusion grid:

```python
from walking_constraints import PelvisCorrectionSettings, correct_pelvis

# orientations: dict[str, scipy.spatial.transform.Rotation], one array per sensor
# grid: regular original-rate times including calibration
# gravity_evidence: pelvis/chest/upper_back arrays with shape (len(grid), 3)
settings = PelvisCorrectionSettings(maximum_backtrack_seconds=0.0)
corrected, audit = correct_pelvis(
    orientations, grid, gravity_evidence, settings=settings
)
```

This integration fragment disables only onset backtracking. The variables must be produced by your processing code; it is not a standalone converter command. Use `raw_gravity_evidence` from the converter for correctly framed evidence. Missing evidence or non-finite/zero-norm vectors skip substitution with a reason; incorrect array shapes raise `ValueError`. Lowering thresholds is not a substitute for confirming actual sensor placement.

### Leg-heading settings

| Name or rule in `walking_heading.py` | Value | Role |
| --- | --- | --- |
| `SIGMA_SECONDS` | 2 s | Gaussian standard deviation; `truncate=2.0` yields approximately ±4 s support. |
| `SHORT_GAP_SECONDS` | 0.5 s | Maximum bounded invalid gap to interpolate. |
| `RECOVERY_SECONDS` | 1 s | Smooth return after an unsupported gap. |
| `MAX_CORRECTION_RATE_DEG_S` | 45 deg/s | Maximum rate of the applied heading correction. |
| Horizontal +X projection quality | Length `≥ 0.65` for chest and segment | Reject ill-defined horizontal heading observations. |
| Chest / leg tilt quality | `≤ 25°` / `≤ 70°` | Only use plausible walking observations. |
| Baseline fallback | First reliable 2 s | Used only when no reliable calibration observation exists. |

These constants have no CLI overrides. `--walking-correction pelvis` disables the leg-heading stage while keeping pelvis substitution.

## Comparison runs and ablations

Give each run a different output path so its report remains available. All examples below retain the supplied arm mounting correction unless otherwise stated.

```shell
python imu_to_bvh.py --output outputs/full.bvh
python imu_to_bvh.py --walking-correction pelvis --output outputs/pelvis_only.bvh
python imu_to_bvh.py --walking-correction none --output outputs/fusion_only.bvh
python imu_to_bvh.py --gyro-repair none --output outputs/no_gyro_repair.bvh
python imu_to_bvh.py --fusion online --output outputs/all_forward_fusion.bvh
python imu_to_bvh.py --foot-tau-acc 3 --output outputs/foot_tau_3.bvh
python imu_to_bvh.py --initial-bias none --output outputs/no_initial_bias.bvh
```

`fusion_only` still uses paired gyro repair and the selected VQF settings. `no_gyro_repair` still applies the walking constraints. Compare one changed setting at a time to isolate its effect.

To reproduce the v2-style processing baseline, including the arm mounting correction but excluding v3 changes:

```shell
python imu_to_bvh.py --walking-correction none --gyro-repair none --fusion online --foot-tau-acc 3 --output outputs/v2_baseline_reproduced.bvh
```

For v1-style processing, make a separate copy of `mounting.json` named `mounting_v1.json`, change only the four arm `heading_deg` values to zero, and use the same baseline settings with `--mounting mounting_v1.json`. This preserves the current mounting configuration. A 100 cm X translation in the distributed v1 demonstration is only a viewing offset; it is not part of IMU reconstruction. Reproducing rotations does not automatically add that demonstration offset.

Crop and output examples:

```shell
python imu_to_bvh.py --start 10 --end 30 --output outputs/segment_10_30.bvh
python imu_to_bvh.py --height-cm 170 --fps 30 --output outputs/height170_30fps.bvh
```

Input ends at the previous valid fusion sample and output ends at the previous frame time. A crop so short that fewer than two output frames remain is rejected. Online fusion does not remove the offline dependency of the correction stages.

## Reading the JSON report

Each conversion writes `<output-stem>.report.json`. It is an audit record, not an accuracy certificate. Reports include absolute input paths and the local Python executable path; review them before sharing. Example BVHs can be distributed without these local reports.

| Field | Interpretation |
| --- | --- |
| `source_units_assumed`, `versions`, `warnings` | Unit assumptions, package versions, and remaining uncertainties. |
| `calibration_time_range` | Common leading interval used for initial bias and calibration. |
| `processing_time_range` | Complete regular fusion grid, including calibration and motion before a requested `--start`. |
| `usable_motion_time_range` | Requested start and the selected safe fusion-grid endpoint. |
| `exported_motion_time_range`, `fps` | Actual first/last BVH timestamps and output frame rate. |
| `sensors.<name>.safe_end_reason`, `long_gaps`, `exact_tail_rows` | Why input was limited; gap and repeated-tail evidence. |
| `sensors.<name>.calibration_mean_gyroscope_rad_s`, `subtracted_initial_bias_rad_s` | Measured common-calibration rate mean and the vector actually subtracted. |
| `sensors.<name>.final_vqf_residual_bias_rad_s` | VQF's final additional bias estimate after initial subtraction, not the original sensor's total bias. |
| `sensors.<name>.calibration_reference_deviation_p95_deg` | 95th percentile rotation magnitude around the final-second calibration reference. It is a consistency diagnostic, not anatomical calibration error. |
| `sensors.<name>.fusion`, `mounting_assumption` | Actual per-sensor fusion method, `tauAcc`, and mounting settings. |
| `sensors.<name>.gyro_repair` | Aggregate counts and per-continuous-block repair decisions. |
| `walking_corrections.pelvis` | Threshold settings, entry/backtrack/recovery/reference intervals, fixed yaw alignments, and replacement progress. Absent when disabled. |
| `walking_corrections.leg_heading.segments.<name>` | Observation validity, unsupported intervals, calibration/fallback baseline, correction magnitude and step. Absent when disabled. |
| `orientation_diagnostics` | First/last ten-second median and maximum bone tilt before/after walking constraints on the processing grid. These are not the v1/v3 file-comparison metrics. |
| `verification` | Frame/channel/joint counts, Euler conventions and round-trip errors; numerical file consistency only. |
| `skeleton`, `fixed_root_position_cm` | Approximate hierarchy, offsets, sensor mapping, and fixed root position. |

### Event indices and time bases

`gyro_repair.continuous_blocks` contains each block's `first_original_row` (zero-based CSV data-row index), first/last original timestamps, period source, candidates, unresolved boundaries, and accepted intervals. Accepted `first_sample` / `last_sample` are **inclusive, zero-based sample indices relative to that block**, not the whole CSV. Add `first_original_row` to recover the zero-based original data-row index. Each accepted event also includes original `first_timestamp` and `last_timestamp`, which are simpler to inspect. Unresolved edge index `i` denotes the jump between block samples `i` and `i+1`; x/y/z lists refer to gx/gy/gz. `changed_samples` counts time rows changed on any axis; summing per-axis counts can count the same row more than once.

`walking_corrections.pelvis.weight_by_frame` is named “frame” for historical reasons. It actually follows the **fusion grid in `processing_time_range`**, approximately 200 Hz here, including calibration. It does not align directly with the cropped 60 FPS BVH rows. With `N` weights and a regular grid, index `i` maps to `t0 + i × (t1 − t0)/(N − 1)`. Pelvis interval timestamps use this original time base; `end_time_inclusive` includes its last sample. Durations include one sample interval.

Weights represent progress toward the chest-based approximation, reduced for recovery or reference unavailability. Zero leaves the source pose and one fully uses the aligned chest target. Intermediate values are not a simple mixture of the original and chest at every time: entry follows a fixed initial relative rotation to avoid reintroducing faulty spins. Read `transition_method` and `weight_definition` with the weight array.

For a global bone rotation `R`, the reported tilt is `acos(clamp(R[1,1], −1, 1))` in degrees: the angle between bone +Y and world +Y. A smaller tilt can be expected during upright walking, but it is not an error against measured truth. In particular, a corrected pelvis value can reflect explicit torso substitution. Consult [validation](validation.md) for what the checks can and cannot establish.
