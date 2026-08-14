# Report Workflow

**English → [README.md](README.md)**

**把你已經有的檔案丟給 AI，再講一句你要什麼。拿回一份可以直接交出去的 Word 檔。**

如果 AI 寫了一個你檔案裡沒有的數字，那個數字不會出現在文件裡。它自己改過的引文、它掰出來的參考文獻，一樣進不去。會被擋下來，而且告訴你是哪一句、為什麼。

**你要準備**：一份量測數據的試算表、老師給的 Word 講義、一頁筆記——你手上有什麼就給什麼。再加一句話，例如「幫我寫成實驗報告」。

**你會拿到**：一份 `.docx`，有目錄、頁碼、真的 Word 表格、用你自己的數字畫的圖。可以照你系上或公司的範本排。中文英文都行。

安裝兩行。不用 API key。沒有東西要設定。

## 先看它做出來的東西

下面兩個檔案就在這個 repo 裡，你什麼都不用裝就能點開看：

- **[`examples/output/report.docx`](examples/output/report.docx)** — 就是交出去的那份：目錄、頁碼、真的 Word 表格、用來源試算表畫的圖
- **[`examples/output/client_readable_qa_note.md`](examples/output/client_readable_qa_note.md)** — 文件裡每一句講到事實的話，各自對應到你資料的哪一列
- **[`examples/README.md`](examples/README.md)** — 同一次執行從頭到尾：三個輸入檔、一行指令、交付的文件與它的 QA 產物

![三頁做好的 Word 報告：標題與摘要頁、目錄頁，以及一頁用來源資料畫的折線圖。](docs/sample_report.png)

## 怎麼用

在 Claude Code 裡：

```text
/plugin marketplace add 0Smallcat0/report-workflow
```

然後 `/plugin install report-workflow@report-workflow`。用別的（Codex、Cursor、你自己接的）就一行：

```bash
claude mcp add report-workflow -- uvx --from "report-workflow[mcp,render]" report-workflow-mcp
```

接著用你自己的話講就好：

> 用 report-workflow 把 ./data 裡的檔案寫成一份給主管的成果報告：做了什麼、花多少錢、值不值得推行。

七種文件：實驗報告、期刊論文、商業報告、研究計畫書、兩種備審資料、一種通用的。**老師會看的那些計算——你的量測跟理論差多少、R²、預算總額——是工具自己從你的資料算出來的**，所以 AI 不用去掰一個數字。各種格式、中文文件、自帶範本怎麼用，都在 **[docs/OUTPUT.md](docs/OUTPUT.md)**。

## 它做不到的事

**它看不懂意思。** 它只查文字裡的數字、引文、參考文獻是不是真的在你檔案裡。它沒辦法判斷 AI 有沒有理解你的資料。**如果 AI 用很順的一句話把你的結果講反了，那句會過。**

這個極限我們是量出來的，不是繞過去：73 個人工設計、想騙過它的假句子，加上一萬組別人寫的公開測試資料。**它到現在還抓不到的那些，我們故意留在測試裡** — [docs/EVIDENCE.md](docs/EVIDENCE.md)。

## 它比人手寫好嗎？比 AI 直接生成好嗎？

第一份 benchmark 是兩臂的，你自己就能重跑：

```bash
python scripts/run_report_quality_benchmark.py --check
```

同一份來源、同一句提示，工具產的對上沒有工具的手寫版，同一套計分器，兩臂都在這個 repo 裡。工具贏 8 個維度裡的 6 個，**輸掉的 2 個照實報告、沒有調掉** —— 其中一個是因為那個指標本身獎勵講得含糊，那是關於指標的事實。看[摘要](benchmarks/evidence/report_quality_2026-08-06/summary.md)。

回答「比人手寫好嗎、比 AI 直接生成好嗎」的是另一份，三臂的，而且難看得多：

```bash
python scripts/run_drone_market_benchmark.py --check
```

三份 CSV、一個市場問題。三份錄好的文件 —— 人手寫的控制組、本管線交付的那份、以及一個 AI 拿到同樣檔案直接寫出來的四份草稿裡最強的一份。三個軸：計數的（numeric）、規則計分的（layout）、以及由三位獨立盲評依固定 rubric 評分的（argument），評審不知道任何一臂是怎麼產生的。以下每一個數字都來自 [`benchmarks/evidence/drone_market_2026-08-14/`](benchmarks/evidence/drone_market_2026-08-14/summary.md)。**看清楚日期**：下一次重錄就會變動，而這一輪之後又加了兩個 checker，會改變 tool arm 的內容。

**看表格之前先看這一段。** 停止條件達成 —— tool arm 對 AI 直接生成的那一臂三軸全勝，對人手寫最多輸一軸 —— **而決定它的是一份沒有動過的文件裡的一個數字。** AI-direct 那一臂是凍結的，逐位元組與上一輪相同，上一輪 argument 軸拿 4/4/4，這一輪這組評審給 4/3/3。如果這組評審再給一次 4/4/4，tool arm 在該軸就是 0–1、該軸沒贏、停止條件不成立。AI-direct 掉的那兩分是應得的 —— 三位評審各自查出它頭條數字算錯，以及它最強那條反證的母體被污染 —— 但同樣的缺陷上一輪就存在，上一輪的評審沒有抓到。**所以評審團之間的變異至少是每個維度一分，而這一輪的勝出邊際就是一分。**

**這些分數是這一題的上界，不是通用結果。** tool arm 是唯一會動的臂，而這一輪它是**第二次**針對同一份題目、同樣三份 CSV、同一套 rubric 被撰寫，撰寫者手上還拿著上一輪三位盲評的逐項扣分。在這種條件下分數上升幾乎是必然的，而這一輪的設計分不開「管線變好」與「同一題重考一次」各占多少。

**這份歸檔沒有 held-out 題目** —— 沒有第二個題目、沒有新的來源、沒有「不能照著改的評審意見」。要做一份出來，得再委製一份人手寫控制組和一份 AI 直接生成的臂，那是這個 benchmark 昂貴的那一半。這是這組數字最大的已知限制。

| 軸 | 對人手寫控制組 | 對 AI 直接生成 |
| --- | --- | --- |
| numeric — 文件的可計數性質 | 4–2 won | 4–2 won |
| layout — 規則計分的結構與表格周邊 | 5–1 won | 4–2 won |
| argument — 三位盲評依固定 rubric | **0–1 lost** | 2–1 won |

argument 軸，每個維度取三票中位數（`claim_strength`／`evidence_depth`／`counter_specificity`）：人手寫 **4/4/4**、工具 **3/4/4**、AI 直接生成 **4/3/3**。tool arm 在 `claim_strength` 上仍然輸給人，而三位評審在它身上找到的那個缺陷也記在歸檔裡。每一票、票所依據的段落、以及是誰投的，都在 [`argument_votes.json`](benchmarks/evidence/drone_market_2026-08-14/argument_votes.json)。

layout 軸是在同一輪裡擴充的，擴充的人就是被量的那一臂的作者，而且是在讀過三份文件之後選的維度 —— 新加的三個裡有兩個是渲染器 by construction 就會做、兩份手寫臂完全不做的性質。這件事寫在[摘要](benchmarks/evidence/drone_market_2026-08-14/summary.md)裡，而它是「這一軸要打折」的理由，不是一個註腳。

**它不會自己寫字。** 寫的是你的 AI，它只決定哪句話留得下來。所以你需要一個 AI agent 才能用。

## 誰用了划算

- **每學期交實驗報告、每週交工作報告的人** — 排版跟核對數字每次都要重來一遍，裝一次就攤掉了
- **交出去要負責的人**（法遵、財務、會被打分數的資料）— 那份「每句話出自哪一列資料」的紀錄，別的工具給不了
- **只交一次報告的人** — 老實說不划算，你自己排版比較快

## 想再看細一點

- 產出長什麼樣、有哪些格式、範本怎麼套 → [docs/OUTPUT.md](docs/OUTPUT.md)
- 它抓得到什麼、抓不到什麼 → [docs/EVIDENCE.md](docs/EVIDENCE.md)
- 為什麼這樣設計 → [docs/DESIGN.md](docs/DESIGN.md)
- MCP 工具有哪些 → [docs/mcp.md](docs/mcp.md)
- 回報問題 → [CONTRIBUTING.md](CONTRIBUTING.md)
