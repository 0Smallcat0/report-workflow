# 可用性獨立審查紀錄 2026-10-20

PR #1（`fix/usability-audit-2026-10-19`，head `aa117b7`）的獨立審查。做了三件事：重跑 PR 的每個宣稱、
以新使用者身分另寫兩份不同類型的真實報告、比對歷史版本。所有修正都在本分支 `aa117b7..HEAD`，
每個缺陷先有失敗測試（`tests/test_usability_review_2026_10_20.py`，44 個測試）再修。

## 1. PR #1 宣稱的驗證

| 宣稱 | 重跑結果 |
| --- | --- |
| 1288 個測試通過，新增 28 個，其中 21 個在未修正的 HEAD 會失敗 | **對**。1288 OK；把新測試檔放到 master `d966669` 跑：16 failures + 5 errors = 21 |
| 對抗測試 recall 89.13%（41/46），誤殺 0% | **對**。`run_adversarial_benchmark.py --check` 通過，封存為 89.1%（41/46）、0/27 |
| 8 種 profile 端到端 8/8 | **對**。重跑 8/8 |
| report-quality、drone-market、render_skill_docs、版本同步檢查都通過 | **對** |
| 三份報告修正前後的行為（run1/2/3 的 before/after） | **對**。用 PR 的 `harness/drive.py` 在 master 與 PR head 各重跑一次，卡點與 `logs/*.jsonl` 一致：mmdc 決策、`unknown sections: results`、`5次/個`、`'24'and`、`retitle`、FA 不認 revision_plan、未採用的 starter 圖被建出 |
| 「三份報告在修正後都完成 publish」 | **部分對**。run1 修正後第一次 publish 仍被 FE 擋（c9「室溫」），作者改寫句子後才完成；README 的表格有寫「仍擋」，但 PR 說明的這句話沒提 |
| `run1_after.py`、`run1_old.py`、`run1_wa.py`、`run3_noretitle.py` 可重現 | **不對**。它們載入 `/tmp/claude-0/rw/tasks/run1.py`，是另一個 session 的暫存路徑，在倉庫裡無法直接執行（改路徑後可以） |
| `harness/repair.py` 的紀錄 | 紀錄寫成 `{"step":"submit_action","**":{...}}`，log 裡看不到每步狀態 |
| 「mid-run 竄改已通過的產物仍然會擋」是安全性質 | 宣稱的行為屬實，但它正是本次報告 B 卡死的原因（見下 #4）：被擋的檔案是 CLAIM_PLAN 自己改寫過的，作者無從「還原」。本分支改成「回到擁有該檔的 stage 重新驗證」，沒有任何檢查被略過 |

## 2. 兩份新報告

照 README → SKILL.md 的受控流程（`check_environment → start_report → get_next_action/submit_action → publish_report`）。
作者稿在 `*/authored/`，用 `../usability_audit_2026-10-19/harness/drive.py` 可重跑：

```
python benchmarks/evidence/usability_audit_2026-10-19/harness/drive.py \
  benchmarks/evidence/usability_review_2026-10-20/paper_en/authored/paper_after_fixes.py OUTDIR LOG.jsonl
```

- **A `proposal_zh/`**：中文提案（proposal），給區公所的「社區圖書館週間延長開放」。來源：入館人次 CSV、問卷 CSV、館務會議經費 memo。
- **B `paper_en/`**：英文課堂論文（academic_paper），睡眠時數與期中成績。來源：40 列問卷 CSV、背景筆記。

### 卡點與修正

| # | 報告 | 卡在哪 | 對作者的影響 | 修正 |
| --- | --- | --- | --- | --- |
| 1 | A | `register_derived_evidence` 失敗的請求被留在 `derived_evidence.json`，且重新註冊時保留舊順序 | 照錯誤訊息改正順序仍得到同一錯誤；死掉的請求在 publish 時讓 DERIVED_EVIDENCE 擋下整份報告，並把作者導到改不了該檔的 drafts stage。只能手改內部檔案 | `564b176` |
| 2 | B | 分組表把 7.5 印成 `7.50–9`，作者寫 `7.5-9` 被說「不是這張表的列」 | 多一輪 | `cf44fb0` |
| 3 | B | claim_type 不被證據允許，claim 階段放行 | 寫完 outline、drafts 才在 lint/FA 得知 | `2b75720` |
| 4 | B | 照 lint 修 `claim_matrix.json` 後，outline 階段回 `scope_violation`「還原舊內容」 | 舊內容是 pipeline 改寫過的版本，作者沒有副本；放回自己的舊版也被拒，**整個 run 無法前進** | `61247d5` |
| 5 | A | 省略選用章節（時程）後標題編號 5 → 7 | 成品錯誤 | `045f56e` |
| 6 | A/B | drafts brief 完全沒提 SKILL.md 推薦的 `structured_drafts.json` | 照 brief 走會手寫 sentence_map | `273430e` |
| 7 | A/B | `check_environment` 的 `required_preflight_decisions` 仍列出 mmdc、notebook_sync、web_research | 文件說「從這個範本開始」，於是每份報告前都問三個選用問題（PR #4 只修了 start_report 端） | `5dfb5ad` |
| 8 | A | 自動建議圖把筆數、佔比、平均、中位數疊成 stacked bar，還把「合計」畫成一個時段 | 起始建議無用 | `e50ef8f`、`8fe79de` |
| 9 | A | 沒給 `title` 時成品沒有標題，QA 全 pass | 交出去的文件沒有標題 | `04d3bce` |
| 10 | B | outline brief 要求填 `paper_spine`（沒有任何程式讀它）；publish 才要求沒寫在任何 brief 的 `thesis_statement` | publish 才擋，要回頭重跑 | `b556dd7` |
| 11 | B | academic_paper 缺 correspondence 在 publish 才擋，而它只能由 start_report 給 | 唯一解法是重開 run | `6a38b39`（開始時就列出；可在 outline.json 補 `front_matter`） |
| 12 | B | brief 範例摘要寫 `**Background:**`，ABSTRACT_CHECK 只認 `## Background:`，回「Found: none」，且失敗被判成 `blocked_non_author_repair` | 照 brief 寫必擋，且沒有可寫的路徑 | `a2c81fa` |
| 13 | B | FIGURE_QUALITY 錯誤訊息為 `[None]`；要求 prose 寫 `Figure 2`（figure_id），但成品把它印成 Figure 1 | 只能寫一個錯誤的交叉引用才能過 | `0b63560` |
| 14 | B | APA 句首要拼寫數字，「Forty undergraduates…」被 FS 判成沒寫出 40 | 誤判 | `9f58591` |
| 15 | B | 沒給 keywords 的 academic_paper 會被印上另一個專案的關鍵字（StrategyIR、abstract syntax tree compilation…） | 成品出現捏造的 metadata | `6023fb5` |
| 16 | B | 引用註冊失敗的 `E_D_` id，訊息說「這些產物可能來自另一個 run，請 remap」 | 錯誤的修法方向 | `c640880` |
| 17 | B | 散佈圖 `data.x/y` 是空的（作者稿讀錯欄位），所有檢查都通過，成品是一張空座標軸 | 成品錯誤 | `537daeb` |

### 版本比對（同一份作者稿）

`*/logs/` 是每個版本第一次卡住的紀錄。舊版沒有 `formula`（≤4.39）與 `group_by`（4.32），所以這兩份報告需要的統計在舊版根本算不出來，
「舊版比較好用」只在不需要計算的報告上成立（PR #1 的 v4.29.1 單擺實驗即是）。

| 版本 | A 提案 | B 論文（作者第一稿） |
| --- | --- | --- |
| v4.32.0 / v4.35.0 / v4.39.0 | `install_decisions: {}` 被拒；`formula` 不支援；引用失敗 id 時被叫去 remap | 同左 |
| master `d966669` | `{}` 被拒；outline 被要求刪掉 4 張沒用的 starter 圖 | `{}` 被拒；`7.5-9` 不是列；remap 誤導訊息 |
| PR head `aa117b7` | **完成** | 依序卡在：`7.5-9`、remap 誤導、（改用 start_report 傳 correspondence 後）thesis、摘要格式、`[None]` 圖表錯誤（需寫錯誤的 Figure 2）、「Forty」。`aa117b7_round1..4.jsonl` |
| 本分支 | **完成** | 第一稿在 **claim 階段**就指出 c3 類型錯誤；改成 factual、在 outline 補 `front_matter` 後**完成**（`branch_after_fixes.jsonl`） |

### 自 v4.29.1 起讓產報告變難的改動，對照修正狀態

| 改動（commit） | 增加的負擔 | 狀態 |
| --- | --- | --- |
| `2ad0542` 混合單位判定 | `units` 欄讓整檔失去統計 | PR #1 已修 |
| `899e086` 每X 比率 | `5次/個` 誤判 | PR #1 已修 |
| `a27c2ca` results_mode 位置 | brief 指錯 section | PR #1 已修 |
| `48b31f5`、`3c6df12` starter 圖 | 未採用的建議圖被強制處理、仍被建出 | PR #1 已修；本分支再修建議圖本身（#8） |
| `f07b19a` rewind | scope_violation | PR #1 只修 lint/publish 階段；本分支修所有階段（#4） |
| `3fd812c` 交叉表必須安置或放棄 | 每張自動交叉表都要處理；ratio 讀不到自動表（未修，見下） | 部分 |
| `9d0bec7` DERIVED_EVIDENCE 硬擋 | 失敗的註冊永久擋 publish | 本分支已修（#1） |
| FS（4.30）、FT、FL、FT2（`4eba285`、`e401849`） | 新增四個事實檢查 | 本次只遇到 FS 誤判（#14），已修；沒有放寬事實檢查 |
| PAPER_SCOPE_FREEZE、METADATA_GATE（較早） | publish 才檢查 thesis / 作者資料 | 本分支提前到 outline / start（#10、#11） |

## 3. 測試與 benchmark

- `python -m unittest discover -s tests`：**1332 通過**（PR head 1288 + 本次 44）。
- `run_adversarial_benchmark.py --check`：通過，recall **89.1%（41/46）**、誤殺 **0%（0/27）**，與 PR head 相同，判定沒有變動；FS 的改動只影響句首拼寫數字。
- `run_report_benchmarks.py --check`：通過。完整重跑 8/8 通過（`report_benchmarks_rerun.log`）。與封存相比，唯一的實質差異是 8 個 profile 的 Figure 1/2：
  原本是標題寫「Adoption planning parameters」、內容其實是 rows/share/mean/median 依 condition 的表格，現在是 28 對 20 分鐘的長條圖，與 benchmark 腳本寫的說明句一致（表格 4→2、圖 4→6，QA 狀態仍為 pass）。
  樣式表裡 `Title` 1→2 是本機 pandoc 多出一個空白 Title 段落，未修改的 master 在同一台機器上也一樣，屬環境差異。封存檔是在 Windows 錄的（`D:\` 路徑），沒有改寫，`--check` 照舊通過。
- `run_report_quality_benchmark.py --check`、`run_drone_market_benchmark.py --check`：通過；`record_tool_arm.py` 重錄後 fixture 無差異。

## 4. 沒修的

- 「室溫」對「溫度_C」（PR #1 已記錄）：詞彙比對的邊界，維持。
- 引用標註「（本研究整理，計算附件 C7）」：會議紀錄、背景筆記也被標成「本研究整理／計算附件」，對讀者是誤導（PR #1 已記錄，留給擁有者）。
- `ratio`／`formula` 不能直接讀 intake 自動建的交叉表，只能讀同一次註冊的表；作者得重新註冊一張一樣的表，再放棄原本那張。
- 沒有相關／迴歸運算（`correlation`、斜率、R²）可註冊；README 說 R² 會算，但只對欄名像「measured」的實驗表自動算。報告 B 只能用分組平均表達關係。屬功能缺口，不在本次修正範圍。
- 作者在筆記裡寫的文獻（Walker 2017、Okano 2019）不會進參考文獻：References 只收被宣告為出版物的來源檔；作者寫的參考文獻列被移除，訊息只在 log。
- 分組表的空溢出列（`9+ | 0 | — | — | —`）會出現在成品表格中。
- 自動圖表標題仍用原始欄名（`mean median_processing_minutes by condition`）；proposal 的建議圖一律放在 `budget_resources`。
- 沒給 title 時 run 目錄以整句 prompt 命名（Windows 路徑長度風險）。
- `remap_agent_artifacts` 找不到非預設 workspace 的前一個 run（`previous_workspace_root` 沒有傳下去），而且只改 id、不複製檔案。
