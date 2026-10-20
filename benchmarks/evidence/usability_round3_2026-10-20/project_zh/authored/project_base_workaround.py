"""Base branch only. 套在某一輪作者稿上（環境變數 ROUND=project_round2.py 等，預設第一稿）：

- ratio 讀不到 intake 的「窗戶 分組交叉表」：作者另外註冊一張含 CO2 中位數的同樣分組表，ratio 改讀它；
- 沒有任何運算能算相關係數：刪掉 c6（r = -0.82），摘要與結論改引 c5。
"""
import os
from pathlib import Path
import importlib.util
_name = os.environ.get("ROUND", "project_first_draft.py")
_s = importlib.util.spec_from_file_location("prev", str(Path(__file__).resolve().with_name(_name)))
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
DERIVATIONS = [d for d in DERIVATIONS if d.get("op") != "pearson_r"]
for d in DERIVATIONS:
    if d["id"] == "closed_vs_open_co2":
        d["source"] = "window_median"; d["column"] = "CO2 中位數"
DERIVATIONS.insert(1, {"id": "window_median", "source": CSV, "group_by": {"column": "窗戶"},
    "measures": [{"op": "median", "column": "CO2_ppm", "label": "CO2 中位數"}]})
CLAIMS = [c for c in CLAIMS if c["claim_id"] != "c6"]
for sid, s in OUTLINE.items():
    s["claims"] = [c if c != "c6" else "c5" for c in s["claims"]]
    s["claims"] = list(dict.fromkeys(s["claims"]))
for sid, paras in DRAFTS.items():
    DRAFTS[sid] = [[s for s in p if not (isinstance(s, tuple) and "c6" in s[1])] for p in paras]
    DRAFTS[sid] = [p for p in DRAFTS[sid] if p]
DRAFTS["conclusion"] = [[("關窗時平均二氧化碳濃度為 1,537.04 ppm，開窗時為 1,143.12 ppm；平均專注度則由開窗的 3.68 分降到關窗的 2.85 分。", ["c5"], [WIN], "measured"),
   "建議班上在下午課堂主動開窗，下一步可以用隨機安排開窗的方式，檢驗開窗是否真的提升專注度。"]]
# 自己註冊的 window_median 也是一張交叉表，必須安置或放棄
OUTLINE_EXTRA = {"unused_derived_evidence": {"E_D_window_median": "只用來算 ratio；表 1 已列出兩組的平均濃度"}}
