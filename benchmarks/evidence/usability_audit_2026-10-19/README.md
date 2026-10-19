# 可用性實測紀錄 2026-10-19

以「真的要交報告的作者」身分，把三份報告從 `start_report` 走到 `publish_report`，
記下每一次被擋、被擋的理由、為了過關把句子改成什麼樣子，以及最後的 DOCX。
同一份作者稿（`*/authored/*.py`）分別在三個版本上跑：

- **HEAD 修正前**：master `d966669`（4.39.0 之後）
- **v4.29.1**（`f07b19a`，2026-08-05）：只跑 run 1，因為 4.32.0 以前沒有
  `register_derived_evidence`，run 2、3 需要的統計量在舊版不能引用
- **修正後**：分支 `fix/usability-audit-2026-10-19`

`harness/drive.py` 照 SKILL.md 的受控流程逐步呼叫
`get_next_action → 寫該階段檔案 → submit_action → … → publish_report`，
每一步的回傳寫進 `*/logs/*.jsonl`。`harness/repair.py` 模擬作者在
publish 失敗後「照錯誤訊息修檔，再 submit_action」。

## Run 1　中文課堂作業：單擺實驗（engineering_lab_report）

來源：`sources/pendulum_trials.csv`（7 列量測）＋ `sources/lab_notes.md`（實驗紀錄）。
作者用 `register_derived_evidence` 的逐列公式算 g = 4π²L/T²。

| 步驟 | HEAD 修正前 | v4.29.1 | 修正後 |
| --- | --- | --- | --- |
| start_report，用 SKILL.md 範例的 `"install_decisions": {}` | 擋：`missing install decision for 'mmdc'`、`'notebook_sync'` | 同樣擋 | 通過 |
| outline，照 02_outline_plan.md 把 `results_mode` 放在 `sections.results` | 擋：`Outline references unknown sections: results` | 同樣擋 | brief 改寫成 `sections.results_discussion.results_mode`，照做通過 |
| publish：「每個擺長…重複 5 次取平均」 | FE＋FS 擋：`'5'次 … evidence gives this value as 5次/個` | **通過** | 通過 |
| publish：「量測期間室溫維持在 24.4 至 24.8 °C」引用 `溫度_C` 欄摘要 | FE 擋：bigram 覆蓋 0% | 通過（舊版只能引原始列） | 仍擋（未修，見下） |
| publish 失敗後照訊息改 `claim_matrix.json` 再 submit | `scope_violation`，要求把檔案還原 | — | 自動回到 claim_matrix 重驗，一路通過 |
| DOCX 圖表中文 | 標題、軸標籤全是方框（WenQuanYi 已安裝） | 同 | 正常 |
| 表格標題（照 authoring.md 範例寫「表 1　…」） | 「表 1. 表 1 各擺長…」 | — | 「表 1. 各擺長…」 |

為了在 HEAD 修正前過關，作者把句子改成（`report_head_before_with_workarounds.docx`）：

- 「每個擺長拉開約 10 度後放手，**每個擺長重複 5 次取平均**，每次量測 10 次擺動的總時間再除以 10 得週期。」——照來源語序重排。
- 「**溫度最小值 24.40 °C，最大值 24.80 °C**。」——原句「量測期間室溫維持在 24.4 至 24.8 °C 之間」被改成抄欄位摘要。
- 主張類型 `statistical` → `factual`（引用了文字來源的已知值）。

## Run 2　英文 business_report：2026 銷售通路檢討

來源：`sources/sales_2026.csv`（36 列；欄位 quarter, region, category, revenue_kusd, **units**, return_rate_pct）＋ `sources/ops_memo.md`。

| 步驟 | HEAD 修正前 | 修正後 |
| --- | --- | --- |
| prepare 自動交叉表 | 只有 `rows / share of rows`（三組各 33.33%），因為 `units` 欄被當成「計量單位欄」，整檔被判為混合單位，所有數值欄的平均／中位數都被拿掉 | 交叉表帶 revenue、units、return rate 的平均與中位數 |
| 自動 figure_plan | 4 張：「rows and 1 other measure by category after sort desc」等計數表、一張 36 列原始資料表 | 未被 outline 採用的建議圖不再要求刪除、也不再被建出來 |
| 「The support desk is staffed 7×24 …」（memo 寫 `7x24`） | FE 擋：`'24'and is not stated in the evidence (evidence states: 7x, 3minutes)` | 通過 |
| c7 混用 memo 與統計表、類型寫 qualitative | publish 才被 FA 擋 | `lint_artifacts` 階段就指出，訊息與 FA 一致 |

## Run 3　revise_existing：智慧電表期中報告改成 9 月進度

來源：`sources/midterm_report.docx`（base_document）＋ `september_update.csv` ＋ `field_notes.md`。

| 步驟 | HEAD 修正前 | 修正後 |
| --- | --- | --- |
| revision_plan 用 brief 與 revision.md 記載的 `retitle` | 擋：`1 unresolvable change(s)`（訊息不說是哪一條；細節在 validation_result 裡是 `Unknown change_type: 'retitle'`） | 通過，標題改為「第三季成果」 |
| 拿掉 retitle 後 publish | FA 擋 c4：`Claim does not appear in sentence_map`——c4 只出現在 revision_plan（文件實際內容），而 FA 只讀 section drafts 的 sentence_map，那些 drafts 在 revise 模式根本不會進文件 | revision_plan 的 claim 連結算數 |
| publish 的 render 驗證 | （修了上面兩個之後）`expected 1 embedded figure(s), found 0`：未採用的 starter 圖仍被建出來，revise 模式又無法放 `[FIGURE:]` | 未採用的建議圖不建，完成 |

## 8 種 profile 端到端 benchmark

`report_benchmarks_rerun_fixed.log`：修正後 `python scripts/run_report_benchmarks.py`
真跑 8/8 通過。`report_benchmarks_rerun_master.log`：同環境下未修正的 master 也 8/8。
兩者產生的封存檔逐檔比對只差在 job id 與 ledger hash；與倉庫內封存（Windows
`D:\` 路徑）的差異來自環境，所以封存沒有改寫，`--check` 照舊通過。

## 沒修的

- 「室溫」對「溫度_C」：FE 的中文 bigram 覆蓋是字面比對，同義詞換說法本來就在
  詞彙檢查的邊界外（AGENTS.md：No semantic layer）。放寬成「數字都對就不看詞」
  會讓「把溫度數字說成銷售額」這類對抗案例過關。
- 引用標註：每句自有筆記都標「（本研究整理，計算附件 C1）」，連「實驗目的」也指向
  「計算附件」。這是 4d501b8／2b5472a 的設計，改它會動到所有 profile 的成品與
  report-quality 封存，留給擁有者決定。
- 自動圖表標題與表頭用原始欄名（`週期_s(依擺長_cm)`、`擺長_cm`）；封面
  template_fields 在中文文件仍印英文鍵名（`Course Name:`、`Student Id:`）。
- 混合文字與統計證據的主張，類型必須是兩者的交集（通常 `factual`）。訊息清楚，未改。
- 同一欄的加總格式不一致（`965` 與 `825.10` 並列）。
