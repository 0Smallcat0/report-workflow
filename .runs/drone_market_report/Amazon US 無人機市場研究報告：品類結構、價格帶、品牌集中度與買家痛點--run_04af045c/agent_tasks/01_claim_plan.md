# 01 Claim Plan

You are operating inside an agent/coding environment. Do not call any external API from the workflow code.

## Inputs
- Report spec: `D:\report_workflow\.runs\drone_market_report\Amazon US 無人機市場研究報告：品類結構、價格帶、品牌集中度與買家痛點--run_04af045c\report_spec.json`
- Blueprint: `D:\report_workflow\.runs\drone_market_report\Amazon US 無人機市場研究報告：品類結構、價格帶、品牌集中度與買家痛點--run_04af045c\blueprint.json`
- Evidence ledger: `D:\report_workflow\.runs\drone_market_report\Amazon US 無人機市場研究報告：品類結構、價格帶、品牌集中度與買家痛點--run_04af045c\evidence_ledger.jsonl`

## Required Output
Write `D:\report_workflow\.runs\drone_market_report\Amazon US 無人機市場研究報告：品類結構、價格帶、品牌集中度與買家痛點--run_04af045c\claim_matrix.json` with this shape:

```json
{
  "_contract": {
  "job_id": "run_04af045c",
  "evidence_ledger_hash": "cf57169778c2e1b3",
  "source_registry_hash": "525de3e5b77b7205"
},
  "claims": [
    {
      "claim_id": "c1",
      "claim_text": "Specific evidence-backed claim.",
      "claim_type": "factual|statistical|methodological|regulatory|qualitative|contextual",
      "risk_level": "low|medium|high",
      "status": "supported",
      "evidence_ids": ["evidence id from evidence_ledger.jsonl"],
      "requires_hedged_wording": false,
      "claim_role": "primary|supporting|background"
    }
  ]
}
```

## Artifact Contract
Keep `_contract` exactly aligned with this run. If you reuse artifacts from an older job,
run `remap_agent_artifacts(job_id="run_04af045c", previous_job_id="<old>", write=true)`
instead of manually copying evidence IDs.

Do not edit `merged_draft.md`, checkpoint files, or `base_document_sections.json`.
For `new_draft`, the editable artifacts are `claim_matrix.json`, `outline.json`,
`section_drafts/*.md`, and `sentence_map.jsonl`.

## Hard Rules
- Every claim must have at least one `evidence_id`.
- Use only evidence IDs from `evidence_ledger.jsonl`.
- Do not use `blocked`, `unverified`, or `disputed` for publishable claims.
- Statistical claims require quantitative evidence.
- For internal project documents, use `factual`, `methodological`, or `qualitative`
  claims unless the evidence explicitly allows `statistical`.
- Mark medium-grade or qualitative source wording as hedged in `sentence_map.jsonl`;
  reserve `measured` wording for high-grade evidence (FD blocks it on
  medium-grade evidence even when that evidence is quantitative).
- `claim_role` is optional for `business_report`. Set it if it helps you keep the argument straight; nothing validates it for this profile.

## Derived Statistics (citable, computed from the source rows)

These are ordinary evidence entries whose values the pipeline computed
from the rows, so citing one puts a checked figure in the document.
They are listed here in full because they sit at the end of the ledger,
past the sample the Evidence Summary shows.

Computed automatically at intake (25):

### `E_28767e63_00b29bbe70` — cite with `[CITE:E_28767e63_00b29bbe70]`.

```
衍生統計(來源:amazon_products.csv):本樣本共收錄 544 筆資料列，總筆數 544 筆，欄位 12 個。各欄有值筆數為 asin 544 筆、title 544 筆、brand 207 筆、seller 11 筆、model 64 筆、price 425 筆、rating 376 筆、review_count 333 筆、sales 165 筆、product_link 544 筆、image_url 544 筆、keyword 544 筆。
```
### `E_28767e63_afdac4a7c6` — cite with `[CITE:E_28767e63_afdac4a7c6]`.

```
衍生統計(來源:amazon_products.csv):brand 欄共 54 個相異值、207 筆有值資料列。分布為 DJI 92 筆(44.4%)、Holy Stone 10 筆(4.8%)、Contixo 9 筆(4.3%)、Potensic 9 筆(4.3%)、BetaFPV 8 筆(3.9%)、Antigravity 6 筆(2.9%)、Autel 6 筆(2.9%)、Cozyego 4 筆(1.9%)、Ruko 4 筆(1.9%)、MAD COMPONENTS 3 筆(1.4%)、Parrot 3 筆(1.4%)、Bwine 2 筆(1.0%)、CADDXFPV 2 筆(1.0%)、MOCVOO 2 筆(1.0%)、Midzooparts 2 筆(1.0%)。前五大合計佔 61.8%，以此欄計算的 HHI 為 2097。
```
### `E_28767e63_c52b27b8f6` — cite with `[CITE:E_28767e63_c52b27b8f6]`.

```
衍生統計(來源:amazon_products.csv):seller 欄共 11 個相異值、11 筆有值資料列。分布為 BraveEdge Tech 1 筆(9.1%)、DJI Gear Center 1 筆(9.1%)、Derry Tech 1 筆(9.1%)、DroneFinds-Hub 1 筆(9.1%)、HOVERAir Official 1 筆(9.1%)、Maxuparts 1 筆(9.1%)、Precision Delivery LLC 1 筆(9.1%)、SkywalkerRC 1 筆(9.1%)、XYY PARTS STORE 1 筆(9.1%)、one-martian 1 筆(9.1%)、zhengzhouhonglushangmaoyouxiangongsi 1 筆(9.1%)。前五大合計佔 45.5%，以此欄計算的 HHI 為 909。
```
### `E_28767e63_a5713cf10f` — cite with `[CITE:E_28767e63_a5713cf10f]`.

```
衍生統計(來源:amazon_products.csv):model 欄共 59 個相異值、64 筆有值資料列。分布為 DJI Mini 3 3 筆(4.7%)、DJI Mini 4 Pro 2 筆(3.1%)、DJI Neo 2 筆(3.1%)、DSDR23A 2 筆(3.1%)、8112 IPE Silver 100KV 1 筆(1.6%)、ATOM 2 1 筆(1.6%)、Air65 II 1 筆(1.6%)、Avatar Pro Kit 1 筆(1.6%)、BAT S Series RC Quadcopter Motor 1 筆(1.6%)、Brushless Motor 1 筆(1.6%)、CxzHtv86564 1 筆(1.6%)、D20 1 筆(1.6%)、DJI Avata 2 1 筆(1.6%)、DJI Mini 5 Pro 1 筆(1.6%)、DJI NEO 2 1 筆(1.6%)。前五大合計佔 15.6%，以此欄計算的 HHI 為 186。
```
### `E_28767e63_020c41e5a7` — cite with `[CITE:E_28767e63_020c41e5a7]`.

```
衍生統計(來源:amazon_products.csv):price 欄共 425 筆數值，最小值 0 USD，第一四分位 32.99 USD，中位數 71.99 USD，平均數 735.50 USD，第三四分位 269.99 USD，最大值 36,999 USD。
```
### `E_28767e63_542da20982` — cite with `[CITE:E_28767e63_542da20982]`.

```
衍生統計(來源:amazon_products.csv):rating 欄共 376 筆數值，最小值 1.80，第一四分位 4，中位數 4.30，平均數 4.26，第三四分位 4.60，最大值 5。
```
### `E_28767e63_c1485e6c92` — cite with `[CITE:E_28767e63_c1485e6c92]`.

```
衍生統計(來源:amazon_products.csv):review_count 欄共 333 筆數值，最小值 1，第一四分位 13，中位數 70，平均數 945.92，第三四分位 515，最大值 33,535。
```
### `E_28767e63_4f305b8385` — cite with `[CITE:E_28767e63_4f305b8385]`.

```
衍生統計(來源:amazon_products.csv):sales 欄共 15 個相異值、165 筆有值資料列。分布為 100+ bought in past month 46 筆(27.9%)、50+ bought in past month 34 筆(20.6%)、200+ bought in past month 22 筆(13.3%)、500+ bought in past month 16 筆(9.7%)、400+ bought in past month 12 筆(7.3%)、1K+ bought in past month 11 筆(6.7%)、300+ bought in past month 11 筆(6.7%)、2K+ bought in past month 5 筆(3.0%)、3K+ bought in past month 2 筆(1.2%)、10K+ bought in past month 1 筆(0.6%)、4K+ bought in past month 1 筆(0.6%)、5K+ bought in past month 1 筆(0.6%)、600+ bought in past month 1 筆(0.6%)、6K+ bought in past month 1 筆(0.6%)、8K+ bought in past month 1 筆(0.6%)。前五大合計佔 78.8%，以此欄計算的 HHI 為 1628。
```
### `E_28767e63_2f658f6efa` — cite with `[CITE:E_28767e63_2f658f6efa]`.

```
衍生統計(來源:amazon_products.csv):keyword 欄共 4 個相異值、544 筆有值資料列。分布為 drone 279 筆(51.3%)、agricultural spray drone 111 筆(20.4%)、drone brushless motor 102 筆(18.8%)、thermal imaging drone 52 筆(9.6%)。前五大合計佔 100.0%，以此欄計算的 HHI 為 3490。
```
### `E_28767e63_ed49ab53fd`
Place this table with `[TABLE:E_28767e63_ed49ab53fd <caption>]`; the renderer rebuilds it as a real Word table with its provenance underneath. Cite a number you discuss in the prose with `[CITE:E_28767e63_ed49ab53fd]`.

```
衍生統計(來源:amazon_products.csv):keyword 分組交叉表。依 keyword 分為 4 組，涵蓋 544 筆資料列（全檔 544 筆）。
keyword | 筆數 | 佔比 | price 平均 | price 中位數 | rating 平均 | rating 中位數 | review_count 中位數
drone | 279 | 51.29% | 1,085.70 USD | 99.97 USD | 4.27 | 4.30 | 197.00
agricultural spray drone | 111 | 20.40% | 705.99 USD | 113.29 USD | 3.77 | 3.95 | 11.50
drone brushless motor | 102 | 18.75% | 56.45 USD | 33.61 USD | 4.38 | 4.40 | 14.00
thermal imaging drone | 52 | 9.56% | 298.69 USD | 124.99 USD | 4.25 | 4.40 | 92.00
合計 | 544 | 100.00% | 735.50 USD | 71.99 USD | 4.26 | 4.30 | 70.00
```
### `E_28767e63_afbea52c52`
Place this table with `[TABLE:E_28767e63_afbea52c52 <caption>]`; the renderer rebuilds it as a real Word table with its provenance underneath. Cite a number you discuss in the prose with `[CITE:E_28767e63_afbea52c52]`.

```
衍生統計(來源:amazon_products.csv):brand 分組交叉表。依 brand 分為 16 組，涵蓋 207 筆資料列（全檔 544 筆）。另有 337 筆在該欄無可用值，未列入分組。
brand | 筆數 | 佔比 | price 平均 | price 中位數 | rating 平均 | rating 中位數 | review_count 中位數
DJI | 92 | 16.91% | 1,077.30 USD | 247.50 USD | 4.39 | 4.50 | 307.00
Holy Stone | 10 | 1.84% | 138.40 USD | 139.99 USD | 4.13 | 4.20 | 2,780.00
Contixo | 9 | 1.65% | 209.43 USD | 149.99 USD | 3.64 | 3.70 | 28.00
Potensic | 9 | 1.65% | 323.77 USD | 279.99 USD | 4.49 | 4.50 | 1,871.00
BetaFPV | 8 | 1.47% | 152.12 USD | 117.99 USD | 4.04 | 4.00 | 12.00
Antigravity | 6 | 1.10% | 1,599.00 USD | 1,599.00 USD | 4.20 | 4.60 | 1.00
Autel | 6 | 1.10% | 3,979.00 USD | 3,289.00 USD | 4.47 | 4.50 | 11.00
Cozyego | 4 | 0.74% | 61.23 USD | 56.98 USD | 4.65 | 4.85 | 4.00
Ruko | 4 | 0.74% | 454.99 USD | 449.99 USD | 4.45 | 4.45 | 175.50
MAD COMPONENTS | 3 | 0.55% | 182.99 USD | 227.99 USD | — | — | —
Parrot | 3 | 0.55% | — | — | 3.80 | 3.80 | 198.00
Bwine | 2 | 0.37% | 399.98 USD | 399.98 USD | 4.45 | 4.45 | 794.00
CADDXFPV | 2 | 0.37% | 149.99 USD | 149.99 USD | 3.15 | 3.15 | 39.00
MOCVOO | 2 | 0.37% | 26.99 USD | 26.99 USD | 3.75 | 3.75 | 901.00
Midzooparts | 2 | 0.37% | 66.14 USD | 66.14 USD | — | — | —
其他（39 組） | 45 | 8.27% | 470.16 USD | 59.99 USD | 4.30 | 4.30 | 82.00
合計 | 207 | 38.05% | 714.22 USD | 119.99 USD | 4.29 | 4.40 | 140.00
```
### `E_28767e63_1af1b725ea`
Place this table with `[TABLE:E_28767e63_1af1b725ea <caption>]`; the renderer rebuilds it as a real Word table with its provenance underneath. Cite a number you discuss in the prose with `[CITE:E_28767e63_1af1b725ea]`.

```
衍生統計(來源:amazon_products.csv):sales 分組交叉表。依 sales 分為 15 組，涵蓋 165 筆資料列（全檔 544 筆）。另有 379 筆在該欄無可用值，未列入分組。
sales | 筆數 | 佔比 | price 平均 | price 中位數 | rating 平均 | rating 中位數 | review_count 中位數
100+ bought in past month | 46 | 8.46% | 362.10 USD | 89.99 USD | 4.22 | 4.35 | 198.00
50+ bought in past month | 34 | 6.25% | 101.56 USD | 57.99 USD | 4.24 | 4.20 | 121.00
200+ bought in past month | 22 | 4.04% | 122.09 USD | 119.98 USD | 4.28 | 4.25 | 794.00
500+ bought in past month | 16 | 2.94% | 245.15 USD | 139.99 USD | 4.37 | 4.40 | 806.00
400+ bought in past month | 12 | 2.21% | 201.17 USD | 47.99 USD | 4.38 | 4.35 | 413.00
1K+ bought in past month | 11 | 2.02% | 68.58 USD | 41.36 USD | 4.42 | 4.50 | 776.50
300+ bought in past month | 11 | 2.02% | 500.32 USD | 236.00 USD | 4.40 | 4.40 | 327.00
2K+ bought in past month | 5 | 0.92% | 323.89 USD | 59.97 USD | 4.32 | 4.40 | 1,166.00
3K+ bought in past month | 2 | 0.37% | 214.49 USD | 214.49 USD | 4.35 | 4.35 | 1,796.50
10K+ bought in past month | 1 | 0.18% | 35.99 USD | 35.99 USD | 4.40 | 4.40 | 33,535.00
4K+ bought in past month | 1 | 0.18% | 299.00 USD | 299.00 USD | 4.50 | 4.50 | 3,965.00
5K+ bought in past month | 1 | 0.18% | 29.58 USD | 29.58 USD | 4.00 | 4.00 | —
600+ bought in past month | 1 | 0.18% | 49.98 USD | 49.98 USD | 3.90 | 3.90 | 131.00
6K+ bought in past month | 1 | 0.18% | 49.99 USD | 49.99 USD | 4.60 | 4.60 | 8,639.00
8K+ bought in past month | 1 | 0.18% | 64.98 USD | 64.98 USD | 4.60 | 4.60 | 8,830.00
合計 | 165 | 30.33% | 227.31 USD | 69.99 USD | 4.29 | 4.30 | 328.00
```
### `E_28767e63_38f7a0a2a0`
Place this table with `[TABLE:E_28767e63_38f7a0a2a0 <caption>]`; the renderer rebuilds it as a real Word table with its provenance underneath. Cite a number you discuss in the prose with `[CITE:E_28767e63_38f7a0a2a0]`.

```
衍生統計(來源:amazon_products.csv):model 分組交叉表。依 model 分為 16 組，涵蓋 64 筆資料列（全檔 544 筆）。另有 480 筆在該欄無可用值，未列入分組。
model | 筆數 | 佔比 | price 平均 | price 中位數 | rating 平均 | rating 中位數 | review_count 中位數
DJI Mini 3 | 3 | 0.55% | — | — | 4.53 | 4.50 | 2,547.00
DJI Mini 4 Pro | 2 | 0.37% | — | — | 4.45 | 4.45 | 2,402.00
DJI Neo | 2 | 0.37% | — | — | 4.50 | 4.50 | 2,585.00
DSDR23A | 2 | 0.37% | 416.99 USD | 416.99 USD | 4.50 | 4.50 | 1,871.50
8112 IPE Silver 100KV | 1 | 0.18% | 227.99 USD | 227.99 USD | — | — | —
ATOM 2 | 1 | 0.18% | 249.99 USD | 249.99 USD | 4.70 | 4.70 | 23.00
Air65 II | 1 | 0.18% | 115.99 USD | 115.99 USD | 5.00 | 5.00 | 4.00
Avatar Pro Kit | 1 | 0.18% | 169.99 USD | 169.99 USD | 4.50 | 4.50 | 75.00
BAT S Series RC Quadcopter Motor | 1 | 0.18% | 65.92 USD | 65.92 USD | — | — | —
Brushless Motor | 1 | 0.18% | 24.99 USD | 24.99 USD | 5.00 | 5.00 | 1.00
CxzHtv86564 | 1 | 0.18% | 1,236.14 USD | 1,236.14 USD | — | — | —
D20 | 1 | 0.18% | 49.99 USD | 49.99 USD | 4.00 | 4.00 | 19,425.00
DJI Avata 2 | 1 | 0.18% | — | — | 4.60 | 4.60 | 515.00
DJI Mini 5 Pro | 1 | 0.18% | 1,159.00 USD | 1,159.00 USD | 4.40 | 4.40 | 698.00
DJI NEO 2 | 1 | 0.18% | — | — | 4.60 | 4.60 | 858.00
其他（44 組） | 44 | 8.09% | 166.30 USD | 72.49 USD | 4.08 | 4.20 | 115.00
合計 | 64 | 11.76% | 211.49 USD | 92.99 USD | 4.22 | 4.40 | 260.00
```
### `E_7b036ce9_bb4c554261` — cite with `[CITE:E_7b036ce9_bb4c554261]`.

```
衍生統計(來源:amazon_classified.csv):本樣本共收錄 544 筆資料列，總筆數 544 筆，欄位 9 個。各欄有值筆數為 asin 544 筆、title 544 筆、brand 207 筆、price 425 筆、sales 165 筆、review_count 333 筆、category 544 筆、score 544 筆、matched 503 筆。
```
### `E_7b036ce9_946f23cfa1` — cite with `[CITE:E_7b036ce9_946f23cfa1]`.

```
衍生統計(來源:amazon_classified.csv):brand 欄共 54 個相異值、207 筆有值資料列。分布為 DJI 92 筆(44.4%)、Holy Stone 10 筆(4.8%)、Contixo 9 筆(4.3%)、Potensic 9 筆(4.3%)、BetaFPV 8 筆(3.9%)、Antigravity 6 筆(2.9%)、Autel 6 筆(2.9%)、Cozyego 4 筆(1.9%)、Ruko 4 筆(1.9%)、MAD COMPONENTS 3 筆(1.4%)、Parrot 3 筆(1.4%)、Bwine 2 筆(1.0%)、CADDXFPV 2 筆(1.0%)、MOCVOO 2 筆(1.0%)、Midzooparts 2 筆(1.0%)。前五大合計佔 61.8%，以此欄計算的 HHI 為 2097。
```
### `E_7b036ce9_3277293859` — cite with `[CITE:E_7b036ce9_3277293859]`.

```
衍生統計(來源:amazon_classified.csv):price 欄共 425 筆數值，最小值 0 USD，第一四分位 32.99 USD，中位數 71.99 USD，平均數 735.50 USD，第三四分位 269.99 USD，最大值 36,999 USD。
```
### `E_7b036ce9_0cb75ded9f` — cite with `[CITE:E_7b036ce9_0cb75ded9f]`.

```
衍生統計(來源:amazon_classified.csv):sales 欄共 15 個相異值、165 筆有值資料列。分布為 100+ bought in past month 46 筆(27.9%)、50+ bought in past month 34 筆(20.6%)、200+ bought in past month 22 筆(13.3%)、500+ bought in past month 16 筆(9.7%)、400+ bought in past month 12 筆(7.3%)、1K+ bought in past month 11 筆(6.7%)、300+ bought in past month 11 筆(6.7%)、2K+ bought in past month 5 筆(3.0%)、3K+ bought in past month 2 筆(1.2%)、10K+ bought in past month 1 筆(0.6%)、4K+ bought in past month 1 筆(0.6%)、5K+ bought in past month 1 筆(0.6%)、600+ bought in past month 1 筆(0.6%)、6K+ bought in past month 1 筆(0.6%)、8K+ bought in past month 1 筆(0.6%)。前五大合計佔 78.8%，以此欄計算的 HHI 為 1628。
```
### `E_7b036ce9_0bf8d22c42` — cite with `[CITE:E_7b036ce9_0bf8d22c42]`.

```
衍生統計(來源:amazon_classified.csv):review_count 欄共 333 筆數值，最小值 1，第一四分位 13，中位數 70，平均數 945.92，第三四分位 515，最大值 33,535。
```
### `E_7b036ce9_272ec71407` — cite with `[CITE:E_7b036ce9_272ec71407]`.

```
衍生統計(來源:amazon_classified.csv):category 欄共 8 個相異值、544 筆有值資料列。分布為 攝影 243 筆(44.7%)、無人機馬達 77 筆(14.2%)、配件/零件 71 筆(13.1%)、植保 63 筆(11.6%)、非無人機商品 46 筆(8.5%)、消費級/其他 22 筆(4.0%)、多用途 14 筆(2.6%)、消防投彈 8 筆(1.5%)。前五大合計佔 91.9%，以此欄計算的 HHI 為 2597。
```
### `E_7b036ce9_36ca2d0b67` — cite with `[CITE:E_7b036ce9_36ca2d0b67]`.

```
衍生統計(來源:amazon_classified.csv):score 欄共 544 筆數值，最小值 0，第一四分位 0，中位數 2，平均數 2.89，第三四分位 4，最大值 15。
```
### `E_7b036ce9_337d76a7e2`
Place this table with `[TABLE:E_7b036ce9_337d76a7e2 <caption>]`; the renderer rebuilds it as a real Word table with its provenance underneath. Cite a number you discuss in the prose with `[CITE:E_7b036ce9_337d76a7e2]`.

```
衍生統計(來源:amazon_classified.csv):category 分組交叉表。依 category 分為 8 組，涵蓋 544 筆資料列（全檔 544 筆）。
category | 筆數 | 佔比 | price 平均 | price 中位數 | review_count 平均 | review_count 中位數 | score 中位數
攝影 | 243 | 44.67% | 535.95 USD | 139.98 USD | 1,115.95 | 225.00 | 4.00
無人機馬達 | 77 | 14.15% | 54.02 USD | 32.70 USD | 48.08 | 14.00 | 2.00
配件/零件 | 71 | 13.05% | 514.52 USD | 79.58 USD | 281.70 | 51.00 | 0.00
植保 | 63 | 11.58% | 1,008.44 USD | 122.46 USD | 176.57 | 1.00 | 6.00
非無人機商品 | 46 | 8.46% | 1,976.10 USD | 29.97 USD | 1,918.41 | 23.50 | 0.00
消費級/其他 | 22 | 4.04% | 43.13 USD | 38.97 USD | 2,658.00 | 223.00 | 0.00
多用途 | 14 | 2.57% | 4,800.36 USD | 3,579.00 USD | 7.43 | 5.00 | 0.00
消防投彈 | 8 | 1.47% | 359.08 USD | 39.99 USD | 30.17 | 12.00 | 2.00
合計 | 544 | 100.00% | 735.50 USD | 71.99 USD | 945.92 | 70.00 | 2.00
```
### `E_7b036ce9_67b56b611c`
Place this table with `[TABLE:E_7b036ce9_67b56b611c <caption>]`; the renderer rebuilds it as a real Word table with its provenance underneath. Cite a number you discuss in the prose with `[CITE:E_7b036ce9_67b56b611c]`.

```
衍生統計(來源:amazon_classified.csv):brand 分組交叉表。依 brand 分為 16 組，涵蓋 207 筆資料列（全檔 544 筆）。另有 337 筆在該欄無可用值，未列入分組。
brand | 筆數 | 佔比 | price 平均 | price 中位數 | review_count 平均 | review_count 中位數 | score 中位數
DJI | 92 | 16.91% | 1,077.30 USD | 247.50 USD | 1,151.12 | 307.00 | 3.00
Holy Stone | 10 | 1.84% | 138.40 USD | 139.99 USD | 6,091.57 | 2,780.00 | 3.00
Contixo | 9 | 1.65% | 209.43 USD | 149.99 USD | 42.86 | 28.00 | 3.00
Potensic | 9 | 1.65% | 323.77 USD | 279.99 USD | 2,604.33 | 1,871.00 | 6.00
BetaFPV | 8 | 1.47% | 152.12 USD | 117.99 USD | 53.29 | 12.00 | 2.50
Antigravity | 6 | 1.10% | 1,599.00 USD | 1,599.00 USD | 36.33 | 1.00 | 2.00
Autel | 6 | 1.10% | 3,979.00 USD | 3,289.00 USD | 53.00 | 11.00 | 2.00
Cozyego | 4 | 0.74% | 61.23 USD | 56.98 USD | 3.50 | 4.00 | 2.00
Ruko | 4 | 0.74% | 454.99 USD | 449.99 USD | 356.50 | 175.50 | 11.00
MAD COMPONENTS | 3 | 0.55% | 182.99 USD | 227.99 USD | — | — | 2.00
Parrot | 3 | 0.55% | — | — | 489.00 | 198.00 | 1.00
Bwine | 2 | 0.37% | 399.98 USD | 399.98 USD | 794.00 | 794.00 | 9.50
CADDXFPV | 2 | 0.37% | 149.99 USD | 149.99 USD | 39.00 | 39.00 | 3.00
MOCVOO | 2 | 0.37% | 26.99 USD | 26.99 USD | 901.00 | 901.00 | 4.00
Midzooparts | 2 | 0.37% | 66.14 USD | 66.14 USD | — | — | 5.00
其他（39 組） | 45 | 8.27% | 470.16 USD | 59.99 USD | 1,121.08 | 82.00 | 2.00
合計 | 207 | 38.05% | 714.22 USD | 119.99 USD | 1,206.95 | 140.00 | 3.00
```
### `E_7b036ce9_c337cda8ba`
Place this table with `[TABLE:E_7b036ce9_c337cda8ba <caption>]`; the renderer rebuilds it as a real Word table with its provenance underneath. Cite a number you discuss in the prose with `[CITE:E_7b036ce9_c337cda8ba]`.

```
衍生統計(來源:amazon_classified.csv):sales 分組交叉表。依 sales 分為 15 組，涵蓋 165 筆資料列（全檔 544 筆）。另有 379 筆在該欄無可用值，未列入分組。
sales | 筆數 | 佔比 | price 平均 | price 中位數 | review_count 平均 | review_count 中位數 | score 中位數
100+ bought in past month | 46 | 8.46% | 362.10 USD | 89.99 USD | 698.48 | 198.00 | 3.50
50+ bought in past month | 34 | 6.25% | 101.56 USD | 57.99 USD | 903.19 | 121.00 | 2.00
200+ bought in past month | 22 | 4.04% | 122.09 USD | 119.98 USD | 1,961.20 | 794.00 | 4.00
500+ bought in past month | 16 | 2.94% | 245.15 USD | 139.99 USD | 2,555.93 | 806.00 | 4.00
400+ bought in past month | 12 | 2.21% | 201.17 USD | 47.99 USD | 1,204.08 | 413.00 | 3.00
1K+ bought in past month | 11 | 2.02% | 68.58 USD | 41.36 USD | 3,215.00 | 776.50 | 2.00
300+ bought in past month | 11 | 2.02% | 500.32 USD | 236.00 USD | 923.00 | 327.00 | 5.00
2K+ bought in past month | 5 | 0.92% | 323.89 USD | 59.97 USD | 2,303.50 | 1,166.00 | 3.00
3K+ bought in past month | 2 | 0.37% | 214.49 USD | 214.49 USD | 1,796.50 | 1,796.50 | 6.00
10K+ bought in past month | 1 | 0.18% | 35.99 USD | 35.99 USD | 33,535.00 | 33,535.00 | 0.00
4K+ bought in past month | 1 | 0.18% | 299.00 USD | 299.00 USD | 3,965.00 | 3,965.00 | 9.00
5K+ bought in past month | 1 | 0.18% | 29.58 USD | 29.58 USD | — | — | 0.00
600+ bought in past month | 1 | 0.18% | 49.98 USD | 49.98 USD | 131.00 | 131.00 | 3.00
6K+ bought in past month | 1 | 0.18% | 49.99 USD | 49.99 USD | 8,639.00 | 8,639.00 | 5.00
8K+ bought in past month | 1 | 0.18% | 64.98 USD | 64.98 USD | 8,830.00 | 8,830.00 | 5.00
合計 | 165 | 30.33% | 227.31 USD | 69.99 USD | 1,747.59 | 328.00 | 3.00
```
### `E_0d77ee19_abffba77dd` — cite with `[CITE:E_0d77ee19_abffba77dd]`.

```
衍生統計(來源:amazon_reviews.csv):本樣本共收錄 473 筆資料列，總筆數 473 筆，欄位 6 個。各欄有值筆數為 review_id 473 筆、asin 473 筆、review_rating 473 筆、review_title 382 筆、review_body 473 筆、review_date 382 筆。
```
### `E_0d77ee19_8eb9aa068f` — cite with `[CITE:E_0d77ee19_8eb9aa068f]`.

```
衍生統計(來源:amazon_reviews.csv):review_rating 欄共 473 筆數值，最小值 1，第一四分位 4，中位數 5，平均數 4.41，第三四分位 5，最大值 5。
```

Registered by request: none yet — see the registration guide below.


## Making a statistic citable

### Asking for a statistic that is not there yet

`register_derived_evidence` computes it from the rows and returns the
`evidence_id` to cite. **One request can return a whole table**: give it
`group_by` and a list of `measures` and it produces one row per group and one
column per measure, registered as a single evidence entry.

```
register_derived_evidence(job_id="<job_id>", derivations=[

  # A grouped table. `buckets` are yours to choose - the tool never guesses
  # where to cut a numeric axis, because where the bands fall is the finding.
  {"id": "price_band_reliability",
   "source": "products.csv",
   "label": "Price band against rating and complaint rate",
   "group_by": {"column": "price", "buckets": [0, 30, 50, 100, 200, 400],
                "label": "Price band"},
   "measures": [{"op": "count",  "label": "Listings"},
                {"op": "share",  "label": "Share of catalogue"},
                {"op": "mean",   "column": "rating", "label": "Mean rating"},
                {"op": "share",  "rows": "rating < 4", "label": "Under 4 stars"}]},

  # Grouping a categorical column needs no buckets.
  {"id": "category_mix", "source": "products.csv",
   "group_by": {"column": "category"},
   "measures": [{"op": "count"}, {"op": "median", "column": "price"}]},

  # Two files, joined on one key. Rows that find no partner are counted and
  # reported in the evidence text - that number is usually worth stating.
  {"id": "band_review_rating",
   "source": ["reviews.csv", "products.csv"],
   "join": {"on": "asin", "how": "inner"},
   "group_by": {"column": "price", "buckets": [0, 30, 50, 100, 200, 400]},
   "measures": [{"op": "count"}, {"op": "mean", "column": "review_rating"}]},

  # A single number, when that is all you need.
  {"id": "hhi_brand", "source": "products.csv", "op": "hhi", "column": "brand"},
])
```

`measures` entries take `op`, `column`, an optional `rows` filter applied
inside each group, and a `label` that becomes the column header. A `share`
with no `rows` filter is the group's share of the whole selection; a `share`
*with* one is that rate inside the group.

Ops: `count`, `sum`, `mean`, `median`, `min`, `max`, `distinct`, `share`,
`hhi`, `top_share` (CR-k, with `k`). Filters: `col=value`, `col!=value`,
`col>=n`, `col~text`, joined with `&`; omit for every row.

Joins: `inner` on a single key; `on` when both files name it the same way,
`left_on`/`right_on` when they do not. A column present in both files is
renamed `<column>__<other_file>` on the right-hand side rather than
overwritten, and the renaming is recorded in the evidence.

The value is computed from the rows - you do not supply it. `expect` is
optional, and is compared against the computed value rather than trusted, so a
statistic you worked out yourself can be registered and checked.

**Register what the argument needs before you start drafting.** Registering
appends to the evidence ledger; artifacts already accepted at an earlier stage
are re-stamped against the new ledger automatically, so this no longer strands
a run - but a claim can only cite an id that already exists, so a figure
discovered mid-draft still costs a round trip. Listing the tables the argument
needs is the cheapest part of this job.

Do not decide in advance that a number cannot be cited. That decision is
invisible in the finished report: nothing is blocked, the sentence is simply
never written, and the reader gets "most" where a figure belonged.


## Evidence Summary
(Full ledger at `D:\report_workflow\.runs\drone_market_report\Amazon US 無人機市場研究報告：品類結構、價格帶、品牌集中度與買家痛點--run_04af045c\evidence_ledger.jsonl`; read individual entries as needed.
This is the first 20 rows only, as a sample of the ledger's
shape. Every derived statistic is listed above in full — they sit at the end of
the ledger and never appear in this window.)
```
Total evidence entries: 1586 (showing first 20)
  evidence_id | source_file | evidence_type | allowed_claim_types | quote_preview
  --------------------------------------------------------------------------------
  E_28767e63_99a45bec33 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0FR42R14S", "title": "Oddire Drones with Camera for Adults 4K, GPS Au
  E_28767e63_80589696ef | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0F8QTBGNP", "title": "Drone with Camera for Adults, 2K HD FPV Drones 
  E_28767e63_e36dbd5c48 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0FD9T2145", "title": "GPS Drone with Camera, 2K HD Drones for Adults,
  E_28767e63_11e6a9ff56 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0H3LW66X7", "title": "GPS Drone with EIS Camera for Adults Beginners,
  E_28767e63_28ff11705d | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0F4WZ3Q2J", "title": "DJI Mini 4K Camera Drone Combo, Drone with 4K U
  E_28767e63_901820bbf0 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0DKHCZHCY", "title": "Potensic ATOM 2 Drone with Camera for Adults 4K
  E_28767e63_5a6fe65560 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0FYPWRFWF", "title": "Drone with Camera, Screen on Controller Remote 
  E_28767e63_9ffed77391 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0CXJDDJ9X", "title": "DJI Mini 4K, Drone With 4K UHD Camera, Under 24
  E_28767e63_0b53219f3a | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0F6XK911R", "title": "DJI Mini 5 Pro Fly More Combo Plus with DJI RC 
  E_28767e63_1e8539d0aa | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0FB3SBPJ7", "title": "Bwine F7GB2 Pro Drones with Camera for Adults 4
  E_28767e63_5b72574c15 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0GS77FXYC", "title": "DJI Mini 5 Pro Drone RC2 Fly More Combo Plus Li
  E_28767e63_be48b4b865 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0FN387TP3", "title": "Dwi Dowellin GPS Drone with Camera for Adults,2
  E_28767e63_89505972f5 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0FBR5JHJ6", "title": "GPS Drone with Camera for Adults, 2K HD Foldabl
  E_28767e63_62d6ab81c5 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0D5CXY6X8", "title": "FLYVISTA Cool Mini Drone with Camera for Kids A
  E_28767e63_7a5bb5de83 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0FJ1QH15P", "title": "DJI Neo 2 Motion Fly More Combo With RC Motion 
  E_28767e63_845c88f126 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0F6XN1J7K", "title": "DJI Mini 5 Pro Fly More Combo With DJI RC 2, 1-
  E_28767e63_0cb3fdb7e9 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B07FVZFFXD", "title": "DJI Air 3S Fly More Combo (RC 2 Screen Remote C
  E_28767e63_d150099e38 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0H25RH4VJ", "title": "MSMV 4K Camera Drone for Adults Kids, Wireless 
  E_28767e63_195630c5b3 | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0FC5RTNX7", "title": "Contixo F23 GPS Drone With Camera, 46 Min Fligh
  E_28767e63_54afc7aaba | amazon_products.csv | quantitative | allowed:[factual, statistical] | {"asin": "B0H25P37NH", "title": "MSMV 4K HD Drone With Camera, Wireless RC Toys 
```
