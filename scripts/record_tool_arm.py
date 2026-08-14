"""Re-record Arm B: one authored run of the pipeline, start to fixture.

The drone-market benchmark compares three recorded reports, and Arm B is the one
that moves — it has to be re-recorded whenever the pipeline changes, or the
comparison is measuring a document the current code would no longer produce.

This drives the whole thing in one pass: prepare, register the derivations the
argument needs, write the claim matrix and outline, draft the prose, validate,
render, and rewrite the fixture from the delivered DOCX in document order.

Authored, not filled in. The claims and the prose here are one author's work, and
they are checked in so the next round can change *one* thing and see what moved.

    python scripts/record_tool_arm.py            # re-record into the fixture
    python scripts/record_tool_arm.py --dry-run  # score only, leave the fixture
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

FIXTURE = REPO_ROOT / "benchmarks" / "fixtures" / "drone_market_tool_arm.md"
SOURCE_DIR = REPO_ROOT / "benchmarks" / "fixtures" / "drone_market"
PROMPT = (
    "根據 Amazon US 無人機類商品資料撰寫一份市場研究報告，涵蓋品類結構、價格帶分布、"
    "品牌集中度、買家痛點四個面向，結論必須能支撐「這個市場值不值得進入、"
    "從哪個切點進入」的判斷。"
)

PRICE_BUCKETS = [0, 30, 50, 100, 200, 500, 800]

DERIVATIONS = [
    {"id": "price_band_supply", "source": "amazon_products.csv",
     "label": "價格帶供給與需求訊號",
     "group_by": {"column": "price", "buckets": PRICE_BUCKETS, "label": "價格帶 (USD)"},
     "measures": [{"op": "count", "label": "掛牌數"}, {"op": "share", "label": "佔比"},
                  {"op": "mean", "column": "rating", "label": "平均星等"},
                  {"op": "median", "column": "review_count", "label": "累積評論中位數"}]},
    {"id": "category_profile",
     "source": ["amazon_classified.csv", "amazon_products.csv"],
     "join": {"on": "asin", "how": "inner"}, "label": "品類結構（分類×掛牌）",
     "group_by": {"column": "category", "label": "品類"},
     "measures": [{"op": "count", "label": "掛牌數"}, {"op": "share", "label": "佔比"},
                  {"op": "median", "column": "price", "label": "價格中位數"},
                  {"op": "mean", "column": "rating", "label": "平均星等"},
                  {"op": "median", "column": "review_count", "label": "累積評論中位數"}]},
    # The cross tabulation the previous recording said could not be built. Both
    # files key on asin — this script joined them twice already — and the
    # sentence claiming otherwise was the single largest deduction three blind
    # judges made. It is also the third leg the executive summary was missing:
    # the cut point had a price band and a satisfaction score and no answer to
    # "which category is it".
    {"id": "category_by_price_band",
     "source": ["amazon_classified.csv", "amazon_products.csv"],
     "join": {"on": "asin", "how": "inner"},
     "label": "品類佔比依價格帶（分類×掛牌，以 asin 聯結）",
     "group_by": {"column": "price", "buckets": PRICE_BUCKETS, "label": "價格帶 (USD)"},
     "measures": [{"op": "count", "label": "掛牌數"},
                  {"op": "share", "rows": "category=攝影", "label": "攝影佔比"},
                  {"op": "share", "rows": "category=植保", "label": "植保佔比"},
                  {"op": "median", "column": "review_count", "label": "累積評論中位數"}]},
    {"id": "review_by_price_band",
     "source": ["amazon_reviews.csv", "amazon_products.csv"],
     "join": {"on": "asin", "how": "inner"}, "label": "口碑依價格帶（評論×掛牌）",
     "group_by": {"column": "price", "buckets": [0, 30, 50, 100, 200, 500],
                  "label": "價格帶 (USD)"},
     "measures": [{"op": "count", "label": "評論數"},
                  {"op": "distinct", "column": "asin", "label": "商品數"},
                  {"op": "mean", "column": "review_rating", "label": "平均星等"},
                  {"op": "share", "rows": "review_rating<=2", "label": "一二星佔比"}]},
    {"id": "review_by_category",
     "source": ["amazon_reviews.csv", "amazon_classified.csv"],
     "join": {"on": "asin", "how": "inner"}, "label": "口碑依品類（評論×分類）",
     "group_by": {"column": "category", "label": "品類"},
     "measures": [{"op": "count", "label": "評論數"},
                  {"op": "mean", "column": "review_rating", "label": "平均星等"},
                  {"op": "share", "rows": "review_rating<=2", "label": "一二星佔比"}]},
    {"id": "pain_theme_by_star", "source": "amazon_reviews.csv",
     "label": "痛點主題依星等",
     "group_by": {"column": "review_rating", "buckets": [1, 3, 5], "label": "星等區間"},
     "measures": [{"op": "count", "label": "評論數"},
                  {"op": "share", "rows": "review_body~camera", "label": "提及影像"},
                  {"op": "share", "rows": "review_body~connect", "label": "提及連線"},
                  {"op": "share", "rows": "review_body~instruct", "label": "提及說明"},
                  {"op": "share", "rows": "review_body~broke", "label": "提及故障"}]},
    {"id": "brand_cr3", "source": "amazon_products.csv", "op": "top_share",
     "column": "brand", "k": 3, "label": "品牌 CR3"},
    {"id": "brand_cr10", "source": "amazon_products.csv", "op": "top_share",
     "column": "brand", "k": 10, "label": "品牌 CR10"},
    {"id": "dji_share", "source": "amazon_products.csv", "op": "share",
     "rows": "brand=DJI", "label": "DJI 掛牌佔比"},
    {"id": "reviewed_asins", "source": "amazon_reviews.csv", "op": "distinct",
     "column": "asin", "label": "有評論的商品數"},
    {"id": "low_star_share", "source": "amazon_reviews.csv", "op": "share",
     "rows": "review_rating<=2", "label": "一二星評論佔比"},

    # Comparisons over rows of the tables above. A multiple and a gap in
    # percentage points are what the argument reaches for once it has the
    # bands, and until COMPARISON_OPS existed the choice was to write them
    # uncited or not at all. They read the printed cells, so the operands are
    # the same figures the reader sees in the table.
    {"id": "camera_share_gap", "op": "pp_diff", "source": "category_by_price_band",
     "column": "攝影佔比", "numerator_group": "200-500", "denominator_group": "0-30",
     "decimals": 2, "label": "攝影佔比：200–500 帶減 0–30 帶"},
    {"id": "camera_share_ratio", "op": "ratio", "source": "category_by_price_band",
     "column": "攝影佔比", "numerator_group": "500-800", "denominator_group": "0-30",
     "decimals": 2, "label": "攝影佔比：500–800 帶對 0–30 帶"},
    {"id": "agri_share_gap", "op": "pp_diff", "source": "category_by_price_band",
     "column": "植保佔比", "numerator_group": "800+", "denominator_group": "200-500",
     "decimals": 2, "label": "植保佔比：800+ 帶減 200–500 帶"},
    {"id": "review_depth_ratio", "op": "ratio", "source": "price_band_supply",
     "column": "累積評論中位數", "numerator_group": "200-500",
     "denominator_group": "0-30", "decimals": 1,
     "label": "累積評論中位數：200–500 帶對 0–30 帶"},
    {"id": "supply_density_ratio", "op": "ratio", "source": "price_band_supply",
     "column": "掛牌數", "numerator_group": "0-30", "denominator_group": "200-500",
     "decimals": 2, "label": "掛牌數：0–30 帶對 200–500 帶"},
    {"id": "low_star_gap", "op": "pp_diff", "source": "review_by_price_band",
     "column": "一二星佔比", "numerator_group": "100-200",
     "denominator_group": "200-500", "decimals": 2,
     "label": "一二星佔比：100–200 帶減 200–500 帶"},
]

E_PRICE, E_CAT = "E_D_price_band_supply", "E_D_category_profile"
E_RVP, E_RVC = "E_D_review_by_price_band", "E_D_review_by_category"
E_PAIN, E_CR3 = "E_D_pain_theme_by_star", "E_D_brand_cr3"
E_DJI = "E_D_dji_share"
E_CATBAND = "E_D_category_by_price_band"
E_CAMGAP, E_CAMRATIO = "E_D_camera_share_gap", "E_D_camera_share_ratio"
E_AGRIGAP = "E_D_agri_share_gap"
E_DEPTH, E_SUPPLY = "E_D_review_depth_ratio", "E_D_supply_density_ratio"
E_LOWSTARGAP = "E_D_low_star_gap"
A_CATSCORE = "E_7b036ce9_337d76a7e2"
A_KEYWORD = "E_28767e63_ed49ab53fd"
A_BRAND = "E_28767e63_afbea52c52"
A_SALES = "E_28767e63_1af1b725ea"
# The three listings holding the top of the sales axis, by row.
A_OCCER = "E_28767e63_fa484829bb"
A_SD8K = "E_28767e63_ef9bcd4e32"
A_SD6K = "E_28767e63_a95a4b308c"

WAIVED = {
    "E_7b036ce9_67b56b611c": "品牌軸已由 amazon_products.csv 的品牌交叉表以更完整的欄位承載，這一張在分類檔上重複同一個切面且少了 rating",
    "E_7b036ce9_c337cda8ba": "銷量級距同樣在 amazon_products.csv 的交叉表出現，且那一張帶 rating，本報告的論證需要星等而不需要分類信心",
    "E_28767e63_38f7a0a2a0": "型號欄只有 64 筆有值、切成 16 組後多數組只有一件掛牌，放進來會讓讀者以為單件商品代表一個型號市場",
}

# (claim_id, evidence_ids, claim text, the argument that follows it)
CLAIMS = [
    ("es1", [E_CAT, A_KEYWORD],
     "544 件掛牌中攝影 243 件佔 44.67%、植保 63 件累積評論中位數 1.00、配件/零件 71 件；"
     "而四個關鍵字裡 drone brushless motor 一個就回收 102 件、佔 18.75%，"
     "可競爭的整機範圍遠小於掛牌總數。",
     "兩個欄位各自獨立地指向同一件事：分類把 148 件歸為零件與馬達，關鍵字則顯示 102 件來自一個只搜馬達的字串。"
     "以 544 為分母估算市場規模，等於把零件貨架與一個累積評論中位數 1.00 的品類算進可競爭範圍；"
     "進入決策要用的分母是攝影那 243 件，不是搜尋結果的總數。"),
    ("es2", [E_RVP, E_PRICE, E_CATBAND],
     "200–500 這一帶 102 則評論、12 件商品，平均星等 4.66、一二星佔比 4.90%，是聯結表最好的一格；"
     "同一帶在掛牌側只有 53 件、佔 9.74%，累積評論中位數 327.00 是全表最高，"
     "而該帶的 53 件掛牌裡攝影佔 66.04%、植保佔 9.43%。",
     "三個來自不同檔案的量指向同一個價格帶：4.66 星來自評論檔，327.00 與 53 件來自掛牌檔，"
     "66.04% 的攝影佔比來自分類檔與掛牌檔以 asin 內聯結後的交叉表。"
     "供給側只有 53 件、9.74%，代表這不是一個被塞滿的位置。"
     "結論是值得進入，而切點不只是一個價格帶：是 200–500 美元帶裡的攝影機種。"
     "這一帶 66.04% 是攝影，植保只佔 9.43%，兩者不是同一批買家，"
     "所以「進入這一帶」與「進入這一帶的攝影」在執行上是兩件事。"
     "以單一機種試水而不是鋪產品線。"
     "它的樣本很薄——12 件商品、102 則評論——資料限制一節會說明那如何限制這個結論，"
     "以及在什麼情況下這個切點應該被推翻。"),
    ("f1", [E_CAT, E_RVC],
     "攝影 243 件、佔 44.67%、累積評論中位數 225.00，且在評論側佔 405 則、平均星等 4.46、"
     "一二星 9.38%，是八個品類中規模與需求訊號同時最高的一個。",
     "規模與需求訊號通常不會同時出現在同一個品類——掛牌多的地方往往是供給過剩，評論多的地方往往是少數爆款。"
     "攝影的 243 件掛牌與 405 則評論是兩個獨立來源，而 9.38% 的一二星佔比說明那些評論多數是滿意的。"
     "三個數字一起，代表這裡的需求足以支撐多家供應商，而不是一兩件商品的長尾。"),
    ("f2", [E_CAT],
     "植保 63 件、佔 11.58%、累積評論中位數 1.00、平均星等 3.27，是八類中星等最低的一類。",
     "63 件掛牌配上這樣的評論中位數，意思是這些商品被上架但沒有被買。"
     "把它讀成「競爭尚未形成的藍海」是危險的：更可能的解釋是這個通路本身不是植保機的購買通路。"),
    ("f3", [A_KEYWORD],
     "drone brushless motor 這個關鍵字回收 102 件、佔 18.75%，價格中位數 33.61 USD，"
     "與 drone 的 99.97 USD 不在同一個價格層。",
     "同一次抓取裡出現兩個相差三倍的價格層，代表關鍵字回收的不是一個品類而是一個貨架。"
     "任何把這些掛牌當成同一個市場的平均價、平均星等，描述的都是一個不存在的商品。"),
    ("f4", [E_PRICE, E_RVP, E_SUPPLY, E_DEPTH],
     "0–30 有 99 件掛牌、佔 18.20%，累積評論中位數只有 24.00；200–500 只有 53 件、佔 9.74%，"
     "累積評論中位數 327.00，且該帶聯結後的平均星等 4.66 與一二星 4.90% 都是最好的一格。"
     "兩帶之間掛牌數是 1.87 倍，累積評論中位數是 13.6 倍。",
     "這兩帶之間，供給密度與需求厚度確實倒過來，而且倍率極不對稱：掛牌 1.87 倍，"
     "累積評論中位數 13.6 倍。"
     "本報告不把它寫成一條跨全表的規律，因為同一張表上有兩處反例："
     "0–30 的 99 件對 50–100 的 63 件，累積評論中位數是 24.00 對 22.00，掛牌少的一帶評論也少；"
     "200–500 的 53 件對 500–800 的 13 件，327.00 對 321.00，同樣同向。"
     "能站住的是這兩個端點之間的對比，而它的意思不是低價賣不動，"
     "而是低價帶的競爭者多到單件商品分不到注意力。"),
    # The band nobody in the previous recording could name, because the
    # previous recording said this table could not be built.
    ("f7", [E_CATBAND, E_CAMGAP, E_CAMRATIO, E_AGRIGAP],
     "品類佔比依價格帶的交叉表顯示：200–500 帶的 53 件掛牌中攝影佔 66.04%、"
     "500–800 帶的 13 件中佔 69.23%，是全表最高的兩格；0–30 帶的 99 件中攝影只佔 12.12%，"
     "而 800+ 帶的 53 件中攝影降到 37.74%、植保升到 32.08%。"
     "200–500 帶與 0–30 帶的攝影佔比相差 53.92 個百分點，500–800 帶是 0–30 帶的 5.71 倍，"
     "800+ 帶的植保佔比比 200–500 帶高 22.65 個百分點。",
     "這張表由分類檔與掛牌檔以 asin 內聯結而成，涵蓋 425 筆有標價的掛牌。"
     "它回答的是價格帶表單獨回答不了的問題：這條價格軸上的每一段賣的是不是同一類東西。"
     "答案是不是。0–30 帶的 12.12% 與 200–500 帶的 66.04% 相差 53.92 個百分點，"
     "低價段主要不是攝影機種；800+ 帶又是第三種東西，攝影只剩 37.74%，"
     "植保比 200–500 帶高出 22.65 個百分點，而植保這一類的累積評論中位數是 1.00。"
     "所以把整條價格軸當成一個市場來比較平均價或平均星等，比較的是三個不同的貨架；"
     "而「高價帶沒需求」這個讀法，在 800+ 這一段其實是「這一段有 32.08% 是另一個通路的商品」。"),
    ("f5", [E_PRICE],
     "500–800 只有 13 件掛牌、佔 2.39%，平均星等 4.50、累積評論中位數 321.00。",
     "這麼少的掛牌撐不起一個結論，但它與上一帶的方向一致，可以當成同一個判斷的第二個獨立佐證。"
     "把兩帶合看，兩百美元以上就是供給稀薄而需求存在的區間。"),
    ("f6", [E_RVP, E_PRICE, E_LOWSTARGAP],
     "100–200 這一帶 77 則評論、11 件商品，平均星等 4.09、一二星佔比 18.18%，是聯結表最差的一格；"
     "而掛牌側該帶有 64 件、佔 11.76%，平均星等 4.16，供給並不稀薄。"
     "它與 200–500 帶的一二星佔比相差 13.28 個百分點。",
     "18.18% 對上一帶的 4.90%，相差 13.28 個百分點，而兩格的價差只有一個級距。"
     "掛牌側 64 件、11.76% 說明這不是樣本稀少造成的雜訊，供給密度與 200–500 的 53 件相當。"
     "最合理的解釋是期待落差：買家付了不算便宜的價格，拿到的是規格妥協過的機器。"),
    ("f8", [E_DJI, A_BRAND],
     "DJI 有 92 件掛牌、佔 16.91%，價格中位數 247.50 USD；第二名 Holy Stone 只有 10 件、佔 1.84%。",
     "第一名與第二名之間差了將近一個數量級，而第二名之後迅速衰減。"
     "這不是一個多強權競爭的品類，是一家獨大加上一群規模相近的小玩家。"),
    ("f9", [E_CR3, A_BRAND],
     "在 brand 欄有值的掛牌上 CR3 為 53.62%，而品牌交叉表顯示這 207 筆之外，"
     "另有 337 筆在 brand 欄無可用值。",
     "53.62% 的分母是 207 筆，不是 544 筆；換成全檔分母則會掉到兩成上下。"
     "同一個現象在兩個分母下給出相反的印象，這是本節最容易被誤讀的地方。"),
    ("f10", [E_PAIN],
     "1–3 星區間 49 則評論中提及連線的佔 28.57%、提及故障的佔 10.20%，"
     "而 5 星以上 349 則的對應比例是 14.04% 與 3.44%。",
     "同一個主題在低分區的比例是高分區的兩倍以上，代表它是被抱怨而不是被稱讚。"
     "連線與故障是這份評論資料裡唯二具備這個性質的主題。"),
    ("f11", [E_PAIN],
     "提及影像的比例在 1–3 星是 22.45%，在 5 星以上是 36.96%，方向與連線和故障相反。",
     "影像在高分區被提得更多，代表提到它的人多半是滿意的。"
     "把提及率當成在意程度會得到相反的結論——這是同一張表裡最容易被誤讀的一列。"),
    ("f12", [E_RVC],
     "攝影類 405 則評論平均星等 4.46、一二星 9.38%；消費級/其他 8 則平均 3.12、一二星 37.50%。",
     "兩個品類的星等差距超過一顆星，而樣本量差了數十倍。"
     "後者的評論數太少，不足以下結論，列在這裡是為了說明主流用途以外的滿意度沒有被這份資料涵蓋。"),
    ("l1", [E_RVP],
     "口碑聯結表只涵蓋 373 則評論、50 件商品，其中 500+ 那一格只有 21 則評論、2 件商品。",
     "摘要那條「200–500 最好」的結論，背後只有 12 件商品。"
     "任何以這張表為基礎的價格帶排序，都必須被理解為五十件商品的排序，而不是全部掛牌的排序；"
     "這一條直接改寫了建議的強度，理由寫在建議一節。"),
    ("l2", [E_PRICE],
     "價格分組只涵蓋 425 筆，另有 119 筆在 price 欄無可用值未列入分組。",
     "缺漏不是隨機的：沒有標價的掛牌集中在 B2B 與高價端。"
     "這代表價格帶分布低估了高價端的供給，而高價端的需求同樣被銷量欄位的缺漏低估——"
     "「高價帶沒需求」不是這份資料支持的說法，只是這份資料看不見。"),
    ("l3", [A_CATSCORE],
     "分類信心分數在配件/零件 71 件是 0.00，在非無人機商品 46 件是 0.00。",
     "低信心集中在殘餘品類，代表攝影與植保這兩個承載主要結論的分類相對可靠。"
     "但它同時意味著配件與零件那個掛牌數不能拿來當成零件市場規模的估計。"),
    ("l4", [E_CR3],
     "CR3 的 53.62% 是以 brand 欄有值的掛牌為分母計算的。",
     "換一個分母，這個數字會完全改變：以全部掛牌為分母時，前三名只佔兩成上下。"
     "報告採用有品牌標示的掛牌為分母，因此品牌集中度的結論只適用於品牌側，不適用於整個貨架。"),
    # The row the tool cannot see. Every figure in the sales table is real and
    # every relation in it recomputes, and its top three tiers are a pair of
    # binoculars and two memory cards.
    ("l5", [A_SALES, A_OCCER, A_SD8K, A_SD6K],
     "銷量欄位最高的三個級距不是無人機：10K+ 那一組唯一的一件是 Occer Compact "
     "Binoculars，35.99 USD、33,535 則評論；8K+ 是 GIGASTONE Micro SD Card，"
     "64.98 USD、8,830 則評論；6K+ 也是 GIGASTONE Micro SD Card，49.99 USD、"
     "8,639 則評論。帶銷量欄位的掛牌共 165 件、佔 30.33%。",
     "任何以銷量級距排序的需求結論，最高的一端都是這三件商品在撐。"
     "它們的數字沒有一個是錯的——交叉表把它們算對了，而它們不屬於這份報告要判斷的市場。"
     "所以銷量欄位不能用來排無人機的需求，本報告的價格帶與品類結論都不使用它；"
     "這也表示「哪一段真的走量」這個問題，這份資料回答不了，"
     "必須以第三方銷量資料補上，而那份資料若顯示低價帶的頭部規模夠大，建議一節的切點就要改。"),
    ("r1", [E_RVP, E_PRICE, E_CATBAND],
     "200–500 平均星等 4.66、一二星 4.90%、聯結到 12 件商品 102 則評論，"
     "而該價格帶掛牌只有 53 件、佔 9.74%，累積評論中位數 327.00，其中攝影佔 66.04%。",
     "建議的切點是 200–500 美元帶的攝影機種。三個獨立的量支撐它，各自來自不同的檔案："
     "4.66 星來自評論檔；327.00 則累積評論中位數與 53 件、9.74% 來自掛牌檔；"
     "66.04% 的攝影佔比來自分類檔與掛牌檔以 asin 內聯結後的交叉表。"
     "4.90% 的負評率與 4.66 出自同一批 102 則評論，只是同一個訊號的第二種寫法，不另計為佐證。"
     "把品類這一腳加進來會改變執行方式：這一帶 66.04% 的掛牌是攝影，"
     "而 0–30 帶的攝影只有 12.12%，兩段賣的不是同一類商品，"
     "所以「進入 200–500」要做的是進入這一帶的攝影機種，"
     "不是在這個價位上放任何一台無人機。"),
    # The recommendation the limitations section changed.
    ("r2", [E_RVP],
     "支撐這個切點的口碑證據只有 12 件商品、102 則評論，而 500+ 那一格只有 2 件商品、21 則評論。",
     "資料限制一節指出這張表薄到什麼程度，所以這裡把建議降級：進入 200–500，"
     "但先以單一機種試水而不是鋪產品線，並在自有銷售資料累積到 50 件同帶商品之前，"
     "不要把這個價格帶的口碑優勢寫進投資假設。"
     "如果先取得的第三方銷量資料顯示低價帶的頭部規模遠大於此，正確的切點會變成 30–100，"
     "那時這份報告的建議應該被推翻而不是被修補。"),
    ("r3", [E_PAIN],
     "1–3 星區間提及連線 28.57%、提及說明 6.12%、提及故障 10.20%。",
     "產品主張應該放在連線穩定與開箱即用，而不是影像規格。"
     "低分評論裡連線的提及率是說明的數倍，而影像在低分區反而比高分區更少被提到。"),
    ("r4", [E_CAT],
     "植保 63 件掛牌的累積評論中位數是 1.00，平均星等 3.27。",
     "不建議進入植保。掛牌數配上這樣的評論中位數與平均星等，"
     "三個數字都指向這個通路上沒有交易在發生，而不是競爭者還沒到。"),
]

TABLES = {
    "structure": [
        (E_CAT, "品類結構：八個品類的規模、價格與需求訊號",
         "下表把八個品類的掛牌數、價格中位數與累積評論中位數並排，用來判斷哪一塊有真實需求。"),
        (A_KEYWORD, "四個搜尋關鍵字各自打到的價格層",
         "下表顯示四個關鍵字回收的商品在價格與評論上的差距，用來判斷它們是不是同一個市場。")],
    "price": [
        (E_PRICE, "價格帶的供給密度與需求厚度",
         "下表把每個價格帶的掛牌數與累積評論中位數放在一起，看供給與需求是否落在同一帶。"),
        (E_RVP, "口碑依價格帶（評論檔與掛牌檔以 asin 聯結）",
         "下表是把評論聯結回掛牌價格之後的結果，用來檢查上一張表的需求訊號是否對應到滿意度。"),
        (E_CATBAND, "品類佔比依價格帶（分類檔與掛牌檔以 asin 聯結）",
         "下表把品類佔比拆進每一個價格帶，用來回答價格帶表單獨回答不了的問題："
         "這條價格軸的每一段賣的是不是同一類東西。")],
    "brand": [
        (A_BRAND, "品牌側的掛牌數、價格與評論分布",
         "下表列出有品牌標示的掛牌，用來判斷這個貨架上誰真的建立了位置。")],
    "pain": [
        (E_PAIN, "痛點主題在不同星等區間的提及率",
         "下表把四個主題的提及率依星等區間拆開，差異方向比絕對值更有訊息。"),
        (E_RVC, "口碑依品類（評論檔與分類檔以 asin 聯結）",
         "下表把評論聯結回品類，用來看滿意度是否隨用途而變。")],
    "limitations": [
        (A_CATSCORE, "分類信心分數依品類",
         "下表列出每個品類的分類信心分數，用來判斷哪些品類的結論站得住。"),
        (A_SALES, "銷量級距與價格、累積評論的對應關係",
         "下表列出銷量欄位的級距，讀它之前要先看最高的三個級距是哪三件商品。")],
}

SUBSECTIONS = [
    ("structure", "品類結構：一個關鍵字貨架，四個不相干的市場", ["f1", "f2", "f3"]),
    ("price", "價格帶：三段價格，三個貨架", ["f4", "f7", "f5", "f6"]),
    ("brand", "品牌集中度：一家獨大，其餘規模相近", ["f8", "f9"]),
    ("pain", "買家痛點：低分不是因為拍得差，是連不上與壞掉", ["f10", "f11", "f12"]),
]

SECTION_CLAIMS = {
    "executive_summary": ["es1", "es2"],
    "limitations": ["l1", "l2", "l3", "l4", "l5"],
    "recommendations": ["r1", "r2", "r3", "r4"],
}

#: What each section draft calls itself on its first line. The blueprint's own
#: Chinese titles, so the merge step recognises and strips them instead of
#: leaving a second heading under the rendered one. Writing the bare
#: `section_id` here is where `## executive_summary` entered the delivered
#: document: the pipeline side of that leak was closed in 0e0a40f, this is the
#: end that produced it.
SECTION_TITLES = {
    "executive_summary": "執行摘要",
    "findings": "主要發現",
    "limitations": "資料限制與反面證據",
    "recommendations": "建議事項",
}


#: Why this recording draws no charts, checked against each of the ten
#: recommendations rather than against one of them.
#:
#: The previous recording declined all ten on the ground that "the
#: recommendations themselves flag on every one of them" that the units differ
#: and a shared Y axis would mislead. That note is on the four `table` entries
#: only; the other six recommend charts and carry no such warning. A reason
#: true of 4 of 10 was used to decline 10 of 10, which is the same defect as
#: the join sentence one section over — a false statement about the tool, used
#: to explain skipping a block of work, that no gate reads.
CHART_SELECTION_REASON = (
    "十筆推薦逐筆檢視後不畫圖，理由依推薦型別分列。"
    "四筆 table（figrec_1、4、8、9）：工具自己的理由是數值欄單位不一致、"
    "應保持表格形式，本報告照做——figrec_1 的分類信心分數與 figrec_4 的關鍵字表"
    "都以 [TABLE:] 標記置入正文；figrec_8 與 figrec_9 各自綁 544 筆逐列證據，"
    "那是來源檔的逐列清單，不是一張圖。"
    "五筆 scatter（figrec_2、3、5、6、7）：figrec_2、3、7 指向的三份證據，"
    "本報告已在 unused_derived_evidence 具名放棄並附理由；figrec_5 指向品牌表，"
    "已以表格置入；figrec_6 指向銷量級距表，而資料限制一節說明該表最高的三個級距"
    "是一副望遠鏡與兩張記憶卡，把它畫成散布圖等於把那個誤讀畫出來。"
    "一筆 histogram（figrec_10）：它綁的是 473 筆逐則評論列，"
    "而痛點分析需要的星等分布已由 [TABLE:E_D_pain_theme_by_star] 以計算過的分組表承載。"
)


def _all_packages_present(name, *args, **kwargs):
    return object()


def author(state, run: Path) -> None:
    from report_workflow.nodes.derived_evidence import apply_derived_evidence

    (run / "derived_evidence.json").write_text(
        json.dumps({"derivations": DERIVATIONS}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    report = apply_derived_evidence(state)
    if report["problems"]:
        raise SystemExit(f"derivations failed: {report['problems'][:3]}")

    by_id = {claim_id: (evidence, text, argument)
             for claim_id, evidence, text, argument in CLAIMS}
    claims = [
        {"claim_id": claim_id, "claim_text": text, "claim_type": "statistical",
         "risk_level": "low", "status": "supported", "evidence_ids": evidence,
         "requires_hedged_wording": True,
         "claim_role": "primary" if claim_id in {"es1", "es2", "r1"} else "supporting"}
        for claim_id, evidence, text, _argument in CLAIMS
    ]
    (run / "claim_matrix.json").write_text(
        json.dumps({"claims": claims}, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    plan_path = run / "section_drafts" / "figure_plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    if plan_path.exists():
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
        payload["figures"] = []
        payload["chart_selection_reason"] = CHART_SELECTION_REASON
        plan_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    outline = {"sections": {
        "executive_summary": {
            "section_id": "executive_summary", "goals": "直接回答值不值得進入與從哪個切點進入",
            "claim_ids": SECTION_CLAIMS["executive_summary"],
            "paragraph_order": ["結論", "依據", "限制"], "figure_ids": []},
        "findings": {
            "section_id": "findings", "goals": "四個面向的結構性發現",
            "paragraph_order": ["觀察", "證據", "推論"], "figure_ids": [],
            "subsections": [
                {"subsection_id": key, "title": title, "claim_ids": claim_ids}
                for key, title, claim_ids in SUBSECTIONS]},
        "limitations": {
            "section_id": "limitations", "goals": "指出哪些證據會削弱上面的結論",
            "claim_ids": SECTION_CLAIMS["limitations"],
            "paragraph_order": ["限制", "影響哪一條結論"], "figure_ids": []},
        "recommendations": {
            "section_id": "recommendations", "goals": "回答任務敘述的兩個問題",
            "claim_ids": SECTION_CLAIMS["recommendations"],
            "paragraph_order": ["建議", "理由", "降級的部分"], "figure_ids": []},
    }, "unused_derived_evidence": WAIVED}
    (run / "outline.json").write_text(
        json.dumps(outline, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    rows: list[dict] = []

    def paragraph(section_id: str, claim_id: str) -> str:
        evidence, text, argument = by_id[claim_id]
        rows.append({
            "sentence_id": f"s_{section_id}_{claim_id}", "section_id": section_id,
            "claim_ids": [claim_id], "evidence_ids": evidence,
            "citation_ids": evidence, "wording_strength": "hedged",
            "draft_origin": "agent_draft"})
        cite = " ".join(f"[CITE:{eid}]" for eid in evidence)
        return f"{text} {cite}{argument}"

    def tables_for(key: str) -> list[str]:
        block: list[str] = []
        for evidence_id, caption, lead_in in TABLES.get(key, []):
            block.extend([lead_in, "", f"[TABLE:{evidence_id} {caption}]", ""])
        return block

    section_dir = run / "section_drafts"
    section_dir.mkdir(exist_ok=True)

    for section_id in ("executive_summary", "recommendations"):
        lines = [f"# {SECTION_TITLES[section_id]}", ""]
        for claim_id in SECTION_CLAIMS[section_id]:
            lines.extend([paragraph(section_id, claim_id), ""])
        (section_dir / f"{section_id}.md").write_text("\n".join(lines), encoding="utf-8")

    lines = [f"# {SECTION_TITLES['findings']}", ""]
    for key, title, claim_ids in SUBSECTIONS:
        lines.extend([f"## {title}", "", paragraph("findings", claim_ids[0]), ""])
        lines.extend(tables_for(key))
        for claim_id in claim_ids[1:]:
            lines.extend([paragraph("findings", claim_id), ""])
    (section_dir / "findings.md").write_text("\n".join(lines), encoding="utf-8")

    lines = [f"# {SECTION_TITLES['limitations']}", ""]
    for claim_id in ("l1", "l2"):
        lines.extend([paragraph("limitations", claim_id), ""])
    lines.extend(tables_for("limitations"))
    for claim_id in ("l3", "l4", "l5"):
        lines.extend([paragraph("limitations", claim_id), ""])
    (section_dir / "limitations.md").write_text("\n".join(lines), encoding="utf-8")

    with open(run / "sentence_map.jsonl", "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def docx_as_text(path: str) -> tuple[str, int]:
    """The delivered document in document order, headings and tables intact."""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(path)
    parts: list[str] = []
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            style = paragraph.style.name or ""
            if style.startswith("Heading"):
                try:
                    level = int(style.split()[-1])
                except ValueError:
                    level = 1
                parts.append("#" * max(1, level) + " " + text)
            elif style == "TOC Heading":
                parts.append("## " + text)
            else:
                parts.append(text)
        elif child.tag.endswith("}tbl"):
            table = Table(child, document)
            grid = ["| " + " | ".join(c.text.strip() for c in row.cells) + " |"
                    for row in table.rows]
            if grid:
                columns = len(table.rows[0].cells)
                grid.insert(1, "|" + "|".join(" --- " for _ in range(columns)) + "|")
            parts.append("\n".join(grid))
    return "\n\n".join(parts), len(document.tables)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="score the run but leave the fixture alone")
    args = parser.parse_args(argv)

    from report_workflow.run_workflow import (
        prepare_workflow, render_workflow, validate_workflow,
    )
    from report_workflow.runtime_support import run_dir_for
    from report_axes import score_layout
    from run_report_quality_benchmark import score_document

    workdir = Path(tempfile.mkdtemp(prefix="toolarm_"))
    try:
        sources = [str(path) for path in sorted(SOURCE_DIR.glob("*.csv"))]
        with patch("report_workflow.preflight.importlib.util.find_spec",
                   side_effect=_all_packages_present):
            state = prepare_workflow(PROMPT, sources, str(workdir / "out"),
                                     report_profile="business_report")
        author(state, run_dir_for(state))
        validated = validate_workflow(state.job_id, workspace_root=str(workdir / "out"))
        decision = (validated.qa or {}).get("qa_decision")
        if decision != "pass":
            print("validate did not pass:", decision)
            print(json.dumps((validated.qa or {}).get("blockers", []),
                             ensure_ascii=False)[:1200])
            return 1
        rendered = render_workflow(state.job_id, workspace_root=str(workdir / "out"))
        docx_path = (rendered.output.get("published_report_path")
                     or rendered.output.get("final_docx_path")
                     or rendered.output.get("rendered_docx_path"))
        text, table_count = docx_as_text(docx_path)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    source = "\n".join(p.read_text(encoding="utf-8")
                       for p in sorted(SOURCE_DIR.glob("*.csv")))
    numeric = score_document(text, source)
    layout = score_layout(text)
    print(f"chars {len(text)}  tables {table_count}")
    print("numeric", json.dumps(numeric, ensure_ascii=False))
    print("layout ", json.dumps(layout, ensure_ascii=False))

    if args.dry_run:
        return 0

    from run_report_quality_benchmark import body_digest

    header = FIXTURE.read_text(encoding="utf-8").split("-->\n\n", 1)[0]
    header = header.split("Measured when recorded:")[0] + (
        f"Measured when recorded: {len(text):,} characters, "
        f"{numeric['verifiable_numbers']} traceable figures, {table_count} tables.\n"
    )
    # The digest is taken over the file with every comment block removed, so
    # writing it into the header does not change it. Regenerated here rather
    # than by hand: this arm is not frozen, and a hash that has to be updated
    # manually after a re-recording is a hash that will be stale.
    contents = header + "-->\n\n" + text
    header += f"Body SHA-256: {body_digest(contents)}\n"
    FIXTURE.write_text(header + "-->\n\n" + text, encoding="utf-8")
    print("fixture rewritten:", FIXTURE.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
