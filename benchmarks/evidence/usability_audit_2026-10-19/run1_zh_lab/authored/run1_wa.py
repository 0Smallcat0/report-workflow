import importlib.util,sys
base=sys.argv[0] and None
s=importlib.util.spec_from_file_location("b","/tmp/claude-0/rw/tasks/run1.py"); b=importlib.util.module_from_spec(s); s.loader.exec_module(b)
globals().update({k:v for k,v in vars(b).items() if not k.startswith("__")})
OUTLINE.pop("results",None)
