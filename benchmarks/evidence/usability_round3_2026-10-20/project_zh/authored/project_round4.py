"""第四輪：FE 說「48 節」的單位證據沒有寫（證據寫的是 48 筆），作者照證據的說法改寫 c4。"""
from pathlib import Path
import importlib.util
_s = importlib.util.spec_from_file_location("r3", str(Path(__file__).resolve().with_name("project_round3.py")))
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
_OLD = "48 節課的二氧化碳濃度介於 884 至 1,725 ppm，中位數為 1,371 ppm。"
_NEW = "全部 48 筆紀錄的二氧化碳濃度介於 884 至 1,725 ppm，中位數為 1,371 ppm。"
for c in CLAIMS:
    if c["claim_id"] == "c4": c["claim_text"] = _NEW
for paras in DRAFTS.values():
    for p in paras:
        for i, s in enumerate(p):
            if isinstance(s, tuple) and s[0] == _OLD:
                p[i] = (_NEW,) + tuple(s[1:])
