from pathlib import Path
import importlib.util
s=importlib.util.spec_from_file_location("b",str(Path(__file__).resolve().parent / "paper_pr_head_3.py")); b=importlib.util.module_from_spec(s); s.loader.exec_module(b)
globals().update({k:v for k,v in vars(b).items() if not k.startswith("__")})
DRAFTS["results"][-1] = ["Figure 2 shows the same pattern student by student, with the lowest scores concentrated below six hours of sleep."]
DRAFTS["results"].insert(-1, ["Figure 2: Midterm score against average nightly sleep (n = 40)."])
