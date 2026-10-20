"""Round 2: what the author changed after the first publish was blocked by FE on c4 and c9."""
from pathlib import Path
import importlib.util
_s = importlib.util.spec_from_file_location("first", str(Path(__file__).resolve().with_name("memo_first_draft.py")))
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
_EDITS = {
 # FE: "'36'weeks states a unit the evidence does not (36values)" - say it the way the notes do.
 "The signal ranged from -2.77 to 3.42 over the 36 weeks, and next-week returns from -2.56% to 2.92%.":
 ("The signal ranged from -2.77 to 3.42 over 36 weekly observations, and next-week returns from -2.56% to 2.92%.", "c4", [LIMITS]),
 # FE: key terms of the auto regime table are its column names.
 "Bull weeks returned 0.30% on average the following week against -0.02% for bear weeks, while the mean signal was -0.22 in bull weeks and 0.71 in bear weeks.":
 ("By regime, the mean next-week return was 0.30% in bull weeks and -0.02% in bear weeks, and the mean signal was -0.22 and 0.71.", "c9", []),
}
for c in CLAIMS:
    for old, (new, cid, extra) in _EDITS.items():
        if c["claim_id"] == cid:
            c["claim_text"] = new; c["evidence_ids"] = c["evidence_ids"] + extra
for sid, paras in DRAFTS.items():
    for p in paras:
        for i, s in enumerate(p):
            if isinstance(s, tuple) and s[0] in _EDITS:
                new, _cid, extra = _EDITS[s[0]]
                p[i] = (new, s[1], list(s[2]) + extra) + tuple(s[3:])
