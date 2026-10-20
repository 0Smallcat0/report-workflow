"""English quant_research_memo, first draft as written after reading the briefs."""
from pathlib import Path
import importlib.util
_s = importlib.util.spec_from_file_location("start", str(Path(__file__).resolve().with_name("start.py")))
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
START = _m.START
CSV = "momentum_backtest.csv"
DERIVATIONS = [
 {"id":"signal_r","op":"pearson_r","source":CSV,"x":"signal_z","y":"next_week_return_pct","decimals":2,"label":"Signal vs next-week return"},
 {"id":"signal_fit","op":"linear_fit","source":CSV,"x":"signal_z","y":"next_week_return_pct","decimals":2,"label":"Next-week return on signal"},
 {"id":"signal_r_bull","op":"pearson_r","source":CSV,"rows":"regime=bull","x":"signal_z","y":"next_week_return_pct","decimals":2,"label":"Signal vs return, bull weeks"},
 {"id":"signal_r_bear","op":"pearson_r","source":CSV,"rows":"regime=bear","x":"signal_z","y":"next_week_return_pct","decimals":2,"label":"Signal vs return, bear weeks"},
 {"id":"return_by_signal_band","source":CSV,"label":"Next-week return by signal band","group_by":{"column":"signal_z","buckets":[-3,0,1,3.5],"label":"Signal z band"},
  "measures":[{"op":"count","label":"Weeks"},{"op":"mean","column":"next_week_return_pct","label":"Mean next-week return (%)"},{"op":"share","rows":"next_week_return_pct>0","label":"Share of up weeks"}]},
 {"id":"high_minus_low","op":"formula","expr":"a - b","decimals":2,"unit":"pct points","label":"Mean return gap, z 1 to 3.5 vs z below 0",
  "inputs":{"a":{"table":"return_by_signal_band","column":"Mean next-week return (%)","row":"1-3.5"},"b":{"table":"return_by_signal_band","column":"Mean next-week return (%)","row":"-3-0"}}},
]
DESIGN="~Test design:"; REGIME="~Regime labels"; JT="~Jegadeesh and Titman"; LIMITS="~Known limits"
SIGNAL="~the signal_z column holds"; RET="~the next_week_return_pct column holds"; BY_REGIME="~regime breakdown"
R="E_D_signal_r"; FIT="E_D_signal_fit"; RB="E_D_signal_r_bull"; RBR="E_D_signal_r_bear"; BAND="E_D_return_by_signal_band"; GAP="E_D_high_minus_low"
CLAIMS = [
 dict(claim_id="c1", claim_text="Each Friday from week 1 to week 36 of 2026 the 20-day momentum signal was computed for an equal-weight basket of 11 sector ETFs and standardized to a z-score against its trailing 52-week history; the outcome is the basket's return over the following week, with no transaction costs.", claim_type="methodological", evidence_ids=[DESIGN], claim_role="supporting"),
 dict(claim_id="c2", claim_text="A week is labelled bull when the basket closed above its 200-day moving average on the signal date and bear otherwise.", claim_type="methodological", evidence_ids=[REGIME], claim_role="supporting"),
 dict(claim_id="c3", claim_text="The signal applies the cross-sectional momentum idea of Jegadeesh and Titman (1993) in time series to a single basket.", claim_type="qualitative", evidence_ids=[JT], claim_role="background"),
 dict(claim_id="c4", claim_text="The signal ranged from -2.77 to 3.42 over the 36 weeks, and next-week returns from -2.56% to 2.92%.", claim_type="statistical", evidence_ids=[SIGNAL, RET], claim_role="supporting"),
 dict(claim_id="c5", claim_text="The signal and the next-week return are positively correlated, r = 0.51 over 36 weeks.", claim_type="statistical", evidence_ids=[R], claim_role="primary"),
 dict(claim_id="c6", claim_text="Each one-unit rise in the signal goes with a 0.56 percentage point higher next-week return (intercept 0.07, R² = 0.26).", claim_type="statistical", evidence_ids=[FIT], claim_role="primary"),
 dict(claim_id="c7", claim_text="Weeks with a signal of 1 or more returned 1.59% on average the following week, against -0.46% for weeks below 0, a gap of 2.05 percentage points; all 7 high-signal weeks were up weeks.", claim_type="statistical", evidence_ids=[BAND, GAP], claim_role="primary"),
 dict(claim_id="c8", claim_text="The relation holds in both regimes: r = 0.42 in the 21 bull weeks and r = 0.85 in the 15 bear weeks.", claim_type="statistical", evidence_ids=[RB, RBR], claim_role="supporting"),
 dict(claim_id="c9", claim_text="Bull weeks returned 0.30% on average the following week against -0.02% for bear weeks, while the mean signal was -0.22 in bull weeks and 0.71 in bear weeks.", claim_type="statistical", evidence_ids=[BY_REGIME], claim_role="supporting"),
 dict(claim_id="c10", claim_text="36 weekly observations is a short sample, the weeks overlap with one rate-hiking cycle, and the regime label was assigned after the fact.", claim_type="factual", evidence_ids=[LIMITS], claim_role="supporting"),
]
OUTLINE = {
 "summary": {"claims": ["c5","c7"]},
 "question_and_data": {"claims": ["c1","c3","c4"]},
 "method": {"claims": ["c1","c2"]},
 "results": {"claims": ["c5","c6","c7"], "figures": ["sig_scatter"]},
 "robustness": {"claims": ["c8","c9"]},
 "limitations": {"claims": ["c10"]},
}
def FIGURE_PLAN_EDIT(run):
    import json
    led=[json.loads(l) for l in open(run / "evidence_ledger.jsonl", encoding="utf-8")]
    rows=[(r["evidence_id"],json.loads(r["content"])) for r in led if r.get("source_file_name","")==CSV and r["content"].startswith("{")]
    p = run / "section_drafts" / "figure_plan.json"
    fp = json.load(open(p, encoding="utf-8")) if p.exists() else {"figures": []}
    fp["figures"] = [f for f in fp["figures"] if f.get("figure_id") != "sig_scatter"]
    fp["figures"].append({"figure_id":"sig_scatter","figure_type":"scatter","title":"Next-week basket return against the momentum signal (36 weeks)","xlabel":"Signal (z-score)","ylabel":"Next-week return (%)",
     "data":{"x":[float(r["signal_z"]) for _,r in rows],"y":[float(r["next_week_return_pct"]) for _,r in rows]},"output_format":"png","section_id":"results",
     "source_evidence_ids":[e for e,_ in rows],"chart_selection_reason":"Two continuous variables per week"})
    json.dump(fp, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
DRAFTS = {
 "summary": [[("The momentum signal has predicted next-week basket returns in this sample: the two are positively correlated, r = 0.51 over 36 weeks.", ["c5"], [R], "measured"),
   ("Weeks with a signal of 1 or more returned 1.59% on average the following week, against -0.46% for weeks below 0, a gap of 2.05 percentage points; all 7 high-signal weeks were up weeks.", ["c7"], [BAND, GAP], "measured"),
   "The sample is short, so the result supports a paper-trading period rather than capital."]],
 "question_and_data": [["The question is whether the desk's 20-day momentum signal says anything about the following week.",
   ("The signal applies the cross-sectional momentum idea of Jegadeesh and Titman (1993) in time series to a single basket.", ["c3"], [JT]),
   ("Each Friday from week 1 to week 36 of 2026 the 20-day momentum signal was computed for an equal-weight basket of 11 sector ETFs and standardized to a z-score against its trailing 52-week history; the outcome is the basket's return over the following week, with no transaction costs.", ["c1"], [DESIGN]),
   ("The signal ranged from -2.77 to 3.42 over the 36 weeks, and next-week returns from -2.56% to 2.92%.", ["c4"], [SIGNAL, RET], "measured")]],
 "method": [[("A week is labelled bull when the basket closed above its 200-day moving average on the signal date and bear otherwise.", ["c2"], [REGIME]),
   "The relation is measured three ways: Pearson's r, a least-squares line of next-week return on the signal, and mean returns across signal bands cut at 0 and 1.",
   "The same correlation is then recomputed inside each regime."]],
 "results": [[("The signal and the next-week return are positively correlated, r = 0.51 over 36 weeks.", ["c5"], [R], "measured"),
   ("Each one-unit rise in the signal goes with a 0.56 percentage point higher next-week return (intercept 0.07, R² = 0.26).", ["c6"], [FIT], "measured")],
   ["[FIGURE:sig_scatter]"],
   [("Weeks with a signal of 1 or more returned 1.59% on average the following week, against -0.46% for weeks below 0, a gap of 2.05 percentage points; all 7 high-signal weeks were up weeks.", ["c7"], [BAND, GAP], "measured")],
   ["[TABLE:E_D_return_by_signal_band Table 1. Next-week return by signal band]"]],
 "robustness": [[("The relation holds in both regimes: r = 0.42 in the 21 bull weeks and r = 0.85 in the 15 bear weeks.", ["c8"], [RB, RBR], "measured"),
   ("Bull weeks returned 0.30% on average the following week against -0.02% for bear weeks, while the mean signal was -0.22 in bull weeks and 0.71 in bear weeks.", ["c9"], [BY_REGIME], "measured"),
   "So the signal is not simply picking out the bull regime."]],
 "limitations": [[("36 weekly observations is a short sample, the weeks overlap with one rate-hiking cycle, and the regime label was assigned after the fact.", ["c10"], [LIMITS]),
   "A correlation of this size over 36 points is not a forecast of live returns after costs."]],
}
