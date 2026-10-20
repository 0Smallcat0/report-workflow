# 可用性第三輪 2026-10-20

處理 PR #1 最後一則審查留言「還沒修的」清單（分支 `fix/usability-round3`，base `fix/usability-audit-2026-10-19` `f27aa10`）。
每項先寫會失敗的測試（`tests/test_usability_round3_2026_10_20.py`），再修；沒有放寬任何事實檢查。

## 驗收：兩份新報告

以新使用者身分照 README → SKILL.md 的受控流程寫（`start_report → get_next_action/submit_action → publish_report`），
用前兩輪沒用過的 profile 與題目。作者稿在 `*/authored/`，每一輪被擋後作者做的修改都是一個獨立檔案，
用同一支 `drive.py` 重跑：

```
benchmarks/evidence/usability_round3_2026-10-20/run.sh \
  benchmarks/evidence/usability_round3_2026-10-20/memo_en/authored/memo_round2.py LOG.jsonl [其他版本的 src/]
```

第三個參數指向另一個 checkout 的 `src/`，就能在 base 分支上重跑同一份稿（本紀錄的 base 是 `f27aa10` 的 worktree）。

| | 報告 X `memo_en/` | 報告 Y `project_zh/` |
| --- | --- | --- |
| profile | `quant_research_memo`（英文） | `admissions_project_report`（中文） |
| 題目 | 20 日動能訊號能否預測下週 ETF 籃子報酬，兩種市況下是否都成立 | 高中自主學習：教室二氧化碳濃度與上課專注度、開窗有沒有差 |
| 來源 | 36 週回測 CSV、測試筆記（含 Jegadeesh and Titman (1993)） | 48 筆量測 CSV、研究筆記（含 Satish et al. (2012)） |
| 用到的新功能 | `pearson_r`、`linear_fit`（#6）、空溢出列（#2）、筆記文獻（#5） | ratio 讀 intake 交叉表（#1）、`pearson_r`（#6）、空溢出列（#2）、參考文獻列（#5） |

### 每一次被擋

**報告 X（英文 memo）**

| 輪 | 本分支 | base `f27aa10` |
| --- | --- | --- |
| 第一稿 | publish 被 FE 擋：c4「36 weeks」的單位證據沒寫（證據是「36 values」）；c9 引 intake 的 regime 交叉表，句中用語（weeks, returned, average…）不在證據裡，覆蓋率 11% | ① `register_derived_evidence`：`pearson_r`、`linear_fit` 不支援 ② claim 階段：引用了沒註冊的 `E_D_signal_r` 等 |
| 第二輪 | **完成**（`memo_round2.py`：c4 改說「36 weekly observations」並引筆記；c9 改用表格的字眼） | 作者只能刪掉 r、斜率、R²、分市況 r 三條主張（`memo_base_no_correlation.py`）→ ③ publish 被 FE 擋 c4、c9（同左） |
| 第三輪 | | **完成**，但成品沒有相關係數與迴歸、表 1 多一列 `3.50+ \| 0 \| — \| —`、內文引了 Jegadeesh and Titman (1993) 卻沒有參考文獻 |
| 被擋次數 | **1** | **3**（且少了 3 條主要主張） |

**報告 Y（中文專題）**

| 輪 | 本分支 | base `f27aa10` |
| --- | --- | --- |
| 第一稿 | ① publish：摘要 232 字，下限 300（作者寫太短，屬實） | ① 註冊：ratio 讀不到 intake 的「窗戶 分組交叉表」、`pearson_r` 不支援 ② claim 階段：引用沒註冊的 id |
| 第二輪 | ② 摘要「287 字」——作者自己數是 312 字。程式不算標點，但 brief 與訊息都沒說（本輪已修，見下 #9） | 作者另註冊一張一樣的分組表給 ratio 讀、刪掉 r（`project_base_workaround.py`）→ ③ 摘要 232 字 |
| 第三輪 | ③ FE：c4「48 節」的單位證據沒寫（證據是「48 筆」） | ④ 摘要 287 字（訊息沒說不算標點） |
| 第四輪 | **完成**。`final_qa_summary.md` 的「For the author」列出被移除的「教育部（2012）。室內空氣品質標準。」（筆記沒提到年份） | ⑤ FE「48 節」 |
| 第五輪 | | **完成**，但沒有相關係數、表 2 多一列 `1,800+ \| 0 \| —`、多註冊一張只為 ratio 用的表（還要在 outline 寫理由放棄它）、被移除的參考文獻只出現在 log |
| 被擋次數 | **3** | **5** |

兩份合計：本分支 4 次，base 8 次；base 的兩份成品各少了作者想寫的相關分析。

## 本輪修正

| # | 問題 | 修正 | commit |
| --- | --- | --- | --- |
| 7 | `run1_after.py` 等載入 `/tmp/claude-0/...`、基底腳本讀 `/home/user/...` | 改成相對腳本位置；測試掃描所有作者腳本 | `486430d` |
| 8 | `repair.py` 的 log 鍵是 `"**"` | 每筆紀錄頂層帶 step/status/stage | `486430d` |
| 1 | ratio／formula 讀不到 intake 自動建的交叉表 | 註冊時以同樣方式從原始列重算 intake 交叉表，可用 evidence id 指名；`expect` 照樣核對 | `c5b80ef` |
| 2 | 分組表的空溢出列（`9+`）出現在成品 | 最後一個邊界以上的開放區間若沒有資料就不列；邊界之間的空區間保留 | `b9ab27f` |
| 3 | 自動圖表標題是原始欄名；proposal 的建議圖一律放 `budget_resources` | 標題去掉底線、`_s`/`_cm`/`_twd` 寫成「(s)」「(TWD)」，不再寫「after sort desc」；proposal 中跟金額有關的表放預算，其他放 `problem_statement` | `2a5debf` |
| 4 | `remap_agent_artifacts` 找不到非預設 workspace 的前一個 run，也不複製檔案 | 新增 `previous_workspace_root`（預設＝`workspace_root`）；`write=true` 會複製新 run 沒有的作者檔案。受控流程下只複製目前 stage 可寫的檔案，其餘列在 `files_deferred`，不繞過 stage 範圍檢查 | `4be422a` |
| 5 | 筆記提到的文獻不進參考文獻；作者寫的參考文獻列被移除且只在 log | 讀出筆記中「Okano et al. (2019, …)」這類作者＋年份；作者寫的參考文獻列，只要某個來源檔的同一段文字同時出現第一作者姓氏與年份就保留（並取代自動產生的同一條）；其餘仍移除，但列在 publish 結果的 `warnings` 與 `final_qa_summary.md` 的「For the author」 | `ed26ea2` |
| 6 | 無法註冊相關係數、迴歸、R² | 新增 `pearson_r` 與 `linear_fit`（`x`、`y` 兩欄；斜率、截距、R²、n），只用兩欄都有數字的列並記錄排除幾列；至少 3 對、常數欄拒絕；證據文字寫出每個數字，FE 照常核對（測試：正確的 r 通過、錯的 r 被擋） | `98bc9b5` |
| 9 | （驗收時發現）中文摘要長度不說明不算標點；admissions 的 drafts brief 叫每個作者用「StrategyIR / AST / orthogonal quality gates」當主軸 | 訊息與 brief 寫明計算方式並附含標點的長度，規則不變；刪掉另一個專案的主軸文字 | `b571b98` |

## 仍沒修的（給擁有者決定或另開）

- 「室溫」對「溫度_C」、來源筆記「本研究整理」標示：依指示未動。
- **列數單位**：「36 weeks」「48 節」對證據的「36 values」「48 筆」被 FE 擋（兩份報告各一次）。這是單位比對的規則，放寬會讓「48 kg」也能對「48 筆」，所以沒動。另外同一份報告中「48 節課中有 93.8%」（引 `E_D_over_1000`）卻通過，規則在不同句子間不一致，值得擁有者看。
- **intake 交叉表的證據文字是原始欄名**（`mean next_week_return_pct`），用自然語言描述它的句子會因用語覆蓋率不足被 FE 擋（報告 X c9）。
- **intake 交叉表會平均編號欄**（`日次`、教室號碼 `教室 平均 236.33`），而且只取前 4 個數值欄，結果欄 `專注度` 不在表中。
- 自動建議圖仍有不合理的選擇：報告 X 的 Figure 1 是以「平均下週報酬」為 x 軸的折線圖；報告 Y 的 Figure 1 畫「日次 平均」。
- 分組表標籤印成 `1–3.50`（多一個 0），只是外觀。
- 中文寫法的作者＋年份（「王小明（2020）」）不讀，前面兩三個漢字是不是人名無法可靠判斷。
- 參考文獻的「可驗證」只看第一作者姓氏＋年份是否同段出現；標題、卷期是作者自己補的。另外原本的「看起來像出版物」規則（DOI、journal、斜體…）在 academic 類 profile 仍會讓來源檔沒提到的條目通過——這是既有行為，本輪沒有收緊。
- `remap_agent_artifacts` 在受控流程中要在每個 stage 開啟時各呼叫一次。

## 檔案

- `*/sources/`：來源；`*/authored/`：每輪作者稿；`*/logs/`：本分支（`branch_*`）與 base（`base_*`）每輪的紀錄
- `*/report_branch.docx`、`*/report_base.docx`：兩邊最後完成的成品；`*/final_qa_summary_branch.md`
- `project_zh/logs/branch_round2_after_message_fix.jsonl`：#9 修正後同一份第二輪稿得到的訊息
- `report_benchmarks_rerun.log`：8 種 profile 端到端重跑
