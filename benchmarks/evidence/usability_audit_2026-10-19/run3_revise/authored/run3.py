import json
RETRY_FULL_DECISIONS=False
from pathlib import Path
SRC = str(Path(__file__).resolve().parent.parent / "sources")
START = dict(prompt="把期中報告更新成 9 月底的進度：用新的安裝數、回傳成功率與告警數修正數字，其他文字盡量保留",
    source_files=[{"path": f"{SRC}/midterm_report.docx", "role": "base_document"}, {"path": f"{SRC}/september_update.csv", "role": "source_data"}, {"path": f"{SRC}/field_notes.md", "role": "source_data"}],
    report_profile="business_report", task_intent="revise_existing",
    preflight_confirmed=True,
    preflight_decisions={"confirmed_by_user": True, "install_decisions": {}, "feature_decisions": {"web_research": "skip", "notebook_sync": "skip"}})
DERIVATIONS = [{"id": "alerts_total", "source": "september_update.csv", "op": "sum", "column": "告警數_件"},
               {"id": "confirmed_total", "source": "september_update.csv", "op": "sum", "column": "確認異常_件"}]
N='~"區域": "北區"'; M='~"區域": "中區"'; S='~"區域": "南區"'; TOT="~累計安裝 1,450"; RELAY="~訊號中繼站"; OPS="~7x24"; PRIV="~12 通"
AL="E_D_alerts_total"; CF="E_D_confirmed_total"
CLAIMS = [
 dict(claim_id="c1", claim_text="截至 9 月底，累計安裝 1,450 具電表。", claim_type="factual", evidence_ids=[TOT], claim_role="primary"),
 dict(claim_id="c2", claim_text="北區安裝 620 具、中區安裝 480 具、南區安裝 350 具。", claim_type="factual", evidence_ids=[N, M, S]),
 dict(claim_id="c3", claim_text="南區新增兩座訊號中繼站後，回傳成功率由 91.0% 提升到 94.1%。", claim_type="factual", evidence_ids=[RELAY], claim_role="primary"),
 dict(claim_id="c4", claim_text="三區告警共 64 件，其中 45 件經確認為真實異常。", claim_type="statistical", evidence_ids=[AL, CF], claim_role="primary"),
 dict(claim_id="c5", claim_text="維運團隊提供 7×24 小時的監控服務。", claim_type="factual", evidence_ids=[OPS]),
 dict(claim_id="c6", claim_text="客服在 7 至 9 月共接到 12 通隱私相關詢問。", claim_type="factual", evidence_ids=[PRIV]),
]
OUTLINE = {
 "executive_summary": {"claims": ["c1", "c4"]},
 "findings": {"claims": ["c1", "c2", "c3", "c4", "c5"]},
 "limitations": {"claims": ["c3", "c6"]},
 "recommendations": {"claims": ["c1"]},
}
DRAFTS = {
 "executive_summary": [[("截至 9 月底，累計安裝 1,450 具電表。", ["c1"], [TOT])]],
 "findings": [[("北區安裝 620 具、中區安裝 480 具、南區安裝 350 具。", ["c2"], [N, M, S])]],
 "limitations": [[("客服在 7 至 9 月共接到 12 通隱私相關詢問。", ["c6"], [PRIV])],[("南區新增兩座訊號中繼站後，回傳成功率由 91.0% 提升到 94.1%。", ["c3"], [RELAY])]],
 "recommendations": [[("截至 9 月底，累計安裝 1,450 具電表。", ["c1"], [TOT])]],
}
def REVISION(run, resolve, contract, ledger):
    ch = [
     dict(section_id="摘要", change_type="replace", original_text="截至 6 月底，已安裝 1,200 具電表，資料回傳成功率為 97.5%。",
          new_text="截至 9 月底，已累計安裝 1,450 具電表。", claim_ids=["c1"], evidence_ids=[resolve(TOT)]),
     dict(section_id="期中成果", change_type="replace", original_text="截至 6 月底，北區安裝 500 具、中區安裝 400 具、南區安裝 300 具，合計 1,200 具。",
          new_text="截至 9 月底，北區安裝 620 具、中區安裝 480 具、南區安裝 350 具，合計 1,450 具。", claim_ids=["c1", "c2"], evidence_ids=[resolve(TOT), resolve(N), resolve(M), resolve(S)]),
     dict(section_id="期中成果", change_type="replace", original_text="資料回傳成功率為 97.5%，異常用電告警共 42 件，其中 30 件經現場確認為真實異常。",
          new_text="異常用電告警共 64 件，其中 45 件經現場確認為真實異常。", claim_ids=["c4"], evidence_ids=["E_D_alerts_total", "E_D_confirmed_total"]),
     dict(section_id="問題與風險", change_type="replace", original_text="南區部分老舊社區的訊號覆蓋不足，導致回傳成功率偏低。",
          new_text="南區部分老舊社區的訊號覆蓋不足；8 月新增兩座訊號中繼站後，回傳成功率由 91.0% 提升到 94.1%。", claim_ids=["c3"], evidence_ids=[resolve(RELAY)]),
     dict(section_id="問題與風險", change_type="replace", original_text="此外，部分用戶對資料隱私仍有疑慮。",
          new_text="此外，部分用戶對資料隱私仍有疑慮，客服在 7 至 9 月共接到 12 通相關詢問。", claim_ids=["c6"], evidence_ids=[resolve(PRIV)]),
     dict(section_id="期中成果", change_type="retitle", new_text="第三季成果"),
    ]
    json.dump({"_contract": contract(), "changes": ch}, open(run / "revision_plan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# c5 (7×24, already in the base document) is carried by no change and no draft;
# a claim nobody writes is dropped by the author, as FA asks.
CLAIMS=[c for c in CLAIMS if c["claim_id"]!="c5"]
OUTLINE["findings"]["claims"]=["c1","c2","c3","c4"]
