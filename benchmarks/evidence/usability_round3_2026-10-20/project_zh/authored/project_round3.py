"""第三輪：摘要算出來 287 字。作者再補一句研究設計的說明。"""
from pathlib import Path
import importlib.util
_s = importlib.util.spec_from_file_location("r2", str(Path(__file__).resolve().with_name("project_round2.py")))
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
DRAFTS["abstract"] = [[DRAFTS["abstract"][0][0].replace(
 "這些結果只能說明相關而非因果。",
 "這些結果只能說明兩者相關，還不能證明是二氧化碳造成專注度下降，也無法排除下午本來就比較疲倦的影響。")]]
