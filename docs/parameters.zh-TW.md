# 參數、比較執行與報告

[English](parameters.md) | [繁體中文](parameters.zh-TW.md) · [首頁](../README.zh-TW.md)

請在專案根目錄、已安裝 [requirements.txt](../requirements.txt) 相依套件的環境執行指令。發布內容不包含本機輸入 CSV。必要檔案見[資料格式](data-format.zh-TW.md)，各校正的意義見[演算法](algorithms.zh-TW.md)。

## 命令列選項

```shell
python imu_to_bvh.py --help
```

預設輸入、輸出與安裝設定路徑，以 `imu_to_bvh.py` 所在目錄為基準。命令列明確提供的相對路徑則以目前工作目錄解析。重複使用相同輸出路徑會覆寫 BVH 及對應 `.report.json`，原始輸入不會修改。

| 選項 | 預設值 | 意義 |
| --- | --- | --- |
| `--input-dir` | `data/Edward_field1_raw` | 包含全部 14 個感測器 CSV 的目錄。 |
| `--trial` | `Edward_field1` | 共同檔名前綴：`<trial>_<sensor>.csv`。 |
| `--output` | `outputs/Edward_field1_v3.bvh` | BVH 輸出位置，副檔名必須是 `.bvh`；報告使用相同主檔名。 |
| `--mounting` | `mounting.json` | 感測器到骨骼的安裝假設 JSON。 |
| `--fps` | `60` | 有限正值的每秒輸出幀數；選定區間必須容納至少兩幀。 |
| `--height-cm` | `175` | 有限正值的站立骨架高度，單位公分；身體比例仍為通用比例。 |
| `--pose` | `n` | 假設實際校正姿態：`n` 為站立手臂下垂，`t` 為手臂水平。不是單純改變畫面外觀的輸出姿勢選項。 |
| `--start` | 共同動作起始時間 | 以秒表示的原始時間戳，不可早於動作；先前校正及動作仍會處理。 |
| `--end` | 最早的感測器安全終點 | 以秒表示的原始時間戳，不可超過共同安全終點；實際網格在之前的樣本／幀結束，且必須晚於 `--start`。 |
| `--max-gap` | `0.05` | 允許插值的最大時間戳間隔，單位秒，須為有限正值且至少為正常間隔的 `1.01 ×`；處理在第一個更大缺口之前停止。 |
| `--gyro-unit` | `rad/s` | 來源角速度單位，可為 `rad/s` 或 `deg/s`；修復前先轉換為 rad/s。 |
| `--accel-unit` | `m/s2` | 來源加速度單位，可為 `m/s2` 或 `g`；`g` 乘以 9.80665。 |
| `--initial-bias` | `calibration` | `calibration` 扣除共同校正段平均角速度；`none` 跳過初始扣除。兩者皆保留 VQF 殘餘偏移估計。 |
| `--gyro-repair` | `paired` | `paired` 修復證據充分的局部角速度回捲；`none` 在扣偏移及融合前保持原始角速度。 |
| `--gyro-wrap-period` | 各區塊估計或 11.45 rad/s 備援值 | 有限正值的完整回捲週期，永遠以 rad/s 表示；僅在 `--gyro-repair paired` 時生效。 |
| `--fusion` | `auto` | `auto` 對骨盆採正向 VQF，其他採 offlineVQF；`online`／`offline` 強制所有感測器使用該濾波模式。整體轉換器仍是離線處理。 |
| `--foot-tau-acc` | `0.5` | 足部加速度時間常數，單位秒，須為有限正值；其他感測器使用 3 秒。 |
| `--walking-correction` | `full` | `full` 包含骨盆替代及下肢相對航向；`pelvis` 僅骨盆替代；`none` 兩者皆關閉。陀螺儀修復及融合依各自設定執行。 |

來源時間假設為秒。來源單位及實際同步尚未從設備文件驗證。只有確定來源單位時才更改單位參數；動畫看起來合理並不足以證明單位正確。

## 安裝設定

JSON 根節點包含 `sensors` 物件，以[資料格式](data-format.zh-TW.md)中的感測器名稱為鍵。未知感測器名稱或未知感測器設定會報錯。缺少的感測器項目，足部使用 `forward_axis: "+x"`，其他使用 `"+z"`，航向均為零；需要手臂修正時，請保留隨附的完整設定。

| 設定 | 意義 |
| --- | --- |
| `forward_axis` | 可為 `+x`、`-x`、`+y`、`-y`、`+z`、`-z`。假設該軸在校正時的水平投影指向人體前方，不能幾乎與重力平行。 |
| `heading_deg` | 繞 BVH 世界 +Y 軸的有限值右手正方向旋轉，單位度，作用於初始感測器到世界轉換；預設為零。 |
| `reference_sensor_to_world_wxyz` | 完整單位四元數 `[w,x,y,z]`，以 `np.isclose(norm, 1, atol=1e-4)` 檢查；取代該感測器的軸向／航向構建。 |

隨附設定中，`left_upper_arm` 與 `left_forearm` 的 `heading_deg` 為 `90`，`right_upper_arm` 與 `right_forearm` 為 `-90`。足部前向軸保留 `+x`，其餘為 `+z`。完整四元數在內部重排成 SciPy 的 `[x,y,z,w]` 慣例；不要將 SciPy 純量在後的四元數直接寫入這個純量在前的 JSON 欄位。

## 透過 Python 設定，而非 CLI 選項

下列名稱描述目前程式內設定，**不是額外的命令列選項**。請在獨立實驗中修改、記錄變更，並重新執行相關合成測試。預設設定是此資料集的步行假設，不是所有人體動作皆適用的門檻。

### 資料與融合設定

| 位置／設定 | 值 | 用途 |
| --- | --- | --- |
| `imu_to_bvh.py`：最短共同校正長度 | 0.5 s | 要求開頭有共同參考區間。 |
| `read_sensor`：固定尾端最短長度 | `max(10, ceil(0.05 / dt))` 個樣本 | 排除足夠長、完全相同的最後六軸向量區塊。 |
| `prepare_gyroscope`：連續區塊切分 | 缺口 `> 1.5 × dt` | 即使之後允許插值，也不將缺失感測器樣本兩側事件成對修復。 |
| `estimate_orientations`：平均角速度警告 | 模長 `> 5 deg/s` | 提醒可能有校正動作、單位錯誤或大偏移。 |
| `estimate_orientations`：參考旋轉視窗 | 共同校正最後 1 s | 使用較穩定的旋轉參考。 |
| `main`：非足部 `tauAcc` | 3 s | 骨盆、軀幹、頭、手臂、大腿及小腿的加速度濾波。 |
| `raw_gravity_evidence`：移動平均 | 3 s，邊界採最近值延伸 | 獨立於陀螺儀的加速度證據，以初始安裝旋轉轉換，再於骨盆偵測器中正規化。 |

除了 `tauAcc`，VQF 參數皆採函式庫預設值。底層 `estimate_orientations` 函式預設為 `gyro_repair="none"`、`fusion="online"`、`tau_acc=3.0`；CLI 的 `main` 會明確傳入其不同的選定預設值。直接呼叫此函式不等於使用 CLI 預設流程。

### 陀螺儀修復設定

| `gyro_repair.py` 中的名稱或規則 | 值 |
| --- | --- |
| `EMPIRICAL_PERIOD_RAD_S` | 11.45 rad/s 備援完整週期 |
| `MAX_PAIR_SECONDS` | 反向候選邊界相隔最多 0.5 s |
| `MIN_SAMPLE_RATE_HZ` | 50 Hz；更低頻率的樣本保持不變 |
| 候選跳變／端點大小 | `> 0.70 × P`／兩者皆 `> 0.35 × P`，且樣本異號 |
| 估計週期使用的相鄰斜率 | 同號，大小嚴格介於每樣本 0.005 至 0.6 rad/s |
| 週期估計支持條件 | 至少 12 筆嚴格介於 10.5 至 12.0 rad/s 的週期，且四分位距 `≤ 0.25 rad/s` |
| 修復後邊界跳變 | `≤ min(0.20 × P, max(1.5, 300 × dt))` rad/s，且各自 `< 25%` 原始跳變 |
| 修復後區間大小 | `≤ 1.35 × P` |

### 骨盆設定

所有欄位皆屬於 `walking_constraints.py` 的 `PelvisCorrectionSettings`。角度單位為度、時間單位為秒。偵測器同時使用融合重力與正規化原始加速度方向；條件的組合方式見[演算法說明](algorithms.zh-TW.md)。

| 欄位 | 預設值 | 作用 |
| --- | ---: | --- |
| `pelvis_tilt_deg` | 60 | 進入時，融合骨盆傾斜須超過此值。 |
| `pelvis_torso_difference_deg` | 45 | 進入時，融合骨盆方向與每個軀幹方向的差異須超過此值。 |
| `torso_max_tilt_deg` | 25 | 進入時，兩條訊號路徑中的每個軀幹參考傾斜皆須低於此值。 |
| `torso_agreement_deg` | 15 | 進入時，兩條路徑中的胸背差異皆須小於此值。 |
| `acceleration_pelvis_tilt_deg` | 50 | 進入時，原始加速度的骨盆傾斜須超過此值。 |
| `acceleration_difference_deg` | 40 | 進入時，原始加速度骨盆方向與每個軀幹方向的差異須超過此值。 |
| `minimum_suspect_seconds` | 2 | 進入所需的連續證據長度。 |
| `minimum_recovery_seconds` | 2 | 清除異常鎖定前所需的連續恢復證據長度。 |
| `recovery_pelvis_tilt_deg` | 30 | 直立恢復時，兩條路徑的骨盆傾斜皆須低於此值。 |
| `recovery_upright_difference_deg` | 25 | 直立恢復也要求兩條路徑中骨盆與每個軀幹差異皆低於此值。 |
| `recovery_common_pose_difference_deg` | 20 | 另一種共同姿態恢復：兩條路徑的全部骨盆對軀幹差異皆低於此值，即使當時共同彎腰。 |
| `active_torso_agreement_deg` | 20 | 使用參考期間，兩條路徑所需的胸背一致性。 |
| `active_torso_acceleration_agreement_deg` | 35 | 每個軀幹的融合重力方向與自身加速度證據的差異須低於此角度。 |
| `maximum_backtrack_seconds` | 2 | 已確認異常之前的最大延伸時間；允許範圍為 0–2，含兩端。 |
| `backtrack_acceleration_pelvis_tilt_deg` | 30 | 向前回溯佐證使用的骨盆加速度傾斜門檻。 |
| `backtrack_acceleration_difference_deg` | 25 | 向前回溯佐證使用的骨盆對每個軀幹加速度方向差門檻。 |
| `blend_seconds` | 1.5 | 進入過渡及參考可用性的淡入淡出；退出長度另受恢復時間上限限制。 |
| `alignment_window_seconds` | 10 | 優先使用的故障前健康航向對齊視窗。 |
| `alignment_guard_seconds` | 3 | 優先對齊視窗排除緊接異常前的這段時間。 |
| `alignment_max_pelvis_tilt_deg` | 30 | 兩條路徑中健康對齊樣本的骨盆傾斜上限。 |

除了允許 0–2 秒的回溯設定，其餘值皆須為有限正值。這個 dataclass 沒有 CLI 選項或 JSON 設定檔。自訂處理時，請在建立完整融合網格的旋轉及原始加速度證據後明確傳入：

```python
from walking_constraints import PelvisCorrectionSettings, correct_pelvis

# orientations：dict[str, scipy.spatial.transform.Rotation]，每個感測器一組旋轉
# grid：包含校正段、原始頻率的規則時間網格
# gravity_evidence：骨盆／胸部／上背的陣列，形狀為 (len(grid), 3)
settings = PelvisCorrectionSettings(maximum_backtrack_seconds=0.0)
corrected, audit = correct_pelvis(
    orientations, grid, gravity_evidence, settings=settings
)
```

這段整合片段僅關閉起點回溯。變數須由你的處理程式產生；它不是獨立可執行的轉換指令。請使用轉換器的 `raw_gravity_evidence` 取得座標正確的證據。證據缺少，或向量含非有限值／零範數時，會略過替代並記錄原因；陣列形狀錯誤則會引發 `ValueError`。降低門檻不能取代對實際感測器安裝的確認。

### 下肢航向設定

| `walking_heading.py` 中的名稱或規則 | 值 | 作用 |
| --- | --- | --- |
| `SIGMA_SECONDS` | 2 s | Gaussian 標準差；`truncate=2.0` 產生約 ±4 s 的影響範圍。 |
| `SHORT_GAP_SECONDS` | 0.5 s | 可插值的有兩側界限無效缺口上限。 |
| `RECOVERY_SECONDS` | 1 s | 無支援觀測缺口後平滑返回的時間。 |
| `MAX_CORRECTION_RATE_DEG_S` | 45 deg/s | 實際航向修正的最大變化速率。 |
| +X 水平投影品質 | 胸部與骨段長度皆 `≥ 0.65` | 排除水平航向不明確的觀測。 |
| 胸部／下肢傾斜品質 | `≤ 25°`／`≤ 70°` | 僅使用符合步行假設的觀測。 |
| 基準備援 | 最初可靠的 2 s | 僅在沒有可靠校正觀測時使用。 |

這些常數沒有 CLI 覆寫選項。`--walking-correction pelvis` 可關閉下肢航向階段，同時保留骨盆替代。

## 比較執行與消融實驗

每次執行請指定不同輸出路徑，以保留對應報告。除另有說明外，以下範例均保留所附手臂安裝修正。

```shell
python imu_to_bvh.py --output outputs/full.bvh
python imu_to_bvh.py --walking-correction pelvis --output outputs/pelvis_only.bvh
python imu_to_bvh.py --walking-correction none --output outputs/fusion_only.bvh
python imu_to_bvh.py --gyro-repair none --output outputs/no_gyro_repair.bvh
python imu_to_bvh.py --fusion online --output outputs/all_forward_fusion.bvh
python imu_to_bvh.py --foot-tau-acc 3 --output outputs/foot_tau_3.bvh
python imu_to_bvh.py --initial-bias none --output outputs/no_initial_bias.bvh
```

`fusion_only` 仍使用成對陀螺儀修復及選定 VQF 設定；`no_gyro_repair` 仍套用步行約束。每次只更改一個設定，才能隔離它的影響。

若要重現包含手臂安裝修正、但不含 v3 變更的 v2 式基準流程：

```shell
python imu_to_bvh.py --walking-correction none --gyro-repair none --fusion online --foot-tau-acc 3 --output outputs/v2_baseline_reproduced.bvh
```

若要使用 v1 式處理，另外複製 `mounting.json` 為 `mounting_v1.json`，只將四個手臂的 `heading_deg` 改成零，接著用相同基準設定加上 `--mounting mounting_v1.json`。這可保留目前安裝設定。發布 v1 示範中的 X 軸平移 100 cm 僅供觀看，不屬於 IMU 重建。重現旋轉不會自動加上該展示位移。

裁切及輸出範例：

```shell
python imu_to_bvh.py --start 10 --end 30 --output outputs/segment_10_30.bvh
python imu_to_bvh.py --height-cm 170 --fps 30 --output outputs/height170_30fps.bvh
```

輸入在前一個有效融合樣本結束，輸出在前一個幀時間結束。裁切過短、剩餘少於兩個輸出幀時會拒絕轉換。正向融合不會消除校正階段的離線相依性。

## 閱讀 JSON 報告

每次轉換寫入 `<output-stem>.report.json`。它是稽核紀錄，不是準確度證明。報告包含絕對輸入路徑及本機 Python 執行檔路徑，分享前請檢視；示範 BVH 可以不附這些本機報告而獨立發布。

| 欄位 | 解讀 |
| --- | --- |
| `source_units_assumed`、`versions`、`warnings` | 單位假設、套件版本及尚存不確定性。 |
| `calibration_time_range` | 初始偏移與校正所用的共同開頭區間。 |
| `processing_time_range` | 完整規則融合網格，包含校正與指定 `--start` 之前的動作。 |
| `usable_motion_time_range` | 要求的起點與選定安全融合網格終點。 |
| `exported_motion_time_range`、`fps` | BVH 實際首末時間戳及輸出幀率。 |
| `sensors.<name>.safe_end_reason`、`long_gaps`、`exact_tail_rows` | 輸入受限原因、缺口與重複尾端證據。 |
| `sensors.<name>.calibration_mean_gyroscope_rad_s`、`subtracted_initial_bias_rad_s` | 實測共同校正角速度平均及實際扣除的向量。 |
| `sensors.<name>.final_vqf_residual_bias_rad_s` | 初始扣除之後，VQF 最後的額外偏移估計，不是原始感測器的總偏移。 |
| `sensors.<name>.calibration_reference_deviation_p95_deg` | 相對最後一秒校正參考的旋轉大小第 95 百分位；這是一致性診斷，不是解剖標定誤差。 |
| `sensors.<name>.fusion`、`mounting_assumption` | 每個感測器實際融合方式、`tauAcc` 與安裝設定。 |
| `sensors.<name>.gyro_repair` | 合計數量及各連續區塊的修復決策。 |
| `walking_corrections.pelvis` | 門檻設定、進入／回溯／恢復／參考區間、固定航向對齊及替代進度；關閉時不存在。 |
| `walking_corrections.leg_heading.segments.<name>` | 觀測有效率、無支援區間、校正／備援基準、修正大小與步進；關閉時不存在。 |
| `orientation_diagnostics` | 處理網格上，步行約束前後首末十秒骨段傾斜中位數及最大值；不是 v1／v3 檔案比較數值。 |
| `verification` | 幀／通道／關節數、歐拉角慣例及往返誤差；僅代表檔案數值一致性。 |
| `skeleton`、`fixed_root_position_cm` | 近似階層、偏移、感測器映射及固定根位置。 |

### 事件索引與時間基準

`gyro_repair.continuous_blocks` 包含各區塊的 `first_original_row`（從零開始的 CSV 資料列索引）、原始首末時間戳、週期來源、候選、未解決邊界及接受的區間。接受事件的 `first_sample`／`last_sample` 是**相對該區塊、從零開始且含兩端的樣本索引**，不是整份 CSV 的索引。加上 `first_original_row` 即可還原原始資料列的零起算索引。每個接受事件也包含原始 `first_timestamp` 及 `last_timestamp`，較容易直接檢視。未解決邊界索引 `i` 表示區塊樣本 `i` 到 `i+1` 的跳變；x／y／z 列表對應 gx／gy／gz。`changed_samples` 計算任一軸變更的時間列；逐軸數量相加可能重複計算同一列。

`walking_corrections.pelvis.weight_by_frame` 因歷史命名使用「frame」，實際對應 **`processing_time_range` 的融合網格**，本資料約 200 Hz，且包含校正。它不直接對齊裁切後 60 FPS 的 BVH 列。若有 `N` 個權重且網格規則，索引 `i` 對應 `t0 + i × (t1 − t0)/(N − 1)`。骨盆區間時間戳採此原始時間基準；`end_time_inclusive` 包含最後樣本，區間長度包含一個取樣間隔。

權重表示朝胸部推估姿態的進度，恢復或參考不可用時會降低。零保留來源姿態，一完全使用對齊的胸部目標。中間值不是每個時刻的原始骨盆／胸部簡單混合；進入過程使用固定初始相對旋轉，避免重新引入故障翻轉。請將 `transition_method`、`weight_definition` 與權重陣列一起閱讀。

對全域骨段旋轉 `R`，報告傾斜為以度表示的 `acos(clamp(R[1,1], −1, 1))`，即骨段 +Y 與世界 +Y 的夾角。直立行走可能預期較小傾斜，但它不是相對量測真值的誤差；尤其校正後骨盆數值可能來自明確軀幹替代。檢查能證明及無法證明的內容見[驗證](validation.zh-TW.md)。
