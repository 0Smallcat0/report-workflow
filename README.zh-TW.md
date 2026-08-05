# Report Workflow

**English → [README.md](README.md)**

**把你手上的資料交給 AI，拿回一份可以直接交出去的 Word 檔——而且任何一句話，只要在你的資料裡找不到根據，它就不會被寫進去。**

**你要準備的**：你已經有的檔案——量測 CSV、老師給的 Word 講義、一頁筆記——加上一句話說你要寫什麼。

**你會拿到的**：一份 `.docx`，有目錄、頁碼、真的 Word 表格、依你的數字畫的圖，可以套你系上或公司的範本。中英文都行。

安裝兩行、零設定、不用 API key。寫字的是你的 AI，這個工具負責決定哪句話可以留下。

## 先看成品，再決定要不要裝

下面兩個檔案就在這個 repo 裡，不用安裝任何東西就能看：

- **[`examples/output/report.docx`](examples/output/report.docx)** — 交出去的那份文件：目錄、頁碼、原生 Word 表格、依來源 CSV 畫的圖
- **[`examples/output/client_readable_qa_note.md`](examples/output/client_readable_qa_note.md)** — 文件裡每一句主張、它的判定結果、以及它靠的是哪一列資料

![三頁管線渲染出的 DOCX 報告：標題與摘要頁、目錄頁，以及一頁含有依來源資料繪製的折線圖與自足圖說。](docs/sample_report.png)

## 怎麼用

在 Claude Code 裡：

```text
/plugin marketplace add 0Smallcat0/report-workflow
```

接著 `/plugin install report-workflow@report-workflow`。其他吃 MCP 的 agent（Codex、Cursor、你自己的工具）用一行：

```bash
claude mcp add report-workflow -- uvx --from "report-workflow[mcp,render]" report-workflow-mcp
```

然後用你自己的話講就好：

> 用 report-workflow 把 ./data 裡的檔案寫成一份給營運主管的成果報告：做了什麼、成效如何、值不值得推行。

七種文件格式：實驗報告、期刊論文、商業報告、研究計畫書、兩種備審資料、一種通用格式。**老師會看的量化分析**（實測斜率對理論值、R²、預算總額）由工具直接從你的資料算出來並登記成可引用的證據——所以 AI 不必自己編一個數字出來。格式、中文文件、自帶範本的說明在 **[docs/OUTPUT.md](docs/OUTPUT.md)**。

## 它不會做什麼

**它讀不懂意思。** 它抓得到編造的數字、不存在的引用、被竄改的引文、被換掉的單位；但如果 AI 用很通順的句子把你的來源講反，它會過。

這條界線是量出來的，不是嘴上講的——69 個人工審查過的紅隊案例、一萬筆外部 HaluEval 資料，**抓不到的案例故意留在語料庫裡**，數字都寫在 **[docs/EVIDENCE.md](docs/EVIDENCE.md)**。

**它也不會自己寫字。** 寫的是你的 AI；這個工具只決定哪句話可以留下。所以你需要一個 agent（Claude Code、Codex 之類）才能用它。

## 誰用了會划算

- **每學期要交實驗報告、每週要交工作報告的人** — 排版和對數字是每次都痛的事，設定成本攤得掉
- **交出去要負責的人**（法遵文件、財務備忘、被評分的資料）— 那份逐句稽核紀錄別的工具給不了
- **只交一次報告的人** — 老實說不划算，你自己排版比較快

## 想再深入

- 產出長什麼樣、有哪些格式、怎麼套範本 → [docs/OUTPUT.md](docs/OUTPUT.md)
- 實測攔截率與誠實的極限 → [docs/EVIDENCE.md](docs/EVIDENCE.md)
- 為什麼這樣設計、威脅模型 → [docs/DESIGN.md](docs/DESIGN.md)
- MCP 工具與參數 → [docs/mcp.md](docs/mcp.md)
- 回報問題與範圍 → [CONTRIBUTING.md](CONTRIBUTING.md)

規格、整合與驗證由作者本人負責，實作大部分交給 coding agent——這些確定性的關卡與 benchmark 存在的理由，就是讓「這對不對」的最終判斷握在人手上，而不是模型。
