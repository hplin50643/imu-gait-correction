# BVH 示範檔案

[English](README.md) | **繁體中文** · [首頁](../README.zh-TW.md)

這兩份重建結果涵蓋同一段走路紀錄。原始 IMU CSV 保留在本機，不包含在發布內容中。

| 檔案 | 版本與用途 |
| --- | --- |
| [before_v1_x100.bvh](before_v1_x100.bvh) | 手臂安裝座標與走路校正之前的既有 v1 重建；根節點 X **平移 +100 cm**，方便並排展示。 |
| [after_v3.bvh](after_v3.bvh) | 採用目前手臂安裝座標、角速度回捲修復、足部融合設定、骨盆替代及下肢相對航向校正的 v3 重建。 |

+100 cm 的位移只改變 v1 根節點的 X 位置。所有旋轉、其他位置、骨架偏移量與影格時間均與本機 v1 檔案相同。這是展示用的間距，並非估計出的行走位移。除此之外，兩份檔案的根位置都是固定的；兩者皆未重建世界座標中的行走軌跡。

## 觀看動作

1. 下載本目錄的兩個 `.bvh` 檔案（在 GitHub 使用原始檔／下載按鈕），或解壓縮發布 ZIP。
2. 在瀏覽器開啟 [BVHView 線上檢視器](https://theorangeduck.com/media/uploads/BVHView/bvhview.html)。
3. 從檔案管理員將 `.bvh` 拖曳至檢視器畫布。同時載入兩份檔案即可並排比較。
4. 播放動作並比較相同影格，尤其留意紀錄後段。README 截圖中的**藍綠色為 v3 校正後，黃色為原始 IMU 的 v1 重建**。顏色屬於檢視器的顯示設定，BVH 檔案本身不包含這些顏色。

每份檔案包含 5,259 個影格、21 個關節、66 個通道，影格率為 60 FPS。首末影格間隔約為 87.6333 秒。BVH 的位置與偏移量使用公分，+Y 向上，旋轉通道採內在 Z-X-Y 順序。骨架使用假設的 175 cm 身高，並非受試者實測骨長。

截圖是穩定性與內部一致性的定性示例，不能證明與獨立量測的關節角一致。請參閱[驗證結果](../docs/validation.zh-TW.md)與[演算法限制](../docs/algorithms.zh-TW.md)。

## 在本機驗證與比較

安裝 [Python 環境](../README.zh-TW.md)後，在專案根目錄執行：

```sh
python validate_bvh.py examples/before_v1_x100.bvh
python validate_bvh.py examples/after_v3.bvh
python compare_bvh.py examples/before_v1_x100.bvh examples/after_v3.bvh --before-label "v1 before correction" --after-label "v3 corrected" --output outputs/v1_v3_comparison.png
```

比較指令會以相同輸出主檔名產生圖表及 JSON。標籤影響顯示文字；JSON 資料始終使用獨立的 `before` 與 `after` 鍵值。根位置的平移不影響姿態指標。工具要求影格數與影格時間相符，但 BVH 不記錄原始絕對起始時間，因此仍須自行確認兩份檔案涵蓋同一段動作。

預設轉換器會由本機 CSV 產生 v3。保留 `mounting.json` 並關閉目前的校正，得到的是保留手臂安裝修正的消融版本，不是完整重現 v1。兩者差異請參閱[參數與消融指令](../docs/parameters.zh-TW.md)。
