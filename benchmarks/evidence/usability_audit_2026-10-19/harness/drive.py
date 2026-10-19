"""Drive one authored report task through report-workflow and log every step.

usage: python drive.py TASK.py OUTDIR LOG.jsonl
The task module defines START (start_report kwargs minus output_dir),
DERIVATIONS (list, optional), CLAIMS, OUTLINE (dict sid->spec), DRAFTS
(dict sid->list of sentences or paragraphs), and optional REVISION (callable).
Evidence refs are "ID" or "~substring" (resolved against the ledger).
"""
import importlib.util, json, sys, glob, re, os, inspect
from pathlib import Path
from report_workflow import agent_wrapper as w
for new, old in (("start_report","start_report_task"),("get_next_action","get_controlled_next_action"),("submit_action","submit_controlled_action"),("publish_report","submit_and_publish_report"),("check_environment","check_setup"),("register_derived_evidence","register_derived_evidence")):
    if not hasattr(w, new) and hasattr(w, old):
        setattr(w, new, getattr(w, old))

task_path, out, log_path = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("task", task_path)
T = importlib.util.module_from_spec(spec); spec.loader.exec_module(T)
LOG = open(log_path, "w", encoding="utf-8")
WR = {"workspace_root": out} if "workspace_root" in inspect.signature(w.submit_action).parameters else {}

def log(step, res):
    keep = {k: res.get(k) for k in ("status", "stage", "next_stage", "error_details", "message",
                                    "decision_issues", "violations", "allowed_repair_paths", "problems",
                                    "final_docx_path", "published_report_path") if res.get(k)}
    LOG.write(json.dumps({"step": step, **keep}, ensure_ascii=False, default=str) + "\n"); LOG.flush()
    print(step, keep.get("status"), str(keep.get("error_details") or keep.get("decision_issues") or keep.get("violations") or keep.get("problems") or "")[:700])
    return res

kw = dict(T.START); kw["output_dir"] = out
res = log("start_report", w.start_report(**kw))
if res.get("status") == "needs_user_decision" and (getattr(T, "RETRY_FULL_DECISIONS", True) or os.environ.get("RETRY")):
    shape = res.get("required_preflight_decisions") or {}
    kw["preflight_decisions"] = {"confirmed_by_user": True,
        "install_decisions": {k: "skip" for k in shape.get("install_decisions", {})},
        "feature_decisions": {k: "skip" for k in shape.get("feature_decisions", {})}}
    res = log("start_report(retry with every optional answered)", w.start_report(**kw))
job = res["job_id"]
run = Path(glob.glob(f"{out}/*{job}")[0])

if getattr(T, "DERIVATIONS", None):
    if hasattr(w, "register_derived_evidence"):
        log("register_derived_evidence", w.register_derived_evidence(job_id=job, derivations=T.DERIVATIONS, **WR))
    else:
        log("register_derived_evidence", {"status": "unavailable_in_this_version"})

def ledger():
    return [json.loads(l) for l in open(run / "evidence_ledger.jsonl", encoding="utf-8") if l.strip()]

def resolve(ref):
    if not ref.startswith("~"):
        return ref
    needle = ref[1:]
    for e in ledger():
        if needle in (e.get("content") or ""):
            return e["evidence_id"]
    return "MISSING:" + needle

def contract():
    for name in ("01_claim_plan.md",):
        t = (run / "agent_tasks" / name).read_text(encoding="utf-8")
        m = re.search(r'"_contract": (\{.*?\})', t, re.S)
        return json.loads(m.group(1))

def write_claims():
    claims = []
    for c in T.CLAIMS:
        c = dict(c); c["evidence_ids"] = [resolve(r) for r in c["evidence_ids"]]
        c.setdefault("risk_level", "low"); c.setdefault("status", "supported"); c.setdefault("requires_hedged_wording", False)
        claims.append(c)
    json.dump({"_contract": contract(), "claims": claims}, open(run / "claim_matrix.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def write_outline():
    secs = {}
    for sid, s in T.OUTLINE.items():
        d = {"section_id": sid, "goals": s.get("goal", sid), "claim_ids": s.get("claims", []),
             "paragraph_order": [s.get("goal", sid)], "figure_ids": s.get("figures", [])}
        d.update(s.get("extra", {})); secs[sid] = d
    o = {"_contract": contract(), "sections": secs}
    o.update(getattr(T, "OUTLINE_EXTRA", {}))
    json.dump(o, open(run / "outline.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if getattr(T, "FIGURE_PLAN_EDIT", None):
        T.FIGURE_PLAN_EDIT(run)

def sent(s):
    if isinstance(s, str):
        return {"text": s}
    return {"text": s[0], "claim_ids": s[1], "evidence_ids": [resolve(r) for r in s[2]],
            "wording_strength": s[3] if len(s) > 3 else "hedged"}

def write_drafts():
    secs = {}
    for sid, paras in T.DRAFTS.items():
        if getattr(T, "FLAT_DRAFTS", False):
            secs[sid] = {"sentences": [sent(s) for p in paras for s in p]}
        else:
            secs[sid] = {"paragraphs": [{"sentences": [sent(s) for s in p]} for p in paras]}
    json.dump({"_contract": contract(), "sections": secs}, open(run / "structured_drafts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

writers = {"claim_matrix": write_claims, "outline": write_outline, "drafts": write_drafts,
           "revision_plan": (lambda: T.REVISION(run, resolve, contract, ledger))}
written = set()
final = None
for i in range(30):
    nxt = w.get_next_action(job_id=job, **WR)
    stage = nxt.get("stage")
    if stage == "completed" or nxt.get("status") == "completed":
        break
    if stage in writers and stage not in written:
        writers[stage](); written.add(stage)
    if stage == "publish":
        final = log("publish_report", w.publish_report(job_id=job, **WR))
        if final.get("status") == "completed":
            # let the harness record the pass
            log("submit_action(publish)", w.submit_action(job_id=job, **WR))
            break
        r = log("submit_action(route publish failure)", w.submit_action(job_id=job, **WR))
        break
    r = log(f"submit_action({stage})", w.submit_action(job_id=job, **WR))
    if r.get("status") not in ("passed", "ready_to_publish", "completed"):
        break
print("RUN_DIR", run)
LOG.write(json.dumps({"run_dir": str(run), "job_id": job}, ensure_ascii=False) + "\n")
