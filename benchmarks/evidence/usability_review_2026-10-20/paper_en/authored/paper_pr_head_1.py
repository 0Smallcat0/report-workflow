from pathlib import Path
import importlib.util
s=importlib.util.spec_from_file_location("b",str(Path(__file__).resolve().parent / "paper_after_fixes.py")); b=importlib.util.module_from_spec(s); s.loader.exec_module(b)
globals().update({k:v for k,v in vars(b).items() if not k.startswith("__")})
# what an author on the PR head would have to do: type the band as the tool printed it,
# and pass the front matter to start_report (the outline block does not exist there)
DERIVATIONS[1]["inputs"]={"a":{"table":"score_by_sleep","column":"Mean score","row":"7.50–9"},"b":{"table":"score_by_sleep","column":"Mean score","row":"4–6"}}
START = dict(START, correspondence="lin.chen@example.edu", keywords=["sleep duration","exam performance","undergraduates"])
