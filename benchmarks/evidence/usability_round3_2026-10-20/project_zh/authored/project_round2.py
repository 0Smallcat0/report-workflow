"""第二輪：publish 回報摘要只有 232 字（下限 300），作者把摘要寫完整。"""
from pathlib import Path
import importlib.util
_s = importlib.util.spec_from_file_location("first", str(Path(__file__).resolve().with_name("project_first_draft.py")))
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
DRAFTS["abstract"] = [[
 "下午第七節常讓人昏沉，本研究想知道教室二氧化碳濃度是否與上課專注度有關，以及開窗能否改善這個情形。"
 "研究以一台二氧化碳偵測器，在三間教室連續十二個上課日、每天第一、三、五、七節下課前量測濃度，同時記錄窗戶開關與在場人數，並請五位同學以一到五分自評專注度後取平均。"
 "結果顯示，關窗時的平均濃度明顯高於開窗，平均專注度也較低；濃度與專注度呈明顯負相關，濃度越高的區間，平均專注度越低，而且絕大多數節次都超過教育部室內空氣品質標準。"
 "由於偵測器只有一台、專注度為自評、開窗也沒有隨機安排，這些結果只能說明相關而非因果。"
 "即使如此，結果已足以建議班上在下午課堂主動開窗通風，並在後續研究中以隨機安排開窗的方式，檢驗開窗是否真的能提升專注度。"
]]
