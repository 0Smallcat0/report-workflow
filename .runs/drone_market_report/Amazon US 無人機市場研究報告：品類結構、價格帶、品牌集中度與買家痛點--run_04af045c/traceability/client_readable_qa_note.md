# 品質查核說明（給閱讀者）

- 品管判定: pass
- 產出完整性: pass

## 每一項主張的依據

以下每一項主張，都必須連結到所提供來源中的材料，才會出現在報告裡。各項所依據的內容引在其下。

### 1. 本次分析涵蓋的 544 筆商品列分屬 8 個品類，其中攝影用整機 243 筆、佔 44.67%，是單一最大品類。

- 狀態: verified (c1)
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):category 分組交叉表。依 category 分為 8 組，涵蓋 544 筆資料列（全檔 544 筆）。 category | 筆數 | 佔比 | price 平均 | price 中位數 | review_count 平均 | review_count 中位數 | score 中位數 攝影 | 243 | 44.67% | 535.95 USD | 139.98 USD | 1,115.95 | 225.0 [...]
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):category 欄共 8 個相異值、544 筆有值資料列。分布為 攝影 243 筆(44.7%)、無人機馬達 77 筆(14.2%)、配件/零件 71 筆(13.1%)、植保 63 筆(11.6%)、非無人機商品 46 筆(8.5%)、消費級/其他 22 筆(4.0%)、多用途 14 筆(2.6%)、消防投彈 8 筆(1.5%)。前五大合計佔 91.9%，以此欄計算的 HHI 為 2597。

### 2. 無人機馬達 77 筆與配件／零件 71 筆合計 148 筆、佔全樣本 27.21%，超過四分之一的搜尋結果並不是可直接販售的整機。

- 狀態: verified (c2)
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):category 分組交叉表。依 category 分為 8 組，涵蓋 544 筆資料列（全檔 544 筆）。 category | 筆數 | 佔比 | price 平均 | price 中位數 | review_count 平均 | review_count 中位數 | score 中位數 攝影 | 243 | 44.67% | 535.95 USD | 139.98 USD | 1,115.95 | 225.0 [...]
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):零組件（無人機馬達與配件／零件）合計佔比為 27.21%。計算方式:對 category!=攝影 & category!=植保 & category!=非無人機商品 & category!=消費級/其他 & category!=多用途 & category!=消防投彈 共 148 筆（全檔 544 筆）施以 share 運算。（148 of 544）

### 3. 分類結果中有 46 筆、佔 8.46% 被判定為非無人機商品，代表關鍵字搜尋本身就帶進可觀的雜訊。

- 狀態: verified (c3)
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):搜尋結果中非無人機商品佔比為 8.46%。計算方式:對 category=非無人機商品 共 46 筆（全檔 544 筆）施以 share 運算。（46 of 544）
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):category 分組交叉表。依 category 分為 8 組，涵蓋 544 筆資料列（全檔 544 筆）。 category | 筆數 | 佔比 | price 平均 | price 中位數 | review_count 平均 | review_count 中位數 | score 中位數 攝影 | 243 | 44.67% | 535.95 USD | 139.98 USD | 1,115.95 | 225.0 [...]

### 4. 植保類雖有 63 筆商品列、佔 11.58%，卻有 88.89% 完全沒有累積任何評論數，該類評論數中位數僅 1。

- 狀態: verified (c4)
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):植保類完全沒有評論數的商品列比重為 88.89%。計算方式:對 category=植保 & review_count= 共 56 筆（全檔 544 筆）施以 share 運算。（56 of 63）
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):category 分組交叉表。依 category 分為 8 組，涵蓋 544 筆資料列（全檔 544 筆）。 category | 筆數 | 佔比 | price 平均 | price 中位數 | review_count 平均 | review_count 中位數 | score 中位數 攝影 | 243 | 44.67% | 535.95 USD | 139.98 USD | 1,115.95 | 225.0 [...]

### 5. 以 agricultural spray drone 關鍵字取得的 111 筆商品列平均星等 3.77，是四組關鍵字中最低，評論數中位數僅 11.5；相對地 drone 關鍵字的 279 筆平均 4.27、評論數中位數 197。

- 狀態: verified (c5)
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):keyword 分組交叉表。依 keyword 分為 4 組，涵蓋 544 筆資料列（全檔 544 筆）。 keyword | 筆數 | 佔比 | price 平均 | price 中位數 | rating 平均 | rating 中位數 | review_count 中位數 drone | 279 | 51.29% | 1,085.70 USD | 99.97 USD | 4.27 | 4.30 | 197.00 a [...]

### 6. 品類分布的 HHI 為 2597、前五大品類合計佔 91.9%，顯示這個搜尋面高度集中於少數幾種商品型態。

- 狀態: verified (c6)
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):category 欄共 8 個相異值、544 筆有值資料列。分布為 攝影 243 筆(44.7%)、無人機馬達 77 筆(14.2%)、配件/零件 71 筆(13.1%)、植保 63 筆(11.6%)、非無人機商品 46 筆(8.5%)、消費級/其他 22 筆(4.0%)、多用途 14 筆(2.6%)、消防投彈 8 筆(1.5%)。前五大合計佔 91.9%，以此欄計算的 HHI 為 2597。

### 7. 多用途類僅 14 筆商品列，價格中位數卻高達 3,579 美元，評論數中位數只有 5。

- 狀態: verified (c7)
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):category 分組交叉表。依 category 分為 8 組，涵蓋 544 筆資料列（全檔 544 筆）。 category | 筆數 | 佔比 | price 平均 | price 中位數 | review_count 平均 | review_count 中位數 | score 中位數 攝影 | 243 | 44.67% | 535.95 USD | 139.98 USD | 1,115.95 | 225.0 [...]

### 8. 425 筆有標價商品列的價格中位數為 71.99 美元，平均數卻達 735.50 美元，第三四分位 269.99 美元、最高值 36,999 美元，分布極度右偏。

- 狀態: verified (c8)
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):price 欄共 425 筆數值，最小值 0 USD，第一四分位 32.99 USD，中位數 71.99 USD，平均數 735.50 USD，第三四分位 269.99 USD，最大值 36,999 USD。

### 9. 全部 544 筆商品列當中有 119 筆、佔 21.88% 在資料擷取當下未顯示價格。

- 狀態: verified (c9)
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):未顯示價格的商品列佔比為 21.88%。計算方式:對 price= 共 119 筆（全檔 544 筆）施以 share 運算。（119 of 544）

### 10. 0 至 50 美元帶集中了 179 筆商品列、佔全樣本 32.90%，是貨架上最擁擠的一段。

- 狀態: verified (c10)
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):價格帶結構與評價表現。依 price 分為 6 組，涵蓋 425 筆資料列（全檔 544 筆）。另有 119 筆在該欄無可用值，未列入分組。 價格帶 (USD) | 商品數 | 佔全樣本 | 平均星等 | 低於 4 星比率 | 評論數中位數 0–50 | 179 | 32.90% | 4.21 | 16.76% | 46.00 50–100 | 63 | 11.58% | 4.37 | 14.29% | 22.00 1 [...]

### 11. 100 至 200 美元帶的 64 筆商品列中有 25.00% 星等低於 4，是所有價格帶中比例最高的一段，平均星等 4.16 也是最低。

- 狀態: verified (c11)
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):價格帶結構與評價表現。依 price 分為 6 組，涵蓋 425 筆資料列（全檔 544 筆）。另有 119 筆在該欄無可用值，未列入分組。 價格帶 (USD) | 商品數 | 佔全樣本 | 平均星等 | 低於 4 星比率 | 評論數中位數 0–50 | 179 | 32.90% | 4.21 | 16.76% | 46.00 50–100 | 63 | 11.58% | 4.37 | 14.29% | 22.00 1 [...]

### 12. 1,500 美元以上共有 44 筆商品列，但在評論資料中這一帶沒有任何一則對應評論。

- 狀態: verified (c12)
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):售價 1500 美元以上的商品列數為 44。計算方式:對 price>=1500 共 44 筆（全檔 544 筆）施以 count 運算。
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv ⋈ amazon_products.csv):各價格帶的實際買家評分。依 price 分為 6 組，涵蓋 373 筆資料列（全檔 473 筆）。另有 100 筆在該欄無可用值，未列入分組。本表由 amazon_reviews.csv 與 amazon_products.csv 以 asin 內接而成，接得 473 筆；amazon_reviews.csv 有 0 筆、amazon_products.csv 有 481 筆接 [...]

### 13. 攝影類中，0 至 50 美元帶的評論數中位數為 433、200 至 500 美元帶為 387，夾在中間的 100 至 200 美元帶卻只有 74。

- 狀態: verified (c13)
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):攝影類無人機的價格帶貨架結構。依 price 分為 6 組，涵蓋 179 筆資料列（全檔 544 筆）。另有 64 筆在該欄無可用值，未列入分組。 價格帶 (USD) | 商品數 | 佔攝影類 | 評論數中位數 | 有近月銷量標示 0–50 | 49 | 20.16% | 433.00 | 31 50–100 | 27 | 11.11% | 167.00 | 14 100–200 | 39 | 16.05% | 7 [...]

### 14. 攝影類 179 筆有標價商品列中，有近月銷量標示的共 101 筆，其中 100 至 200 美元帶有 23 筆、200 至 500 美元帶有 21 筆。

- 狀態: verified (c14)
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):攝影類無人機的價格帶貨架結構。依 price 分為 6 組，涵蓋 179 筆資料列（全檔 544 筆）。另有 64 筆在該欄無可用值，未列入分組。 價格帶 (USD) | 商品數 | 佔攝影類 | 評論數中位數 | 有近月銷量標示 0–50 | 49 | 20.16% | 433.00 | 31 50–100 | 27 | 11.11% | 167.00 | 14 100–200 | 39 | 16.05% | 7 [...]

### 15. 207 筆有標示品牌的商品列共來自 54 個品牌，其中 DJI 單一品牌就佔 92 筆、44.4%。

- 狀態: verified (c15)
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):brand 欄共 54 個相異值、207 筆有值資料列。分布為 DJI 92 筆(44.4%)、Holy Stone 10 筆(4.8%)、Contixo 9 筆(4.3%)、Potensic 9 筆(4.3%)、BetaFPV 8 筆(3.9%)、Antigravity 6 筆(2.9%)、Autel 6 筆(2.9%)、Cozyego 4 筆(1.9%)、Ruko 4 筆(1.9%)、MAD COMPONENTS [...]

### 16. 品牌前五大集中度 CR5 為 61.84%，以品牌欄計算的 HHI 為 2097。

- 狀態: verified (c16)
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):品牌前五大集中度 CR5為 61.84%。計算方式:對 全部資料列 共 544 筆（全檔 544 筆）的 brand 欄施以 top_share 運算。（top DJI, Holy Stone, Contixo, Potensic, BetaFPV）
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):brand 欄共 54 個相異值、207 筆有值資料列。分布為 DJI 92 筆(44.4%)、Holy Stone 10 筆(4.8%)、Contixo 9 筆(4.3%)、Potensic 9 筆(4.3%)、BetaFPV 8 筆(3.9%)、Antigravity 6 筆(2.9%)、Autel 6 筆(2.9%)、Cozyego 4 筆(1.9%)、Ruko 4 筆(1.9%)、MAD COMPONENTS [...]

### 17. 544 筆商品列中有 337 筆、佔 61.95% 完全沒有標示品牌。

- 狀態: verified (c17)
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):未標示品牌的商品列佔比為 61.95%。計算方式:對 brand= 共 337 筆（全檔 544 筆）施以 share 運算。（337 of 544）

### 18. 攝影類中僅 53.50% 的商品列標示品牌，DJI 佔全攝影類的 24.28%，該類以品牌欄計算的 HHI 為 2,259。

- 狀態: verified (c18)
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):攝影類中有標示品牌的商品列比重為 53.50%。計算方式:對 category=攝影 & brand!= 共 130 筆（全檔 544 筆）施以 share 運算。（130 of 243）
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):DJI 佔攝影類商品列比重為 24.28%。計算方式:對 category=攝影 & brand=DJI 共 59 筆（全檔 544 筆）施以 share 運算。（59 of 243）
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):攝影類品牌 HHI為 2,259.17。計算方式:對 category=攝影 共 243 筆（全檔 544 筆）的 brand 欄施以 hhi 運算。（28 groups over 130 rows）

### 19. DJI 商品列的價格中位數為 247.50 美元，其中只有 25% 售價低於 200 美元。

- 狀態: verified (c19)
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):DJI 商品列價格中位數為 247.50 USD。計算方式:對 brand=DJI 共 92 筆（全檔 544 筆）的 price 欄施以 median 運算。（48 of 92 selected rows carry a number）
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):DJI 商品列中售價低於 200 美元的比重為 25%。計算方式:對 brand=DJI & price<200 共 23 筆（全檔 544 筆）施以 share 運算。（23 of 92）

### 20. DJI 的 92 筆商品列平均星等 4.39、評論數中位數 307，兩項都高於全體有品牌商品列的 4.29 與 140。

- 狀態: verified (c20)
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):brand 分組交叉表。依 brand 分為 16 組，涵蓋 207 筆資料列（全檔 544 筆）。另有 337 筆在該欄無可用值，未列入分組。 brand | 筆數 | 佔比 | price 平均 | price 中位數 | rating 平均 | rating 中位數 | review_count 中位數 DJI | 92 | 16.91% | 1,077.30 USD | 247.50 USD | 4.39 | [...]

### 21. 100 至 200 美元帶的 64 筆商品列中有 40 筆沒有標示品牌；其餘 24 筆平均 4.13 星，其中商品數較多的 Contixo 為 3.58 星、CADDXFPV 為 3.15 星。

- 狀態: verified (c21)
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):100–200 美元價格帶的品牌與評價。依 brand 分為 7 組，涵蓋 24 筆資料列（全檔 544 筆）。另有 40 筆在該欄無可用值，未列入分組。 品牌 | 商品數 | 平均星等 | 價格中位數 | 評論數中位數 BetaFPV | 5 | 4.42 | 115.99 USD | 7.50 Contixo | 4 | 3.58 | 154.99 USD | 33.50 DJI | 3 | 4.80 | 119. [...]
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):價格帶結構與評價表現。依 price 分為 6 組，涵蓋 425 筆資料列（全檔 544 筆）。另有 119 筆在該欄無可用值，未列入分組。 價格帶 (USD) | 商品數 | 佔全樣本 | 平均星等 | 低於 4 星比率 | 評論數中位數 0–50 | 179 | 32.90% | 4.21 | 16.76% | 46.00 50–100 | 63 | 11.58% | 4.37 | 14.29% | 22.00 1 [...]

### 22. 評論資料共 473 則、平均 4.41 分，但只涵蓋 63 個相異商品。

- 狀態: verified (c22)
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv):本樣本共收錄 473 筆資料列，總筆數 473 筆，欄位 6 個。各欄有值筆數為 review_id 473 筆、asin 473 筆、review_rating 473 筆、review_title 382 筆、review_body 473 筆、review_date 382 筆。
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv):review_rating 欄共 473 筆數值，最小值 1，第一四分位 4，中位數 5，平均數 4.41，第三四分位 5，最大值 5。
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv):評論資料涵蓋的相異商品數為 63。計算方式:對 全部資料列 共 473 筆（全檔 473 筆）的 asin 欄施以 distinct 運算。

### 23. 1 星評論中有 27.03% 提及連線或配對問題，5 星評論則為 14.04%，差距接近一倍。

- 狀態: verified (c23)
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv):各星等評論提及的問題主題比率。依 review_rating 分為 5 組，涵蓋 473 筆資料列（全檔 473 筆）。 評分區間（星） | 評論則數 | 提及連線配對 | 提及墜機 | 提及零件損壞 | 提及退貨 | 提及電池續航 1–2 | 37 | 27.03% | 18.92% | 10.81% | 21.62% | 29.73% 2–3 | 12 | 33.33% | 8.33% | 8.33% | 8.33% [...]

### 24. 提及電池與續航的比率在 5 星評論高達 43.55%，在 1 星評論反而降到 29.73%，方向與其他問題主題完全相反。

- 狀態: verified (c24)
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv):各星等評論提及的問題主題比率。依 review_rating 分為 5 組，涵蓋 473 筆資料列（全檔 473 筆）。 評分區間（星） | 評論則數 | 提及連線配對 | 提及墜機 | 提及零件損壞 | 提及退貨 | 提及電池續航 1–2 | 37 | 27.03% | 18.92% | 10.81% | 21.62% | 29.73% 2–3 | 12 | 33.33% | 8.33% | 8.33% | 8.33% [...]

### 25. 1 星評論提及零件損壞的比率為 10.81%、提及退貨為 21.62%、提及墜機為 18.92%，分別是 5 星評論 3.44%、11.17%、8.60% 的兩倍上下。

- 狀態: verified (c25)
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv):各星等評論提及的問題主題比率。依 review_rating 分為 5 組，涵蓋 473 筆資料列（全檔 473 筆）。 評分區間（星） | 評論則數 | 提及連線配對 | 提及墜機 | 提及零件損壞 | 提及退貨 | 提及電池續航 1–2 | 37 | 27.03% | 18.92% | 10.81% | 21.62% | 29.73% 2–3 | 12 | 33.33% | 8.33% | 8.33% | 8.33% [...]

### 26. 100 至 200 美元帶的買家平均評分 4.09、1 至 2 星佔 18.18%，是所有價格帶中最差的一段；200 至 500 美元帶則是 4.66 與 4.90%。

- 狀態: verified (c26)
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv ⋈ amazon_products.csv):各價格帶的實際買家評分。依 price 分為 6 組，涵蓋 373 筆資料列（全檔 473 筆）。另有 100 筆在該欄無可用值，未列入分組。本表由 amazon_reviews.csv 與 amazon_products.csv 以 asin 內接而成，接得 473 筆；amazon_reviews.csv 有 0 筆、amazon_products.csv 有 481 筆接 [...]

### 27. 攝影類 405 則評論平均 4.46 分、1 至 2 星佔 9.38%；消防投彈與消費級／其他兩類分別只有 3.58 與 3.12 分，但樣本僅 12 則與 8 則。

- 狀態: verified (c27)
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv ⋈ amazon_classified.csv):各品類的實際買家評分。依 category 分為 5 組，涵蓋 473 筆資料列（全檔 473 筆）。本表由 amazon_reviews.csv 與 amazon_classified.csv 以 asin 內接而成，接得 473 筆；amazon_reviews.csv 有 0 筆、amazon_classified.csv 有 481 筆接不上。 品類 | 評論則數 [...]

### 28. 有買家指出商品標稱的最大飛行距離遠高於實際表現，機體在遠低於標稱距離處就失去連線，隨後失去影像並墜毀。

- 狀態: verified (c28)
- 出自 `amazon_reviews.csv` (high): {"review_id": "RTT5AD0VU5K90", "asin": "B0C5T7SZQZ", "review_rating": "1.0", "review_title": "Lost connection completly after 100 feet (says it can reach 3,200 feet)", "review_body": "Calibrated multiple times still was not stable, says can [...]

### 29. 有買家表示開箱後花超過一小時仍無法讓遙控器與機體穩定配對，遙控器持續發出提示音卻始終無法取得控制權。

- 狀態: verified (c29)
- 出自 `amazon_reviews.csv` (high): {"review_id": "R1KAJFO1FRJMFJ", "asin": "B0CWKWBZJT", "review_rating": "1.0", "review_title": "Didn't work out of the box", "review_body": "This was a complete waste of time. I was never able to reliably pair the drone with the controller, [...]

### 30. 有買家在第三次飛行按下返航鍵後，機體反而向後飛離視線且未再返回。

- 狀態: verified (c30)
- 出自 `amazon_reviews.csv` (high): {"review_id": "R3U1POWSMN3MDI", "asin": "B0FC5RTNX7", "review_rating": "2.0", "review_title": "Disappointed in purchase!", "review_body": "The drone flew 3 times total. The drone worked fine the first two flights. The second flight was in t [...]

### 31. 有買家在第二次飛行時失去遙控回應、撞入樹叢並折斷機臂，並直言這不是該價位應有的表現。

- 狀態: verified (c31)
- 出自 `amazon_reviews.csv` (high): {"review_id": "R3B5JFYL8GLEQ", "asin": "B0F6Y9PB64", "review_rating": "1.0", "review_title": "Junk", "review_body": "Seemed good on the first flight. Second flight it took off into the trees with no response from remote commands. It crashed [...]

### 32. 有買家反映機體飛行本身沒有問題，卻因手機應用程式無法連線而使相機功能完全無法使用。

- 狀態: verified (c32)
- 出自 `amazon_reviews.csv` (high): {"review_id": "RS8H031JBUX4E", "asin": "B0C5T9GZQY", "review_rating": "1.0", "review_title": "Hard pass", "review_body": "Flies great, fun to use but couldn’t get app on iPhone to connect to drone making the camera function unusable.\nPoor [...]

### 33. 有買家因應用程式在其所在地區無法下載，導致整台機體無法使用。

- 狀態: verified (c33)
- 出自 `amazon_reviews.csv` (high): {"review_id": "RU2LAUMYO88PG", "asin": "B0GC5NFDHR", "review_rating": "1.0", "review_title": "App not downloadable", "review_body": "The app is not available in my region. Would have been nice to know before I bought it. Now I just have a p [...]

### 34. 25.79% 的評論提及 beginner、7.61% 提及 easy to fly，顯示留下評論的主力是入門買家。

- 狀態: verified (c34)
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv):評論內文提及 beginner（新手）的比率為 25.79%。計算方式:對 review_body~beginner 共 122 筆（全檔 473 筆）施以 share 運算。（122 of 473）
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv):評論內文提及 easy to fly（好上手）的比率為 7.61%。計算方式:對 review_body~easy to fly 共 36 筆（全檔 473 筆）施以 share 運算。（36 of 473）

### 35. 以商品編號內接時，473 則評論全部找得到對應商品，但有 481 筆商品列沒有任何評論可對接。

- 狀態: verified (c35)
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv ⋈ amazon_products.csv):各價格帶的實際買家評分。依 price 分為 6 組，涵蓋 373 筆資料列（全檔 473 筆）。另有 100 筆在該欄無可用值，未列入分組。本表由 amazon_reviews.csv 與 amazon_products.csv 以 asin 內接而成，接得 473 筆；amazon_reviews.csv 有 0 筆、amazon_products.csv 有 481 筆接 [...]

### 36. 銷量欄位僅 165 筆商品列有值，且以「100+ bought in past month」這類分級字串記錄，無法還原成實際銷售數量。

- 狀態: verified (c36)
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):sales 欄共 15 個相異值、165 筆有值資料列。分布為 100+ bought in past month 46 筆(27.9%)、50+ bought in past month 34 筆(20.6%)、200+ bought in past month 22 筆(13.3%)、500+ bought in past month 16 筆(9.7%)、400+ bought in past month 12 [...]

### 37. 價格帶分析只涵蓋 425 筆有標價的商品列，另有 119 筆未列入分組；買家評分的價格帶分析中，另有 100 則評論因對應商品未標價而未列入。

- 狀態: verified (c37)
- 出自 `amazon_products.csv` (high): 衍生統計(來源:amazon_products.csv):價格帶結構與評價表現。依 price 分為 6 組，涵蓋 425 筆資料列（全檔 544 筆）。另有 119 筆在該欄無可用值，未列入分組。 價格帶 (USD) | 商品數 | 佔全樣本 | 平均星等 | 低於 4 星比率 | 評論數中位數 0–50 | 179 | 32.90% | 4.21 | 16.76% | 46.00 50–100 | 63 | 11.58% | 4.37 | 14.29% | 22.00 1 [...]
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv ⋈ amazon_products.csv):各價格帶的實際買家評分。依 price 分為 6 組，涵蓋 373 筆資料列（全檔 473 筆）。另有 100 筆在該欄無可用值，未列入分組。本表由 amazon_reviews.csv 與 amazon_products.csv 以 asin 內接而成，接得 473 筆；amazon_reviews.csv 有 0 筆、amazon_products.csv 有 481 筆接 [...]

### 38. 100 至 200 美元帶的買家評分結論只由 11 個商品、77 則評論支撐。

- 狀態: verified (c38)
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv ⋈ amazon_products.csv):各價格帶的實際買家評分。依 price 分為 6 組，涵蓋 373 筆資料列（全檔 473 筆）。另有 100 筆在該欄無可用值，未列入分組。本表由 amazon_reviews.csv 與 amazon_products.csv 以 asin 內接而成，接得 473 筆；amazon_reviews.csv 有 0 筆、amazon_products.csv 有 481 筆接 [...]

### 39. 攝影類是唯一同時具備規模（243 筆商品列）與買家實證（405 則評論、涵蓋 51 個商品）的整機品類。

- 狀態: verified (c39)
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):category 分組交叉表。依 category 分為 8 組，涵蓋 544 筆資料列（全檔 544 筆）。 category | 筆數 | 佔比 | price 平均 | price 中位數 | review_count 平均 | review_count 中位數 | score 中位數 攝影 | 243 | 44.67% | 535.95 USD | 139.98 USD | 1,115.95 | 225.0 [...]
- 出自 `amazon_reviews.csv` (high): 衍生統計(來源:amazon_reviews.csv ⋈ amazon_classified.csv):各品類的實際買家評分。依 category 分為 5 組，涵蓋 473 筆資料列（全檔 473 筆）。本表由 amazon_reviews.csv 與 amazon_classified.csv 以 asin 內接而成，接得 473 筆；amazon_reviews.csv 有 0 筆、amazon_classified.csv 有 481 筆接不上。 品類 | 評論則數 [...]

### 40. 攝影類售價落在 100 至 200 美元的商品列共 39 筆，佔該類 16.05%。

- 狀態: verified (c40)
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):攝影類售價 100–200 美元的商品列數為 39。計算方式:對 category=攝影 & price>=100 & price<200 共 39 筆（全檔 544 筆）施以 count 運算。
- 出自 `amazon_classified.csv` (high): 衍生統計(來源:amazon_classified.csv):攝影類無人機的價格帶貨架結構。依 price 分為 6 組，涵蓋 179 筆資料列（全檔 544 筆）。另有 64 筆在該欄無可用值，未列入分組。 價格帶 (USD) | 商品數 | 佔攝影類 | 評論數中位數 | 有近月銷量標示 0–50 | 49 | 20.16% | 433.00 | 31 50–100 | 27 | 11.11% | 167.00 | 14 100–200 | 39 | 16.05% | 7 [...]

## 本包內容

報告本身、建立報告所用的來源材料、證據帳本、機器可讀的主張稽核檔，以及品管摘要。
