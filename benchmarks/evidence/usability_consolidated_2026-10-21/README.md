# 三份新報告：整合後的流程能不能一次跑完（2026-10-21）

整合 PR #1、#2、#3 之後，用前面三輪都沒用過的題目與資料，從 `start_report` 一路走到
`publish_report`，各寫一份報告：

| 資料夾 | profile | 語言 | 資料 |
|---|---|---|---|
| `quant_zh/` | `quant_research_memo` | 繁中 | 低波動因子回測（2 回看期間 × 樣本內外 × 高低波動組合，8 列）＋研究筆記 |
| `lab_zh/` | `engineering_lab_report` | 繁中 | 彈簧伸長量（6 種負重 × 3 次量測＋平均）＋實驗講義 |
| `business_en/` | `business_report` | 英文 | 客服工單（3 月 × 3 管道）＋營運備忘錄 |

資料都是為了測試寫的示範數據，來源檔裡也這樣寫明，不含任何個人資料。

## 怎麼重跑

```bash
pip install -e .[render]
cd benchmarks/evidence/usability_consolidated_2026-10-21
RW_LABEL=branch python harness/run_all.py quant_zh     # lab_zh、business_en 同理
# 換成別的版本：PYTHONPATH=<另一個 checkout>/src RW_LABEL=master python harness/run_all.py quant_zh
```

`harness/rw.py` 一次呼叫一個工具（`check_environment`+`start_report`、`get_next_action`、
`submit_action`、`register_derived_evidence`、`publish_report`），`run_all.py` 把
`authored/` 裡的作者檔案依序交出去，在第一次被擋的地方停下來，跟作者實際碰到的一樣。
每一步記在 `<報告>/logs/<版本>.jsonl`，路徑已換成 `<run>`。run 資料夾在 `.runs/`，不進 git。

`authored/id_labels.json` 只做一件事：自動交叉表的 evidence id 是內容雜湊，各版本措辭
不同 id 就不同，所以用表格第一行對回去，作者內容本身一字不改。

## 結果：同一份作者稿，四個版本

| | master `1562182` | #2 head `9c5f908`（含 #1） | #3 head `096fe43` | 本分支 |
|---|---|---|---|---|
| quant_zh | publish 擋 7 條 | publish 擋 7 條 | publish 擋 7 條 | **一次完成，0 次被擋** |
| lab_zh | drafts 擋（缺 `cover`）；補上 cover 後 publish 擋 2 條 | 同左 | 同左 | **一次完成，0 次被擋** |
| business_en | publish 擋 3 條 | publish 擋 3 條 | publish 擋 2 條 | **一次完成，0 次被擋** |
| run 資料夾名稱 | 含空白（business） | 含空白 | 含逗號 | 連字號、無逗號 |
| 3 份 brief 總量 | 58.0 / 55.9 / 57.4 KB | 60.0 / 58.0 / 59.2 KB | 48.0 / 46.3 / 47.1 KB | 49.4 / 48.3 / 48.9 KB |

被擋的是什麼（`logs/master.jsonl` 等）：

- **quant_zh**：「回看 12 個月時夏普值 0.81」——12 只在回看月數欄，主張「點名」的是夏普值
  欄（c1–c4）；研究問題被說成「證據只問不答」（c12）；「每月底依過去 6 個月」讀成 6 個月/月
  （c8）；樣本交叉表根本沒有夏普值欄，因為回看月數佔掉了它的位置（c6）。
- **lab_zh**：brief 叫作者寫的章節清單不含 `cover`，交出去卻因缺 `cover` 被擋；補上之後（把
  `structured_drafts.json` 加一個空的 `cover` 再跑，這個變體沒有存檔），
  「負重 50 g 時平均伸長 2.0 cm」的 50 g 不算數（c2），「前四組」被當成數量 4（c3）。
- **business_en**：「resolved within 24 hours」的 24 不在資料列，雖然欄名就是
  `resolved_within_24h_pct`（c2）；master 與 #2 另外把 "4 and 6 minutes" 的 and 當單位、
  把 minutes 與 min 當成不同單位（#3 已修）。

## 本分支上開了幾次 run、卡在哪

下表是寫這三份報告時的實際過程（程式還在修，探索紀錄在 `logs/explore.jsonl`）。每次卡住
先判斷是工具的錯還是作者的錯：工具的錯就修程式並加回歸測試，作者的錯就改稿。

| 報告 | 開 run 次數 | 卡在哪 | 處理 |
|---|---|---|---|
| quant_zh | 3（最終重跑 1） | run 1：intake 對回看月數算平均與四分位，交叉表沒有夏普值 | 修：三個以上設定欄構成完整網格時，數值設定欄也是設定（`ab070df`） |
| | | run 2：建議圖 x 軸是 6,6,6,6,12,12,12,12；outline 範本列出 brief 說「不要寫」的 `results_mode` | 修：三個標籤欄交叉時畫成網格（`d56e6f6`）；範本只在讀得到時列出（`bbb8e09`） |
| | | run 3：publish 被 FE 擋 4 類（回看 12 個月、研究問題、每月底、樣本外 6 個月） | 修 FE（`e7e55d0`），同一個 run 重交後完成 |
| lab_zh | 2（最終重跑 1） | run 1：建議圖畫「第一次伸長」而非平均；表頭「拉力 (N) (N)」 | 修（`fff13ee`、`9c3839c`） |
| | | run 2：drafts 與 lint 都因缺 `cover` 擋 | 修（`683e4a7`） |
| | | run 2：publish 擋「50 g」「前四組」「三次伸長」「兩組」 | 前兩個是工具的錯，修（`683e4a7`）；「三次伸長」「250 g 與 300 g 兩組」是作者寫的計數句、證據沒寫 3 和 2，改稿 |
| | | run 2：成品第一章是空的「封面」 | 修（`c4b9543`），重新 publish |
| business_en | 2（最終重跑 1） | run 1：brief 列出的題目少了第一題、第三題以 "and" 開頭；資料夾名稱有逗號 | 修（`43745dd`、`fcba81a`） |
| | | run 2：publish 擋「within 24 hours」與 c6 | 24 hours 是工具的錯，修（`732e6b7`）；c6 的主張寫了「3 June」但對應的句子沒寫，是作者的錯，拆成兩條主張 |

修完之後，用最終程式碼把三份都從頭重跑一次（`logs/branch.jsonl`）：每份 1 次 run、0 次被擋。

## 成品

`*/report_branch.docx` 是本分支一次跑完的成品。和前面幾輪相比，看得到的差別：

- 內文只在工具算出來的數字後面加「（本研究計算，表 N）」，引用作者自己檔案的句子不再加
  「（本研究整理，計算附件 C4）」。
- 表頭寫「年化報酬 (%) 平均」「砝碼質量 (g)」「resolved within 24h (%)」，不是原始欄名。
- 實驗報告不再有空的「封面」章節；量化備忘錄的圖是「回看期間 / 樣本」× 高低波動組合。

仍然看得到、這次沒動的：英文交叉表的表頭「median median first response (min)」（中位數的
中位數，字面上照實寫）；實驗報告的單欄摘要仍對砝碼質量算四分位（不擋人，只是 brief 裡多
一條）。
