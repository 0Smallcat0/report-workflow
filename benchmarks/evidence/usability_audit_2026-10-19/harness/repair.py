"""Apply an author's edits after a publish failure, then drive the run to publish.

usage: python repair.py OUTDIR LOG.jsonl '{"claim_matrix.json": [["old", "new"], ...]}'
Edits are applied BEFORE submit_action, as the publish error suggests. Every
submit/publish call is appended to LOG.jsonl as one flat record per step.
"""
import glob
import json
import sys

_KEEP = ("status", "stage", "next_stage", "error_details", "violations")


def entry(step, result):
    """One log record: the step name plus the result fields a reader needs."""
    return {"step": step, **{k: result.get(k) for k in _KEEP if result.get(k)}}


def main(argv):
    from report_workflow import agent_wrapper as w

    out, log_path, edits = argv[1], argv[2], json.loads(argv[3])
    log = open(log_path, "a", encoding="utf-8")
    run = glob.glob(out + "/*")[0]
    job = run.split("--")[-1]
    WR = {"workspace_root": out}
    for fname, pairs in edits.items():
        p = f"{run}/{fname}"
        s = open(p, encoding="utf-8").read()
        for a, b in pairs:
            assert a in s, (fname, a)
            s = s.replace(a, b)
        open(p, "w", encoding="utf-8").write(s)
    log.write(json.dumps({"step": "author edits after publish failure", "files": list(edits)}, ensure_ascii=False) + "\n")
    for _ in range(12):
        r = w.submit_action(job_id=job, **WR)
        rec = entry("submit_action", r)
        print("submit_action", rec.get("status"), rec.get("stage"), str(rec.get("error_details") or rec.get("violations") or "")[:300])
        log.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        if r["status"] == "ready_to_publish":
            p = w.publish_report(job_id=job, **WR)
            print("publish_report", p["status"], (p.get("error_details") or "")[:300])
            log.write(json.dumps({**entry("publish_report", p), "docx": p.get("published_report_path")}, ensure_ascii=False, default=str) + "\n")
            if p["status"] == "completed":
                w.submit_action(job_id=job, **WR)
            break
        if r["status"] not in ("passed",):
            break


if __name__ == "__main__":
    main(sys.argv)
