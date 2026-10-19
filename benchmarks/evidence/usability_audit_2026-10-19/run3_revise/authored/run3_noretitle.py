import importlib.util
s=importlib.util.spec_from_file_location("b","/tmp/claude-0/rw/tasks/run3.py"); b=importlib.util.module_from_spec(s); s.loader.exec_module(b)
globals().update({k:v for k,v in vars(b).items() if not k.startswith("__")})
import json
def REVISION(run, resolve, contract, ledger):
    b.REVISION(run, resolve, contract, ledger)
    p=json.load(open(run/"revision_plan.json")); p["changes"]=[c for c in p["changes"] if c["change_type"]!="retitle"]
    json.dump(p,open(run/"revision_plan.json","w"),ensure_ascii=False,indent=1)
