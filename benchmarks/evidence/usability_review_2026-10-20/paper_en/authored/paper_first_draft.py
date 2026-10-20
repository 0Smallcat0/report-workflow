from pathlib import Path
HERE = Path(__file__).resolve().parent
SRC = str(HERE.parent / "sources")
START = dict(prompt="Write a short academic paper for my stats course on whether students who sleep more score higher on the midterm, using my survey data",
    source_files=[{"path": f"{SRC}/sleep_survey.csv", "role": "source_data"}, {"path": f"{SRC}/background_notes.md", "role": "source_data"}],
    report_profile="academic_paper", title="Sleep Duration and Midterm Performance in an Introductory Statistics Course",
    author_block="Lin Chen", affiliation_block="Department of Statistics", preflight_confirmed=True,
    preflight_decisions={"confirmed_by_user": True, "install_decisions": {}, "feature_decisions": {"web_research": "skip", "notebook_sync": "skip"}})
DERIVATIONS = [
 {"id":"score_by_sleep","source":"sleep_survey.csv","label":"Midterm score by nightly sleep band","group_by":{"column":"sleep_hours","buckets":[4,6,7.5,9],"label":"Sleep band (h)"},
  "measures":[{"op":"count","label":"Students"},{"op":"mean","column":"exam_score","label":"Mean score"},{"op":"median","column":"exam_score","label":"Median score"},{"op":"mean","column":"study_hours_week","label":"Mean study hours"}]},
 {"id":"gap_high_low","op":"formula","expr":"a - b","label":"Mean score gap, 7.5-9 h vs 4-6 h sleepers","unit":"points","decimals":2,
  "inputs":{"a":{"table":"score_by_sleep","column":"Mean score","row":"7.5-9"},"b":{"table":"score_by_sleep","column":"Mean score","row":"4-6"}}},
]
W="~Walker (2017"; O="~Okano"; M="~Survey method"; L="~Limitations noted"; ROWS="~the file holds 40"; SLEEP="~the sleep_hours column"; STUDY="~the study_hours_week column"; SCORE="~the exam_score column"
G=["E_D_score_by_sleep","E_D_gap_high_low"]
CLAIMS = [
 dict(claim_id="c1", claim_text="Walker (2017) argues that sleep after learning consolidates memory.", claim_type="qualitative", evidence_ids=[W], claim_role="background"),
 dict(claim_id="c2", claim_text="Okano et al. (2019) found that sleep quality and duration over the month before exams explained about 25% of the variance in grades of 88 MIT students.", claim_type="factual", evidence_ids=[O], claim_role="background"),
 dict(claim_id="c3", claim_text="40 first- and second-year undergraduates self-reported average nightly sleep over the two weeks before the midterm, and midterm scores were taken from the gradebook.", claim_type="methodological", evidence_ids=[M, ROWS], claim_role="supporting"),
 dict(claim_id="c4", claim_text="Nightly sleep ranged from 4.50 to 8.80 hours, with a median of 6.70 hours.", claim_type="statistical", evidence_ids=[SLEEP], claim_role="supporting"),
 dict(claim_id="c5", claim_text="Students sleeping 7.50 to 9 hours averaged 87.82 on the midterm, against 74.54 for those sleeping 4 to 6 hours, a gap of 13.28 points.", claim_type="statistical", evidence_ids=G, claim_role="primary"),
 dict(claim_id="c6", claim_text="Mean weekly study hours were similar across sleep bands, 7.85 for the 4 to 6 hour band and 8.19 for the 7.50 to 9 hour band, so study time does not explain the score gap.", claim_type="statistical", evidence_ids=["E_D_score_by_sleep", STUDY], claim_role="primary"),
 dict(claim_id="c7", claim_text="Midterm scores ranged from 67 to 98 with a median of 82.50.", claim_type="statistical", evidence_ids=[SCORE], claim_role="supporting"),
 dict(claim_id="c8", claim_text="Sleep was self-reported, the sample is one course at one university, and students who slept more may differ in other ways such as fewer part-time job hours.", claim_type="methodological", evidence_ids=[L], claim_role="supporting"),
]
OUTLINE = {
 "abstract": {"claims": ["c5","c6"]}, "introduction": {"claims": ["c1","c2"]}, "research_scope": {"claims": ["c3"]},
 "methods": {"claims": ["c3","c4"]}, "results": {"claims": ["c4","c5","c7"], "figures": ["2"], "extra": {"results_mode": "empirical"}},
 "discussion": {"claims": ["c6","c2"]}, "limitations": {"claims": ["c8"]}, "conclusion": {"claims": ["c5"]}, "references": {"claims": []},
}
OUTLINE_EXTRA = {"paper_spine": {"problem":"Whether students who sleep more before a midterm score higher","gap":"Prior work studied MIT students; this course has not been measured","objective":"Compare midterm scores across self-reported sleep bands","contribution":"A 13.28-point gap between the longest and shortest sleepers not explained by study time","method_basis":"Survey of 40 students joined to gradebook scores, grouped by sleep band","main_limitation":"Self-reported sleep, one course, observational"}}
def FIGURE_PLAN_EDIT(run):
    import json
    led=[json.loads(l) for l in open(run / "evidence_ledger.jsonl", encoding="utf-8")]
    rows=[(r["evidence_id"],json.loads(r["content"])) for r in led if r.get("source_file_name","").endswith(".csv") and r["content"].startswith("{")]
    p = run / "section_drafts" / "figure_plan.json"
    fp = json.load(open(p, encoding="utf-8")) if p.exists() else {"figures": []}
    fp["figures"] = [f for f in fp["figures"] if f.get("figure_id") != "2"]
    fp["figures"].append({"figure_id":"2","figure_type":"scatter","title":"Midterm score against average nightly sleep (n = 40)","xlabel":"Average nightly sleep (hours)","ylabel":"Midterm score",
     "data":{"x":[float(r["sleep_hours"]) for _,r in rows],"y":[float(r["exam_score"]) for _,r in rows]},"output_format":"png","section_id":"results",
     "source_evidence_ids":[e for e,_ in rows],"chart_selection_reason":"Two continuous variables per student"})
    json.dump(fp, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
A = lambda t: [t]
DRAFTS = {
 "abstract": [A("**Background:** Students are often told that sleep matters for exam performance, and laboratory work links sleep after learning to memory consolidation. Whether the link is visible in an ordinary course, where students choose how long they sleep and how long they study, is less often checked with the course's own data."),
   A("**Objective:** We asked whether students in one introductory statistics course who reported more nightly sleep before the midterm also scored higher on it."),
   A("**Methods:** Forty first- and second-year undergraduates reported their average nightly sleep over the two weeks before the midterm and their weekly study hours. Midterm scores were taken from the gradebook with consent. Students were grouped into three sleep bands, and mean scores and mean study hours were compared across bands."),
   A("**Principal Findings:** Students who slept 7.5 to 9 hours averaged 87.82 points, against 74.54 for those who slept 4 to 6 hours, a gap of 13.28 points. Mean weekly study hours were close across the bands, 7.85 and 8.19 hours, so the gap is not explained by study time."),
   A("**Significance:** The size of the gap in a single ordinary course suggests that sleep deserves a place in study advice, although a self-reported, observational sample of one course cannot show that more sleep causes higher scores.")],
 "introduction": [["Advice to students before an exam usually concerns study time, but a growing literature points to sleep as well.",
   ("Walker (2017) argues that sleep after learning consolidates memory.", ["c1"], [W]),
   ("In a field setting, Okano et al. (2019) found that sleep quality and duration over the month before exams explained about 25% of the variance in grades of 88 MIT students.", ["c2"], [O]),
   "This paper asks whether a similar pattern appears in a smaller, ordinary course."]],
 "research_scope": [["The study covers a single introductory statistics course.",
   ("Forty first- and second-year undergraduates self-reported average nightly sleep over the two weeks before the midterm, and midterm scores were taken from the gradebook.", ["c3"], [M, ROWS]),
   "The question is descriptive: do scores differ across sleep bands, and does study time account for any difference."]],
 "methods": [[("Forty first- and second-year undergraduates self-reported average nightly sleep over the two weeks before the midterm, and midterm scores were taken from the gradebook.", ["c3"], [M, ROWS]),
   ("Nightly sleep ranged from 4.50 to 8.80 hours, with a median of 6.70 hours.", ["c4"], [SLEEP], "measured"),
   "Students were grouped into bands of 4 to 6, 6 to 7.5 and 7.5 to 9 hours, and the mean and median score and the mean weekly study hours were computed for each band."]],
 "results": [[("Midterm scores ranged from 67 to 98 with a median of 82.50.", ["c7"], [SCORE], "measured"),
   ("Scores rose with sleep: students sleeping 7.50 to 9 hours averaged 87.82 on the midterm, against 74.54 for those sleeping 4 to 6 hours, a gap of 13.28 points.", ["c5"], G, "measured")],
   ["[TABLE:E_D_score_by_sleep Table 1. Midterm score and study hours by nightly sleep band]"], ["[FIGURE:2]"],
   ["Figure 1 shows the same pattern student by student, with the lowest scores concentrated below six hours of sleep."]],
 "discussion": [["A natural objection is that students who sleep more simply study more.",
   ("The data do not support that reading: mean weekly study hours were similar across sleep bands, 7.85 for the 4 to 6 hour band and 8.19 for the 7.50 to 9 hour band, so study time does not explain the score gap.", ["c6"], ["E_D_score_by_sleep", STUDY], "measured"),
   ("The direction agrees with Okano et al. (2019), who found that sleep quality and duration over the month before exams explained about 25% of the variance in grades of 88 MIT students.", ["c2"], [O])]],
 "limitations": [["Three limits temper the result.", ("Sleep was self-reported, the sample is one course at one university, and students who slept more may differ in other ways such as fewer part-time job hours.", ["c8"], [L])]],
 "conclusion": [[("In this course, students who slept 7.50 to 9 hours averaged 87.82 on the midterm, against 74.54 for those sleeping 4 to 6 hours, a gap of 13.28 points.", ["c5"], G, "measured"),
   "Sleep belongs in study advice alongside study time, and a larger study with measured sleep would test whether the gap holds."]],
 "references": [["Walker, M. (2017). Why We Sleep. Scribner."], ["Okano, K., et al. (2019). Sleep quality, duration, and consistency are associated with better academic performance in college students. npj Science of Learning, 4, 16."]],
}
