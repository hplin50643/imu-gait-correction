# 專案配置與發布內容

[English](repository.md) | **繁體中文** · [首頁](../README.zh-TW.md)

公開儲存庫為 [root50643/imu-gait-correction](https://github.com/root50643/imu-gait-correction)。本專案由 Python 腳本組成，沒有 PyPI 套件設定；本次整理不新增授權條款，也不授予新的使用權利。

```text
README.md / README.zh-TW.md     英文首頁／完整繁體中文
imu_to_bvh.py                   主要轉換程式
gyro_repair.py                  局部角速度修復
walking_constraints.py         骨盆替代
walking_heading.py             下肢相對航向穩定化
validate_bvh.py                 獨立 BVH 讀取與驗證程式
compare_bvh.py                  可標示版本的前後比較
mounting.json                  固定安裝假設
requirements.txt               Python 相依套件
environment.yml                Python 3.10 conda 環境
tests/                         合成與回歸測試
docs/                          成對說明、圖片與比較摘要
examples/                      v1／v3 BVH 與成對觀看說明
data/Edward_field1_raw/         可執行範例的 14 份原始 CSV
tools/build_release.py         依明確檔案清單建立 ZIP
release-files.txt              經審查的發布檔案清單
.github/workflows/tests.yml    Ubuntu／Windows 測試工作流程
```

## 內附的原始資料範例

發布內容包含 `data/Edward_field1_raw/` 中全部 **14 份原始 CSV**，合計 **33,663,479 位元組（約 33.7 MB）**，保留原始檔案位元組。複製或下載專案並安裝環境後，`python imu_to_bvh.py` 預設就會讀取此目錄；[快速開始](../README.zh-TW.md#安裝與執行)提供完整命令與輸出路徑。

這是資料排除規則中逐檔明列的例外，只包含這些經審查的 CSV 路徑。將其他檔案放入此目錄或其他 `data/` 目錄，不會自動加入 Git 或發布 ZIP。

## 僅保留本機的資料

| 位置 | 內容與處理方式 |
| --- | --- |
| `data/` 的其他內容 | 14 份範例以外的錄製資料、處理過的資料及來源壓縮檔；保留本機。 |
| `outputs/` | 既有 v1/v2/v3 輸出、實驗比較、預覽及完整報告；保留本機。 |
| `tools/bvhview/` | 從專案根目錄移至此處的既有 BVHView 執行檔及壓縮檔，Python 轉換器不需要它們。 |
| `.local/` | 原始截圖備份、舊 README 備份、整理腳本及本機驗證輸出。 |
| `dist/` | 產生的發布 ZIP 與校驗碼清單。 |
| 快取／環境 | Python 位元碼、編輯器狀態、虛擬環境與本機環境設定。 |

這些僅供本機使用的內容由 [`.gitignore`](../.gitignore) 排除，`data/` 中只允許 14 份經審查的原始 CSV 路徑。`outputs/` 以外的 `*.report.json` 也會忽略，因為報告包含本機絕對路徑。原始資料及既有輸出均保留；先前的目錄整理只搬移既有的四份根目錄測試檔，以及檢視器執行檔／壓縮檔。另複製兩份示範 BVH 至 `examples/`，不包含任何環境目錄。

## 建立並審查 ZIP

```sh
python tools/build_release.py
```

建立工具只使用 [release-files.txt](../release-files.txt) 明確列出的檔案，不會遞迴封裝整個專案。它會拒絕不存在、重複、排除或外部路徑。輸出為 `dist/imu-to-bvh-github.zip`，內含單一 `imu-to-bvh/` 目錄。`dist/imu-to-bvh-github.manifest.json` 列出各檔案的位元組數與 SHA-256，以及 ZIP 的校驗碼。工具固定每個封裝項目的時間戳及權限；檔案位元組與 Python/zlib 環境相同時，會產生相同的 ZIP 位元組。ZIP 與其清單是本機交付產物，不會加入原始碼發布內容。

重建前請審查檔案清單。發布內容包含腳本、測試、安裝／CI 設定、完整英文與繁體中文文件、四張裁切截圖及中繼資料、不含路徑的 v1/v3 數值摘要、兩份示範 BVH，以及 `data/Edward_field1_raw/` 中的 14 份原始 CSV。排除其餘原始或處理過的資料、來源壓縮檔、實驗報告、環境、本機檢視器執行檔及原始截圖。

這份檔案清單也是 Git 發布的審查範圍。建立 ZIP 不會提交、上傳或推送任何內容。公開的原始碼發布內容維護於上方連結的儲存庫。
