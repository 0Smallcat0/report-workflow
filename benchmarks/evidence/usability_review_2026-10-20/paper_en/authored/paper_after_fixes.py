from pathlib import Path
import importlib.util
s=importlib.util.spec_from_file_location("b",str(Path(__file__).resolve().parent / "paper_first_draft.py")); b=importlib.util.module_from_spec(s); s.loader.exec_module(b)
globals().update({k:v for k,v in vars(b).items() if not k.startswith("__")})
for c in CLAIMS:
    if c["claim_id"]=="c3": c["claim_type"]="factual"
OUTLINE_EXTRA = dict(OUTLINE_EXTRA, front_matter={"correspondence":"lin.chen@example.edu","keywords":["sleep duration","exam performance","undergraduates"]})
