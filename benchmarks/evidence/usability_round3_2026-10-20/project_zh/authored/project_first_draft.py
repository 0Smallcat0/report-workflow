"""中文 admissions_project_report，讀完 brief 後寫的第一稿。"""
from pathlib import Path
import importlib.util
_s = importlib.util.spec_from_file_location("start", str(Path(__file__).resolve().with_name("start.py")))
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
START = _m.START
CSV = "教室CO2紀錄.csv"
WIN_AUTO = "~窗戶 分組交叉表"; PERIOD_AUTO = "~節次 分組交叉表"
DERIVATIONS = [
 {"id":"window_table","source":CSV,"label":"開窗與關窗的二氧化碳濃度與專注度","group_by":{"column":"窗戶","label":"窗戶"},
  "measures":[{"op":"count","label":"節數"},{"op":"mean","column":"CO2_ppm","label":"平均 CO2 (ppm)"},{"op":"mean","column":"專注度","label":"平均專注度"},{"op":"share","rows":"CO2_ppm>1000","label":"超過 1000 ppm 的比例"}]},
 # 讀 intake 已建好的「窗戶 分組交叉表」：source 是 brief 列出的 evidence id
 {"id":"closed_vs_open_co2","op":"ratio","source":"E_f6aefa21_2b23e015be","column":"CO2_ppm 中位數","numerator_group":"關","denominator_group":"開","decimals":2,"label":"關窗與開窗的 CO2 中位數倍數"},
 {"id":"focus_by_co2_band","source":CSV,"label":"各二氧化碳濃度區間的平均專注度","group_by":{"column":"CO2_ppm","buckets":[800,1000,1200,1400,1600,1800],"label":"CO2 區間 (ppm)"},
  "measures":[{"op":"count","label":"節數"},{"op":"mean","column":"專注度","label":"平均專注度"}]},
 {"id":"co2_focus_r","op":"pearson_r","source":CSV,"x":"CO2_ppm","y":"專注度","decimals":2,"label":"CO2 濃度與專注度的相關"},
 {"id":"over_1000","source":CSV,"op":"share","rows":"CO2_ppm>1000","decimals":1,"label":"超過 1000 ppm 的節數比例"},
]
MOT="~研究動機"; METHOD="~測量方法"; LIT="~文獻：Satish"; LIMIT="~研究限制"
SHAPE="~本樣本共收錄 48 筆"; CO2="~CO2_ppm 欄共 48 筆數值"
WIN="E_D_window_table"; RATIO="E_D_closed_vs_open_co2"; BAND="E_D_focus_by_co2_band"; R="E_D_co2_focus_r"; OVER="E_D_over_1000"
CLAIMS = [
 dict(claim_id="c1", claim_text="下午第七節常覺得昏沉，想知道是不是教室空氣不流通造成的。", claim_type="qualitative", evidence_ids=[MOT], claim_role="background"),
 dict(claim_id="c2", claim_text="以一台解析度 1 ppm 的 NDIR 二氧化碳偵測器放在講桌旁，連續 12 個上課日在第 1、3、5、7 節下課前 5 分鐘讀數，並記錄窗戶開關與人數；專注度由 5 位同學以 1 到 5 分自評後取平均。", claim_type="methodological", evidence_ids=[METHOD], claim_role="supporting"),
 dict(claim_id="c3", claim_text="Satish et al. (2012) 發現二氧化碳濃度由 600 ppm 升到 1000 ppm 時，受試者的決策表現已有下降；教育部室內空氣品質標準的二氧化碳 8 小時平均值為 1000 ppm。", claim_type="factual", evidence_ids=[LIT], claim_role="background"),
 dict(claim_id="c4", claim_text="48 節課的二氧化碳濃度介於 884 至 1,725 ppm，中位數為 1,371 ppm。", claim_type="statistical", evidence_ids=[SHAPE, CO2], claim_role="supporting"),
 dict(claim_id="c5", claim_text="關窗時平均二氧化碳濃度為 1,537.04 ppm，開窗時為 1,143.12 ppm；平均專注度則由開窗的 3.68 分降到關窗的 2.85 分。", claim_type="statistical", evidence_ids=[WIN], claim_role="primary"),
 dict(claim_id="c6", claim_text="二氧化碳濃度與專注度呈明顯負相關，r = -0.82（n = 48）。", claim_type="statistical", evidence_ids=[R], claim_role="primary"),
 dict(claim_id="c7", claim_text="濃度在 1000–1199 ppm 的節次平均專注度為 3.91 分，到 1600–1799 ppm 時降為 2.44 分。", claim_type="statistical", evidence_ids=[BAND], claim_role="supporting"),
 dict(claim_id="c8", claim_text="關窗時的二氧化碳濃度中位數是開窗時的 1.32 倍（1,549 對 1,171.50 ppm）。", claim_type="statistical", evidence_ids=[RATIO, WIN_AUTO], claim_role="supporting"),
 dict(claim_id="c9", claim_text="48 節課中有 93.8% 超過教育部標準的 1000 ppm。", claim_type="statistical", evidence_ids=[OVER, LIT], claim_role="supporting"),
 dict(claim_id="c10", claim_text="第 7 節的二氧化碳濃度中位數為 1,510 ppm，高於第 1 節的 1,178.50 ppm。", claim_type="statistical", evidence_ids=[PERIOD_AUTO], claim_role="supporting"),
 dict(claim_id="c11", claim_text="本研究只有一台偵測器、只測三間教室，專注度是自評，而且窗戶開關沒有隨機安排。", claim_type="qualitative", evidence_ids=[LIMIT], claim_role="supporting", requires_hedged_wording=True),
]
OUTLINE = {
 "abstract": {"claims": ["c5","c6"]},
 "introduction": {"claims": ["c1","c3"]},
 "research_scope": {"claims": ["c2"]},
 "methods": {"claims": ["c2","c4"]},
 "results": {"claims": ["c4","c5","c6","c7","c8","c10"]},
 "discussion": {"claims": ["c9","c3"]},
 "limitations": {"claims": ["c11"]},
 "conclusion": {"claims": ["c6"]},
 "references": {"claims": []},
}
A = lambda t: [t]
DRAFTS = {
 "abstract": [A("下午第七節常讓人昏沉，本研究想知道教室二氧化碳濃度是否與上課專注度有關，以及開窗能否改善。研究以一台二氧化碳偵測器，在三間教室連續十二個上課日、每天四個節次記錄濃度、窗戶開關與人數，並請五位同學自評專注度。結果顯示，關窗時的平均濃度明顯高於開窗，平均專注度也較低；濃度與專注度呈明顯負相關，濃度越高的區間，平均專注度越低，而且多數節次都超過教育部建議的標準。由於偵測器只有一台、專注度為自評、開窗也沒有隨機安排，這只是相關而非因果，但已足以建議班上在下午課堂主動開窗，並在後續研究中以隨機開窗的方式檢驗。")],
 "introduction": [["許多同學都有下午上課特別想睡的經驗。",
   ("下午第七節常覺得昏沉，想知道是不是教室空氣不流通造成的。", ["c1"], [MOT]),
   ("Satish et al. (2012) 發現二氧化碳濃度由 600 ppm 升到 1000 ppm 時，受試者的決策表現已有下降；教育部室內空氣品質標準的二氧化碳 8 小時平均值為 1000 ppm。", ["c3"], [LIT]),
   "因此本研究在自己的教室實際量測，檢驗濃度與專注度之間的關係。"]],
 "research_scope": [["研究範圍限於本校三間教室與平日的四個節次。",
   ("以一台解析度 1 ppm 的 NDIR 二氧化碳偵測器放在講桌旁，連續 12 個上課日在第 1、3、5、7 節下課前 5 分鐘讀數，並記錄窗戶開關與人數；專注度由 5 位同學以 1 到 5 分自評後取平均。", ["c2"], [METHOD])]],
 "methods": [[("以一台解析度 1 ppm 的 NDIR 二氧化碳偵測器放在講桌旁，連續 12 個上課日在第 1、3、5、7 節下課前 5 分鐘讀數，並記錄窗戶開關與人數；專注度由 5 位同學以 1 到 5 分自評後取平均。", ["c2"], [METHOD]),
   ("48 節課的二氧化碳濃度介於 884 至 1,725 ppm，中位數為 1,371 ppm。", ["c4"], [SHAPE, CO2], "measured"),
   "分析時比較開窗與關窗兩組的平均值，將濃度分成每 200 ppm 一個區間計算平均專注度，並計算兩者的相關係數。"]],
 "results": [[("關窗時平均二氧化碳濃度為 1,537.04 ppm，開窗時為 1,143.12 ppm；平均專注度則由開窗的 3.68 分降到關窗的 2.85 分。", ["c5"], [WIN], "measured"),
   ("關窗時的二氧化碳濃度中位數是開窗時的 1.32 倍（1,549 對 1,171.50 ppm）。", ["c8"], [RATIO, WIN_AUTO], "measured")],
   ["[TABLE:E_D_window_table 表 1 開窗與關窗的二氧化碳濃度與專注度]"],
   [("二氧化碳濃度與專注度呈明顯負相關，r = -0.82（n = 48）。", ["c6"], [R], "measured"),
   ("濃度在 1000–1199 ppm 的節次平均專注度為 3.91 分，到 1600–1799 ppm 時降為 2.44 分。", ["c7"], [BAND], "measured")],
   ["[TABLE:E_D_focus_by_co2_band 表 2 各二氧化碳濃度區間的平均專注度]"],
   [("第 7 節的二氧化碳濃度中位數為 1,510 ppm，高於第 1 節的 1,178.50 ppm。", ["c10"], [PERIOD_AUTO], "measured")]],
 "discussion": [[("48 節課中有 93.8% 超過教育部標準的 1000 ppm。", ["c9"], [OVER, LIT], "measured"),
   ("這與 Satish et al. (2012) 的發現方向一致：他們觀察到濃度由 600 ppm 升到 1000 ppm 時，決策表現已有下降。", ["c3"], [LIT]),
   "換句話說，教室在大部分時間裡都處於文獻認為會影響表現的濃度。"]],
 "limitations": [[("本研究只有一台偵測器、只測三間教室，專注度是自評，而且窗戶開關沒有隨機安排。", ["c11"], [LIMIT], "hedged"),
   "因此結果只能說明相關，不能證明二氧化碳造成專注度下降。"]],
 "conclusion": [[("二氧化碳濃度與專注度呈明顯負相關，r = -0.82（n = 48）。", ["c6"], [R], "measured"),
   "建議班上在下午課堂主動開窗，下一步可以用隨機安排開窗的方式，檢驗開窗是否真的提升專注度。"]],
 "references": [["Satish, U., Mendell, M. J., Shekhar, K., et al. (2012). Is CO2 an indoor pollutant? Direct effects of low-to-moderate CO2 concentrations on human decision-making performance. Environmental Health Perspectives, 120(12), 1671–1677."],
   ["教育部（2012）。室內空氣品質標準。"]],
}
