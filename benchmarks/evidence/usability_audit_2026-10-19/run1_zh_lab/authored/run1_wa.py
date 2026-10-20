import importlib.util,sys
s=importlib.util.spec_from_file_location("b",str(__import__("pathlib").Path(__file__).resolve().with_name("run1.py"))); b=importlib.util.module_from_spec(s); s.loader.exec_module(b)
globals().update({k:v for k,v in vars(b).items() if not k.startswith("__")})
OUTLINE.pop("results",None)
