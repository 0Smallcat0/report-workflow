# 廢棄物回收利用經濟性分析

<!--
RECORDED SAMPLE — do not edit to make the benchmark look better.

This is one write-up of `recycling_market_report.md`, produced from the same
source and the same brief with no harness in the loop. It is checked in so the
comparison is reproducible; regenerating it would move the numbers for reasons
that have nothing to do with the pipeline.

It is deliberately not a strawman. The prose is competent, the structure is
sound, and it reads well — which is the point. What it does not do is carry its
sources into the text, keep the source's tables, or disclose how a derived
number was derived. Those are the properties the harness makes non-optional,
and this file is the honest measure of what happens when nothing enforces them.
-->

## 執行摘要

四個回收品類的經濟性差異主要來自成本結構而非技術成熟度。電池回收的毛利受碳酸鋰
價格週期支配，塑膠受原油價格牽動，紡織的瓶頸在人工分選成本，紙張則由區域物流決定。
整體而言，白紙與舊瓦楞紙的單位經濟性最穩健，混紡紡織品最差。

## 主要發現

鋰電池方面，濕法冶金製程的回收率可以達到 95% 以上，是目前商業化程度最高的路線。
不過碳酸鋰價格在過去三年劇烈波動，從高點約八萬美元一路跌到八千多美元後才回升到
兩萬上下，這使得黑粉的收購意願隨行情大幅起伏。以目前價位估算，單噸黑粉的鋰金屬
收入大約落在兩千四百美元左右，但這個數字對價格假設非常敏感。

塑膠回收的關鍵在於再生料與原生料的價差。機械回收的產出率約七成，單位成本兩百一
十美元，換算後每噸再生料的攤銷成本接近三百美元；溶劑回收與化學解聚的成本則明顯
更高。美國市場近期原生 PET 報價下滑，導致再生廠陸續關閉，這說明再生料需求對原油
價格的敏感度高於對回收量的敏感度。

紡織品回收的困難不在處理而在分選。純棉與聚酯的分選準確率都接近九成，混紡卻只有
一半左右，噸成本也因此接近純棉的兩倍。自動化光譜分選設備理論上可以改善，但實際
導入案例的回收期普遍偏長。

紙張方面，舊瓦楞紙的回收率約七成、成本最低廉，白紙因為油墨少、脫墨成本低，單位
經濟性最好，混合紙則兩者皆不如。三者之間的價差主要由區域供需決定。

## 建議事項

若要投入回收產業，建議優先評估紙張品類，其成本結構最單純且波動來源可預測。電池
回收的長期報酬可能更高，但需要能承受原料價格週期的資本結構。紡織品回收在自動化
分選成本下降之前，不建議作為主要投入標的。

四個品類的成本驅動因子彼此獨立，因此同時投入多個品類並不能有效分散風險，這一點
在配置資金時需要納入考量。
