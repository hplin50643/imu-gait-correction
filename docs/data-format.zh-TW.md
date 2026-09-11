# 輸入資料格式

[English](data-format.md) | **繁體中文** · [首頁](../README.zh-TW.md)

## 檔案與感測器名稱

本儲存庫不附實際量測 CSV。請將有權使用的量測資料放入本機目錄。轉換程式每個感測器讀取一份 CSV，檔名格式為 `<trial>_<sensor>.csv`。預設試驗名稱為 `Edward_field1`，預設目錄為 `data/Edward_field1_raw/`。

| 感測器檔名後綴 | BVH 關節 | 意義 |
| --- | --- | --- |
| `pelvis` | Hips | 骨盆感測器 |
| `upper_back` | Spine | 上背感測器；以串接軀幹關節近似對應 |
| `chest` | Chest | 胸部感測器；航向參考與有條件的骨盆替代來源 |
| `head` | Head | 頭部感測器 |
| `left_upper_arm` | LeftArm | 左上臂 |
| `left_forearm` | LeftForeArm | 左前臂 |
| `right_upper_arm` | RightArm | 右上臂 |
| `right_forearm` | RightForeArm | 右前臂 |
| `left_thigh` | LeftUpLeg | 左大腿 |
| `left_shank` | LeftLeg | 左小腿 |
| `left_foot` | LeftFoot | 左腳 |
| `right_thigh` | RightUpLeg | 右大腿 |
| `right_shank` | RightLeg | 右小腿 |
| `right_foot` | RightFoot | 右腳 |

例如骨盆檔案是 `data/Edward_field1_raw/Edward_field1_pelvis.csv`，14 份檔案皆須提供。其餘骨架關節繼承父節點方向，不代表額外的量測。

## 欄位與單位

```text
Timestamp,ax,ay,az,gx,gy,gz,is_calibration
```

| 欄位 | 型態／預設單位 | 意義 |
| --- | --- | --- |
| `Timestamp` | 有限數值，秒 | 共用時間軸上的取樣時間 |
| `ax`、`ay`、`az` | 有限數值，m/s² | 包含重力參考、以感測器座標表示的加速度 |
| `gx`、`gy`、`gz` | 有限數值，rad/s | 繞感測器各軸的角速度 |
| `is_calibration` | 布林標記 | 該筆資料是否位於開頭校正區塊 |

校正標記接受 `true`／`false` 或 `1`／`0`，不區分大小寫並忽略前後空白。額外欄位會被忽略；本轉換流程不使用既有四元數、步態階段或 ZUPT 欄位。

預設單位是對這份紀錄的假設，尚未由設備文件確認。只有在確認來源單位後，才使用 `--gyro-unit deg/s` 或 `--accel-unit g`；程式內部會轉為 rad/s 與 m/s²。加速度平均值不會被扣除，因為傾斜估計需要重力參考。

## 校正與時間要求

- 時間戳必須嚴格遞增，不能重複或含非有限值；六軸量測欄位也必須全部為有限數值。
- 每個感測器必須具有一個開頭校正區塊，之後接續動作資料。校正區塊及各感測器共同重疊的校正時間，都至少須涵蓋 0.5 秒。
- 預設校正姿勢為站立、雙手下垂（N-pose），且足夠靜止以估計角速度偏移。只有實際以 T-pose 校正時，才使用 `--pose t`。
- 各感測器取樣間隔的中位數必須一致。本紀錄約為 200 Hz；時間戳相同本身不能證明硬體已同步。
- 共同有效終點受第一個超過 `--max-gap`（預設 0.05 秒）的缺口、足夠長且六軸完全重複的尾端區塊，或檔案終點限制。固定尾值偵測是資料品質啟發式檢查，不是對停止變化原因的診斷。
- 只對有效區間內的短缺口插值。角速度回捲先在原始連續區塊修復，不跨缺口配對事件。
- `--start`／`--end` 使用原始時間戳。處理仍從校正段開始，指定起點不會重新初始化融合或走路校正基準。較早的 `--end` 會減少可用的後續觀測，因此可能改變離線估計。

本示範紀錄的校正段為 `0–5.145 秒`，有效動作段為 `5.15–92.795 秒`。60 FPS 的最後輸出時間戳為 `92.783333 秒`，共 5,259 幀。這些是特定紀錄的觀測結果，不是程式寫死的長度要求。

## 使用其他紀錄

```sh
python imu_to_bvh.py --input-dir data/my_trial_raw --trial my_trial --output outputs/my_trial.bvh
```

以 `my_trial_<sensor>.csv` 的命名方式提供全部檔案。解讀結果前請查看[安裝與參數設定](parameters.zh-TW.md)：新的紀錄可能具有不同的感測器軸向、起始姿勢、身體比例或角速度回捲模型。預設輸出名稱不會隨 `--trial` 自動改變，因此請如上明確指定 `--output`。

產生的 JSON 報告包含本機輸入／輸出路徑、時間、校正統計、修正事件及假設。完整報告請留在本機；[驗證說明](validation.zh-TW.md)介紹本儲存庫採用的不含路徑摘要。
