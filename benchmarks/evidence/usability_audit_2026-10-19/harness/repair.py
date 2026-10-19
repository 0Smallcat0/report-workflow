import json,glob,sys
from report_workflow import agent_wrapper as w
out=sys.argv[1]; log=open(sys.argv[2],"a",encoding="utf-8"); edits=json.loads(sys.argv[3])
run=glob.glob(out+"/*")[0]; job=run.split("--")[-1]; WR={"workspace_root":out}
# edit claim_matrix and structured_drafts together, as the publish error suggests, BEFORE calling submit_action
for fname, pairs in edits.items():
    p=f"{run}/{fname}"; s=open(p,encoding="utf-8").read()
    for a,b in pairs:
        assert a in s,(fname,a); s=s.replace(a,b)
    open(p,"w",encoding="utf-8").write(s)
log.write(json.dumps({"step":"author edits after publish failure","files":list(edits)},ensure_ascii=False)+"\n")
for i in range(12):
    r=w.submit_action(job_id=job,**WR) if True else None
    keep={k:r.get(k) for k in ("status","stage","next_stage","error_details","violations") if r.get(k)}
    print("submit_action",keep.get("status"),keep.get("stage"),str(keep.get("error_details") or keep.get("violations") or "")[:300])
    log.write(json.dumps({"step":"submit_action","**":keep},ensure_ascii=False,default=str)+"\n")
    if r["status"]=="ready_to_publish":
        p=w.publish_report(job_id=job,**WR); print("publish_report",p["status"],(p.get("error_details") or "")[:300])
        log.write(json.dumps({"step":"publish_report","status":p["status"],"error_details":p.get("error_details"),"docx":p.get("published_report_path")},ensure_ascii=False)+"\n")
        if p["status"]=="completed": w.submit_action(job_id=job,**WR)
        break
    if r["status"] not in ("passed",): break
