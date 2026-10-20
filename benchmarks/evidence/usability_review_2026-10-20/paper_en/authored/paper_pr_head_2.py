from pathlib import Path
import importlib.util
s=importlib.util.spec_from_file_location("b",str(Path(__file__).resolve().parent / "paper_pr_head_1.py")); b=importlib.util.module_from_spec(s); s.loader.exec_module(b)
globals().update({k:v for k,v in vars(b).items() if not k.startswith("__")})
OUTLINE_EXTRA = dict(OUTLINE_EXTRA, thesis_statement="Students who slept 7.5 to 9 hours scored 13.28 points higher than those who slept 4 to 6 hours.")
