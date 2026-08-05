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

這個極限我們是量出來的，不是繞過去：69 個人工設計、想騙過它的假句子，加上一萬組別人寫的公開測試資料。**它到現在還抓不到的那些，我們故意留在測試裡** — [docs/EVIDENCE.md](docs/EVIDENCE.md)。

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

規格是我寫的、東西是我接起來的、結果是我驗的；程式大部分是 coding agent 寫的。這些檢查跟測試存在的理由，就是讓「這到底對不對」由人決定，不是由模型決定。
