"""Base branch only: no op computes r, a slope or R², so the author drops those claims.

Built on the first draft (base_round2) or on round 2's FE fixes (base_round3, ROUND2=1).
"""
import os
from pathlib import Path
import importlib.util
_name = "memo_round2.py" if os.environ.get("ROUND2") else "memo_first_draft.py"
_s = importlib.util.spec_from_file_location("prev", str(Path(__file__).resolve().with_name(_name)))
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
_DROP = {"c5", "c6", "c8"}
DERIVATIONS = [d for d in DERIVATIONS if d.get("op") not in ("pearson_r", "linear_fit")]
CLAIMS = [c for c in CLAIMS if c["claim_id"] not in _DROP]
for s in OUTLINE.values():
    s["claims"] = [c for c in s["claims"] if c not in _DROP]
OUTLINE["summary"]["claims"] = ["c7"]
for sid, paras in DRAFTS.items():
    DRAFTS[sid] = [[s for s in p if not (isinstance(s, tuple) and set(s[1]) & _DROP)] for p in paras]
    DRAFTS[sid] = [p for p in DRAFTS[sid] if p]
DRAFTS["methods_note"] = None
del DRAFTS["methods_note"]
DRAFTS["method"][0][1] = "The relation is measured as mean returns across signal bands cut at 0 and 1, and the regime breakdown is compared."
DRAFTS["method"][0] = DRAFTS["method"][0][:2]
