from pathlib import Path
import importlib.util
s=importlib.util.spec_from_file_location("b",str(Path(__file__).resolve().parent / "paper_pr_head_2.py")); b=importlib.util.module_from_spec(s); s.loader.exec_module(b)
globals().update({k:v for k,v in vars(b).items() if not k.startswith("__")})
DRAFTS["abstract"] = [[t[0].replace("**Background:**","## Background:\n").replace("**Objective:**","## Objective:\n").replace("**Methods:**","## Methods:\n").replace("**Principal Findings:**","## Principal Findings:\n").replace("**Significance:**","## Significance:\n")] for t in DRAFTS["abstract"]]
