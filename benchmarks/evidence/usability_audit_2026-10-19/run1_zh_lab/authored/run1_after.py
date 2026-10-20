import importlib.util
s=importlib.util.spec_from_file_location("b",str(__import__("pathlib").Path(__file__).resolve().with_name("run1.py"))); b=importlib.util.module_from_spec(s); s.loader.exec_module(b)
globals().update({k:v for k,v in vars(b).items() if not k.startswith("__")})
RETRY_FULL_DECISIONS=False
OUTLINE.pop("results",None)
# what 02_outline_plan.md now says for engineering_lab_report
OUTLINE["results_discussion"]["extra"]={"results_mode":"empirical"}
