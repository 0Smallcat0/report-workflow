from pathlib import Path
HERE = Path(__file__).resolve().parent
SRC = str(HERE.parent / "sources")
START = dict(prompt="幫我寫一份提案給區公所：建議社區圖書館週二到週五延長開放到晚上九點，說明需求、經費與風險",
    source_files=[{"path": f"{SRC}/入館人次_2026.csv", "role": "source_data"}, {"path": f"{SRC}/問卷結果.csv", "role": "source_data"}, {"path": f"{SRC}/經費與人力估算.md", "role": "source_data"}],
    report_profile="proposal", title="延長社區圖書館週間開放時間提案", preflight_confirmed=True,
    preflight_decisions={"confirmed_by_user": True, "install_decisions": {}, "feature_decisions": {"web_research": "skip", "notebook_sync": "skip"}})
DERIVATIONS = [
 {"id":"support_by_group","op":"formula","source":"問卷結果.csv","row_label":"身分","decimals":1,"label":"各身分支持延長到21點的比例","formulas":[{"label":"支持比例","expr":"希望延長到21點人數/填答人數*100","unit":"%"}],"inputs":{}},
 {"id":"resp_total","source":"問卷結果.csv","op":"sum","column":"填答人數","label":"填答總人數"},
 {"id":"support_total","source":"問卷結果.csv","op":"sum","column":"希望延長到21點人數","label":"支持延長總人數"},
 {"id":"support_rate","op":"formula","expr":"s/r*100","inputs":{"s":"support_total","r":"resp_total"},"unit":"%","decimals":1,"label":"整體支持比例"},
 {"id":"by_slot","source":"入館人次_2026.csv","group_by":{"column":"時段"},"measures":[{"op":"mean","column":"平均每日入館人次","label":"平均每日入館人次"}]},
 {"id":"evening_ratio","op":"ratio","source":"by_slot","column":"平均每日入館人次","numerator_group":"18-20","denominator_group":"09-12","decimals":2},
]
OPEN="~目前開放時間"; HRS="~每週多開放"; STAFF="~人力："; ELEC="~電費與空調"; TOT="~合計全年增加支出"; RISK="~風險："; MONTH="~月份 分組交叉表"
SUP=["E_D_resp_total","E_D_support_total","E_D_support_rate"]; SLOT=["E_D_by_slot","E_D_evening_ratio"]
CLAIMS = [
 dict(claim_id="c1", claim_text="圖書館目前週二至週日 09:00 至 20:00 開放，週一休館。", claim_type="factual", evidence_ids=[OPEN]),
 dict(claim_id="c2", claim_text="18-20 時段平均每日入館 64.00 人次，是 09-12 時段 40.78 人次的 1.57 倍。", claim_type="statistical", evidence_ids=SLOT),
 dict(claim_id="c3", claim_text="15-18 時段平均每日入館 69.44 人次，是四個時段中最高。", claim_type="statistical", evidence_ids=["E_D_by_slot"]),
 dict(claim_id="c4", claim_text="260 名填答者中有 174 人希望延長到 21 點，佔 66.9%。", claim_type="statistical", evidence_ids=SUP),
 dict(claim_id="c5", claim_text="上班族支持比例 83.0%、學生 70.9%，退休者僅 22.5%。", claim_type="statistical", evidence_ids=["E_D_support_by_group"]),
 dict(claim_id="c6", claim_text="週二至週五延長到 21:00，每週多開放 4 小時，全年約 208 小時。", claim_type="factual", evidence_ids=[HRS]),
 dict(claim_id="c7", claim_text="每晚需 1 名館員與 1 名工讀生，合計每小時 516 元，全年人事費約 107,328 元。", claim_type="factual", evidence_ids=[STAFF]),
 dict(claim_id="c8", claim_text="電費與空調每延長 1 小時約 85 元，全年約 17,680 元。", claim_type="factual", evidence_ids=[ELEC]),
 dict(claim_id="c9", claim_text="全年增加支出約 125,008 元，低於區公所補助上限 150,000 元。", claim_type="factual", evidence_ids=[TOT]),
 dict(claim_id="c10", claim_text="20:00 後周邊公車班距拉長為 30 分鐘，夜間保全費用尚未估算。", claim_type="qualitative", evidence_ids=[RISK], requires_hedged_wording=True),
 dict(claim_id="c11", claim_text="1 月至 9 月各月平均每日入館人次介於 54.25 至 58.75，需求沒有明顯季節起伏。", claim_type="statistical", evidence_ids=[MONTH]),
]
OUTLINE = {
 "executive_summary": {"claims": ["c2","c4","c9"]},
 "problem_statement": {"claims": ["c1","c2","c3","c4","c5","c11"], "figures": ["9"]},
 "objectives": {"claims": ["c6"]}, "proposed_approach": {"claims": ["c6","c7"]}, "scope_deliverables": {"claims": ["c6"]},
 "budget_resources": {"claims": ["c7","c8","c9"]}, "risks": {"claims": ["c10","c5"]},
}
def FIGURE_PLAN_EDIT(run):
    import json
    p = run / "section_drafts" / "figure_plan.json"
    fp = json.load(open(p, encoding="utf-8")) if p.exists() else {"figures": []}
    fp["figures"].append({"figure_id":"9","figure_type":"bar","title":"各時段平均每日入館人次（2026 年 1–9 月）","xlabel":"時段","ylabel":"人次",
      "data":{"labels":["09-12","12-15","15-18","18-20"],"series":[{"name":"平均每日入館人次","values":[40.78,51.44,69.44,64.0]}]},
      "output_format":"png","section_id":"problem_statement","source_evidence_ids":["E_D_by_slot"],"chart_selection_reason":"四個時段的平均入館人次直接比較"})
    json.dump(fp, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    o = json.load(open(run / "outline.json", encoding="utf-8"))
    waive = {}
    for line in open(run / "evidence_ledger.jsonl", encoding="utf-8"):
        e = json.loads(line)
        if "時段 分組交叉表" in e.get("content", ""):
            waive[e["evidence_id"]] = "與報告引用的時段平均重複"
    if waive:
        o["unused_derived_evidence"] = waive
    json.dump(o, open(run / "outline.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
DRAFTS = {
 "executive_summary": [["本提案建議社區圖書館自 2027 年起，週二至週五的開放時間由 20:00 延長到 21:00。",
   ("今年 1 至 9 月，18-20 時段平均每日入館 64.00 人次，是 09-12 時段 40.78 人次的 1.57 倍。", ["c2"], SLOT, "measured"),
   ("260 名填答者中有 174 人希望延長到 21 點，佔 66.9%。", ["c4"], SUP, "measured"),
   ("全年增加支出約 125,008 元，低於區公所補助上限 150,000 元。", ["c9"], [TOT]),
   "因此，本館請區公所核准以社區活動補助支應這筆經費。"]],
 "problem_statement": [
   [("圖書館目前週二至週日 09:00 至 20:00 開放，週一休館。", ["c1"], [OPEN]),
    ("傍晚是全天最擁擠的時段：15-18 時段平均每日入館 69.44 人次，是四個時段中最高。", ["c3"], ["E_D_by_slot"], "measured"),
    ("閉館前的 18-20 時段仍有 64.00 人次，是 09-12 時段的 1.57 倍，如圖 1 所示。", ["c2"], SLOT, "measured")],
   ["[FIGURE:9]"],
   [("這不是季節性現象：1 月至 9 月各月平均每日入館人次介於 54.25 至 58.75，需求沒有明顯季節起伏。", ["c11"], [MONTH], "measured")],
   ["問卷結果也指向同一個方向。", ("260 名填答者中有 174 人希望延長到 21 點，佔 66.9%。", ["c4"], SUP, "measured"),
    ("支持者集中在白天要上班上課的人：上班族支持比例 83.0%、學生 70.9%，退休者僅 22.5%。", ["c5"], ["E_D_support_by_group"], "measured")],
   ["[TABLE:E_D_support_by_group 各身分支持延長到 21 點的比例]"]],
 "objectives": [[("本提案的目標是在週二至週五延長到 21:00，每週多開放 4 小時，全年約 208 小時。", ["c6"], [HRS]), "延長的一小時主要服務下班、下課後才能到館的讀者。"]],
 "proposed_approach": [["延長時段沿用現有服務，不新增活動，以控制成本。", ("每晚需 1 名館員與 1 名工讀生，合計每小時 516 元，全年人事費約 107,328 元。", ["c7"], [STAFF]),
   ("排班上，週二至週五延長到 21:00，每週多開放 4 小時，全年約 208 小時。", ["c6"], [HRS])]],
 "scope_deliverables": [["範圍限於週二至週五；週末與週一維持現狀。", ("交付項目是全年約 208 小時的延長開放，每週多開放 4 小時。", ["c6"], [HRS])]],
 "budget_resources": [[("人力是最大的支出：每晚需 1 名館員與 1 名工讀生，合計每小時 516 元，全年人事費約 107,328 元。", ["c7"], [STAFF]),
   ("電費與空調每延長 1 小時約 85 元，全年約 17,680 元。", ["c8"], [ELEC]),
   ("兩者合計，全年增加支出約 125,008 元，低於區公所補助上限 150,000 元。", ["c9"], [TOT]), "差額可作為尚未估算的保全費用預備金。"]],
 "risks": [["最大的風險在交通與安全。", ("20:00 後周邊公車班距拉長為 30 分鐘，夜間保全費用尚未估算。", ["c10"], [RISK]),
   ("退休者的支持比例僅 22.5%，延長時段對這群讀者幫助有限。", ["c5"], ["E_D_support_by_group"], "measured"), "因應方式是先試辦一季，並在開辦前向保全公司取得報價。"]],
}
