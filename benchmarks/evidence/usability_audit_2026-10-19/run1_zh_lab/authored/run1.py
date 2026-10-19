SRC = "/home/user/report-workflow/benchmarks/evidence/usability_audit_2026-10-19/run1_zh_lab/sources"
START = dict(prompt="寫一份普通物理實驗課的單擺實驗報告，用量測數據估算重力加速度",
    source_files=[{"path": f"{SRC}/pendulum_trials.csv", "role": "source_data"}, {"path": f"{SRC}/lab_notes.md", "role": "source_data"}],
    report_profile="engineering_lab_report", template_fields={"course_name": "普通物理實驗", "student_id": "B12345678"},
    title="單擺實驗：由週期與擺長估算重力加速度",
    preflight_confirmed=True,
    # exactly the record SKILL.md shows
    preflight_decisions={"confirmed_by_user": True, "install_decisions": {}, "feature_decisions": {"web_research": "skip", "notebook_sync": "skip"}})
DERIVATIONS = [{"id": "g_per_length", "op": "formula", "source": "pendulum_trials.csv", "row_label": "擺長_cm", "decimals": 2,
    "label": "各擺長推得的重力加速度",
    "formulas": [{"label": "週期平方", "expr": "週期_s*週期_s", "unit": "s²"},
                 {"label": "g", "expr": "4*3.14159265*3.14159265*(擺長_cm/100)/(週期_s*週期_s)", "unit": "m/s²"}], "inputs": {}}]
OBJ="~本實驗目的是量測"; THEO="~理論上小角度"; APP="~器材："; PROC="~步驟："; OPEN="~實驗室開放時間"; REF="~已知台北"; ERR="~誤差來源"
LEN="~擺長_cm 欄共"; PER="~週期_s 欄共"; TEMP="~溫度_C 欄共"; G="E_D_g_per_length"
CLAIMS = [
 dict(claim_id="c1", claim_text="本實驗目的是量測單擺週期與擺長的關係，並由週期平方與擺長的關係估算重力加速度 g。", claim_type="factual", evidence_ids=[OBJ], claim_role="background"),
 dict(claim_id="c2", claim_text="小角度單擺週期 T = 2π√(L/g)，T² 與 L 成正比，斜率為 4π²/g。", claim_type="factual", evidence_ids=[THEO], claim_role="background"),
 dict(claim_id="c3", claim_text="器材包括鐵架、細線、直徑 2.0 cm 鋼球、解析度 0.01 s 碼表與最小刻度 1 mm 捲尺。", claim_type="factual", evidence_ids=[APP], claim_role="supporting"),
 dict(claim_id="c4", claim_text="每個擺長量測 10 次擺動總時間後除以 10 得週期，並重複 5 次取平均。", claim_type="methodological", evidence_ids=[PROC], claim_role="supporting"),
 dict(claim_id="c5", claim_text="實驗室開放時間為 7x24 小時。", claim_type="factual", evidence_ids=[OPEN], claim_role="background"),
 dict(claim_id="c6", claim_text="擺長由 20 cm 增加到 80 cm 時，週期由 0.90 s 增加到 1.79 s。", claim_type="statistical", evidence_ids=[LEN, PER], claim_role="supporting"),
 dict(claim_id="c7", claim_text="七個擺長推得的重力加速度介於 9.75 至 9.86 m/s²。", claim_type="statistical", evidence_ids=[G], claim_role="primary"),
 dict(claim_id="c8", claim_text="擺長 50 cm 推得 g = 9.79 m/s²，與台北地區已知值 9.79 m/s² 相同。", claim_type="factual", evidence_ids=[G, REF], claim_role="primary"),
 dict(claim_id="c9", claim_text="量測期間室溫維持在 24.4 至 24.8 °C。", claim_type="statistical", evidence_ids=[TEMP], claim_role="supporting"),
 dict(claim_id="c10", claim_text="誤差來源包括人工按碼表約 0.2 s 的反應時間，以及擺角不完全是小角度。", claim_type="qualitative", evidence_ids=[ERR], claim_role="supporting", requires_hedged_wording=True),
 dict(claim_id="c11", claim_text="最短擺長 20 cm 推得的 g 為 9.75 m/s²，是七組中最低值。", claim_type="statistical", evidence_ids=[G], claim_role="supporting"),
]
OUTLINE = {
 "cover": {"claims": []}, "objectives": {"claims": ["c1"]}, "requirements": {"claims": ["c1"]}, "theory": {"claims": ["c2"]},
 "apparatus": {"claims": ["c3", "c5"]}, "procedure": {"claims": ["c4"]}, "data": {"claims": ["c6", "c9"], "figures": ["1"]},
 "calculations": {"claims": ["c7", "c11"]},
 "results_discussion": {"claims": ["c8", "c10", "c11"]},
 "conclusion": {"claims": ["c7", "c8"]},
 # what 02_outline_plan.md says: results_mode at sections.results.results_mode
 "results": {"claims": [], "extra": {"results_mode": "empirical"}},
}
OUTLINE_EXTRA = {"lab_spine": {"experiment_purpose": "由單擺週期與擺長估算 g", "variables": "自變數擺長(cm)，應變數週期(s)，控制變數擺角與溫度",
  "apparatus_procedure_basis": "實驗紀錄的器材與步驟", "measurement_basis": "量測數據表", "uncertainty_limitations": "碼表反應時間、擺角"}}
DRAFTS = {
 "cover": [["單擺實驗：由週期與擺長估算重力加速度"]],
 "objectives": [[("本實驗的目的是量測單擺週期與擺長的關係，並由週期平方與擺長的關係估算重力加速度 g。", ["c1"], [OBJ])]],
 "requirements": [[("為了估算 g，本實驗需要在不同擺長下量測週期，並以週期平方對擺長的關係計算重力加速度。", ["c1"], [OBJ])]],
 "theory": [[("小角度單擺的週期為 T = 2π√(L/g)，因此 T² 與 L 成正比，斜率為 4π²/g。", ["c2"], [THEO]),
             ("由此可知，只要量得各擺長的週期，就能以 g = 4π²L/T² 逐點估算重力加速度。", ["c2"], [THEO])]],
 "apparatus": [[("本實驗使用鐵架、細線、直徑 2.0 cm 的鋼球、解析度 0.01 s 的碼表，以及最小刻度 1 mm 的捲尺。", ["c3"], [APP]),
                ("實驗室開放時間為 7x24 小時，量測時段可自行安排。", ["c5"], [OPEN])]],
 "procedure": [[("每個擺長拉開約 10 度後放手，以碼表量測 10 次擺動的總時間，再除以 10 得到週期。", ["c4"], [PROC]),
                ("每個擺長重複量測 5 次並取平均，以降低單次按錶的誤差。", ["c4"], [PROC])]],
 "data": [[("擺長由 20 cm 增加到 80 cm 時，週期由 0.90 s 增加到 1.79 s，如圖 1 所示。", ["c6"], [LEN, PER], "measured")],
          ["[FIGURE:1]"],
          [("量測期間室溫維持在 24.4 至 24.8 °C 之間，溫度變化很小。", ["c9"], [TEMP], "measured")]],
 "calculations": [[("以 g = 4π²L/T² 逐一計算，七個擺長推得的重力加速度介於 9.75 至 9.86 m/s²，見表 1。", ["c7"], [G], "measured")],
                  ["[TABLE:E_D_g_per_length 表 1　各擺長的週期平方與推得的重力加速度]"],
                  [("其中最短擺長 20 cm 推得的 g 為 9.75 m/s²，是七組中的最低值。", ["c11"], [G], "measured")]],
 "results_discussion": [[("擺長 50 cm 推得 g = 9.79 m/s²，與台北地區已知值 9.79 m/s² 相同。", ["c8"], [G, REF], "hedged"),
                         ("最短擺長 20 cm 的結果 9.75 m/s² 偏低，可能是因為短擺的週期只有 0.90 s，人工按錶的反應時間相對影響較大。", ["c11", "c10"], [G, ERR])],
                        [("誤差來源可能包括人工按碼表約 0.2 s 的反應時間，以及擺角不完全是小角度。", ["c10"], [ERR])]],
 "conclusion": [[("七個擺長推得的重力加速度介於 9.75 至 9.86 m/s²，與台北地區已知值 9.79 m/s² 接近。", ["c7", "c8"], [G, REF], "hedged")]],
}
