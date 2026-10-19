SRC = "/home/user/report-workflow/benchmarks/evidence/usability_audit_2026-10-19/run2_en_business/sources"
START = dict(prompt="Write a business report for leadership on 2026 sales by region and category: should Software get more marketing budget next year, and which region is underperforming?",
    source_files=[{"path": f"{SRC}/sales_2026.csv", "role": "source_data"}, {"path": f"{SRC}/ops_memo.md", "role": "source_data"}],
    report_profile="business_report", title="2026 Channel Review: Region and Category Performance",
    preflight_confirmed=True,
    preflight_decisions={"confirmed_by_user": True, "install_decisions": {}, "feature_decisions": {"web_research": "skip", "notebook_sync": "skip"}})
DERIVATIONS = [
 {"id": "rev_region", "source": "sales_2026.csv", "label": "Revenue and returns by region", "group_by": {"column": "region", "label": "Region"},
  "measures": [{"op": "sum", "column": "revenue_kusd", "label": "Revenue (kUSD)"}, {"op": "mean", "column": "return_rate_pct", "label": "Mean return rate (%)"}]},
 {"id": "rev_category", "source": "sales_2026.csv", "label": "Revenue and returns by category", "group_by": {"column": "category", "label": "Category"},
  "measures": [{"op": "sum", "column": "revenue_kusd", "label": "Revenue (kUSD)"}, {"op": "mean", "column": "return_rate_pct", "label": "Mean return rate (%)"}]},
 {"id": "rev_quarter", "source": "sales_2026.csv", "label": "Revenue by quarter", "group_by": {"column": "quarter", "label": "Quarter"},
  "measures": [{"op": "sum", "column": "revenue_kusd", "label": "Revenue (kUSD)"}]},
]
REG="E_D_rev_region"; CAT="E_D_rev_category"; QTR="E_D_rev_quarter"
DESK="~support desk is staffed"; DMG="~60% of hardware returns"; STORES="~opened two new stores"; ASK="~Leadership wants to know"; PACK="~packaging supplier"
CLAIMS = [
 dict(claim_id="c1", claim_text="Revenue across Q1-Q3 2026 totalled 3,430.90 kUSD, of which Hardware brought 1,592.20 kUSD.", claim_type="statistical", evidence_ids=[CAT], claim_role="primary"),
 dict(claim_id="c2", claim_text="Software earned 1,044 kUSD and had the lowest mean return rate of the three categories at 1.11%.", claim_type="statistical", evidence_ids=[CAT], claim_role="primary"),
 dict(claim_id="c3", claim_text="South had the lowest revenue of the four regions at 814.80 kUSD, against 965 kUSD in North.", claim_type="statistical", evidence_ids=[REG], claim_role="primary"),
 dict(claim_id="c4", claim_text="Quarterly revenue rose from 1,082.50 kUSD in 2026-Q1 to 1,197.20 kUSD in 2026-Q3.", claim_type="statistical", evidence_ids=[QTR], claim_role="supporting"),
 dict(claim_id="c5", claim_text="Hardware's mean return rate of 2.80% is more than double Software's 1.11%.", claim_type="statistical", evidence_ids=[CAT], claim_role="supporting"),
 dict(claim_id="c6", claim_text="The logistics team estimates that 60% of hardware returns cite damaged packaging.", claim_type="qualitative", evidence_ids=[DMG], requires_hedged_wording=True),
 dict(claim_id="c7", claim_text="North opened two new stores in Q2 2026, so part of its lead may come from store count rather than store performance.", claim_type="qualitative", evidence_ids=[STORES, REG], requires_hedged_wording=True),
 dict(claim_id="c8", claim_text="The support desk is staffed 7×24 and answers within 3 minutes on average.", claim_type="factual", evidence_ids=[DESK]),
 dict(claim_id="c9", claim_text="A packaging supplier trial under evaluation costs 45 kUSD per quarter.", claim_type="factual", evidence_ids=[PACK]),
 dict(claim_id="c10", claim_text="West had the highest mean return rate of the four regions at 1.90%.", claim_type="statistical", evidence_ids=[REG], claim_role="supporting"),
 dict(claim_id="c11", claim_text="The data cover three quarters only, 2026-Q1 to 2026-Q3, so a full-year comparison is not possible.", claim_type="statistical", evidence_ids=[QTR]),
]
OUTLINE = {
 "executive_summary": {"claims": ["c1", "c2", "c3"]},
 "findings": {"claims": ["c1", "c2", "c3", "c4", "c5", "c10", "c8"]},
 "limitations": {"claims": ["c6", "c7", "c11"]},
 "recommendations": {"claims": ["c2", "c3", "c9"]},
}
# the three auto tables (row counts of a balanced design) have to be waived by id
def _waive():
    return {}
OUTLINE_EXTRA = {}
DRAFTS = {
 "executive_summary": [[("Revenue across the first three quarters of 2026 totalled 3,430.90 kUSD, and Hardware contributed 1,592.20 kUSD of it.", ["c1"], [CAT], "measured"),
                        ("Software earned 1,044 kUSD with the lowest mean return rate of any category, 1.11%, which makes it the better candidate for extra marketing budget.", ["c2"], [CAT], "measured"),
                        ("South is the weakest region at 814.80 kUSD, against 965 kUSD in North.", ["c3"], [REG], "measured")]],
 "findings": [[("Hardware is the largest category, 1,592.20 kUSD of the 3,430.90 kUSD total.", ["c1"], [CAT], "measured"),
               ("Its mean return rate of 2.80% is more than double Software's 1.11%.", ["c5"], [CAT], "measured")],
              ["[TABLE:E_D_rev_category Revenue and mean return rate by product category, Q1-Q3 2026]"],
              [("By region, North leads at 965 kUSD and South trails at 814.80 kUSD.", ["c3"], [REG], "measured"),
               ("West has the highest mean return rate of the four regions, 1.90%.", ["c10"], [REG], "measured")],
              ["[TABLE:E_D_rev_region Revenue and mean return rate by region, Q1-Q3 2026]"],
              [("Revenue grew every quarter, from 1,082.50 kUSD in 2026-Q1 to 1,197.20 kUSD in 2026-Q3.", ["c4"], [QTR], "measured"),
               ("Service levels are not a constraint: the support desk is staffed 7×24 and answers within 3 minutes on average.", ["c8"], [DESK])]],
 "limitations": [[("The logistics team estimates that 60% of hardware returns cite damaged packaging, so the Hardware return gap may be a shipping problem rather than a product one.", ["c6"], [DMG])],
                 [("North opened two new stores in Q2 2026, so part of its lead over South may reflect store count rather than store performance.", ["c7"], [STORES, REG])],
                 [("The data cover three quarters only, 2026-Q1 to 2026-Q3, so a full-year comparison is not possible.", ["c11"], [QTR])]],
 "recommendations": [[("Software should receive more marketing budget next year: it earned 1,044 kUSD with the lowest return rate, 1.11%.", ["c2"], [CAT])],
                     [("South is the underperforming region, with 814.80 kUSD of revenue, and should be reviewed first.", ["c3"], [REG])],
                     [("Before changing Hardware's budget, run the packaging supplier trial, which costs 45 kUSD per quarter.", ["c9"], [PACK])]],
}
RETRY_FULL_DECISIONS=False
