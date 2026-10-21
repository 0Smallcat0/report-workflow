"""One pass of the authored files through the controlled harness, start to publish.

    RW_LABEL=branch python harness/run_all.py quant_zh

Stops at the first refusal and prints it, the way an author would meet it;
the step log is <report>/logs/$RW_LABEL.jsonl.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def step(report: str, *args: str) -> dict:
    out = subprocess.run(
        [sys.executable, str(HERE / "rw.py"), report, *args],
        capture_output=True, text=True, cwd=HERE.parent, env=os.environ,
    )
    try:
        return json.loads(out.stdout)
    except ValueError:
        return {"status": "crashed", "message": (out.stderr or out.stdout)[-2000:]}


def main() -> int:
    report = sys.argv[1]
    log = HERE.parent / report / "logs" / f"{os.environ.get('RW_LABEL', 'branch')}.jsonl"
    if log.exists():
        log.unlink()
    result = step(report, "start")
    print("start", result.get("status"), (result.get("message") or "")[:300] if result.get("status") != "awaiting_agent_artifacts" else "")
    if result.get("status") != "awaiting_agent_artifacts":
        return 1
    if (HERE.parent / report / "authored" / "derivations.json").is_file():
        result = step(report, "register", "derivations.json")
        print("register", result.get("status"), result.get("problems") or "")
    for _ in range(8):
        step(report, "put")
        result = step(report, "submit")
        print("submit", result.get("stage"), result.get("status"), (result.get("error_details") or "")[:1500])
        if result.get("status") == "completed":
            return 0
        if result.get("status") not in {"passed", "ready_to_publish"}:
            return 2
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
