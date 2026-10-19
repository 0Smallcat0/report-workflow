import importlib.util
s=importlib.util.spec_from_file_location("b","/tmp/claude-0/rw/tasks/run1.py"); b=importlib.util.module_from_spec(s); s.loader.exec_module(b)
globals().update({k:v for k,v in vars(b).items() if not k.startswith("__")})
FLAT_DRAFTS=True
R20='~"擺長_cm": "20"'; R80='~"擺長_cm": "80"'; R40='~"擺長_cm": "40"'
DERIVATIONS=None
for c in CLAIMS:
    if c["claim_id"]=="c6": c["evidence_ids"]=[R20,R80]
    if c["claim_id"]=="c9": c["evidence_ids"]=[R40,R80]
CLAIMS=[c for c in CLAIMS if c["claim_id"] not in ("c7","c8","c11")]
OUTLINE["calculations"]={"claims":["c6"]}; OUTLINE["results_discussion"]={"claims":["c10"]}; OUTLINE["conclusion"]={"claims":["c6"]}
DRAFTS["data"]=[[("擺長由 20 cm 增加到 80 cm 時，週期由 0.90 s 增加到 1.79 s，如圖 1 所示。",["c6"],[R20,R80],"measured")],["[FIGURE:1]"],[("量測期間室溫維持在 24.4 至 24.8 °C 之間，溫度變化很小。",["c9"],[R40,R80],"measured")]]
DRAFTS["calculations"]=[[("擺長 20 cm 的週期為 0.90 s，擺長 80 cm 的週期為 1.79 s。",["c6"],[R20,R80],"measured")]]
DRAFTS["results_discussion"]=[[("誤差來源可能包括人工按碼表約 0.2 s 的反應時間，以及擺角不完全是小角度。",["c10"],[ERR])]]
DRAFTS["conclusion"]=[[("擺長由 20 cm 增加到 80 cm 時，週期由 0.90 s 增加到 1.79 s。",["c6"],[R20,R80],"measured")]]
for c in CLAIMS:
    if c["claim_id"]=="c6": c["claim_role"]="primary"
OUTLINE.pop("results",None)
