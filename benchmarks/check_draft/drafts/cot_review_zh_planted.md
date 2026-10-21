# 思維鏈提示讀書報告

## 方法

Wei 等人（2022）提出思維鏈提示（chain-of-thought prompting），在提示裡放入幾個附有中間推理步驟的示範，讓大型語言模型先寫出推理過程再作答。只用八個思維鏈示範，PaLM 540B 就在 GSM8K 數學應用題上達到當時最佳的準確率，甚至超過加了驗證器的微調 GPT-3。

實驗涵蓋五個數學應用題資料集，其中 GSM8K 有 1,391 題、ASDiv 有 2,096 題、AQuA 有 254 題。受測模型包括 GPT-3 的 350M、1.3B、6.7B 與 175B 四種規模，LaMDA 的 137B，以及 PaLM 的 8B、62B 與 540B。示範數固定為 8 個，受限於 1024 個 token 的輸入長度。實驗只做推論，PaLM 540B 跑在 TPU v4 上，配置為 129 顆晶片、384 個核心。

## 算術推理

根據表 1，PaLM 540B 在 GSM8K 上的標準提示準確率只有 17.92%，改用思維鏈後升到 57.6%，再加上外部計算器則為 58.6%。換算下來，思維鏈的準確率約為標準提示的 3 倍。同一資料集上，GPT-3 175B 用思維鏈可達 63.1%，Codex 則有 46.9%，而先前微調方法的最佳成績是 55%。

作者指出，思維鏈只有在約 100M 參數以上的模型才會帶來增益。他們寫道 "chain of thought actually hurts performance for most models smaller than 100B parameters"。

## 錯誤分析

作者人工檢查了 LaMDA 137B 在 GSM8K 上答對的 50 個例子，除了兩個碰巧答對之外，推理過程都正確。在答錯的 50 個例子中，64% 的思維鏈幾乎正確，只差小錯誤，其餘 54% 則有重大的語意理解或連貫性錯誤。細看錯誤類型，8% 只是計算錯誤（calculator error），16% 是符號對應錯誤（symbol mapping error），27% 是少了一個步驟（one step missing）。加上外部計算器後，LaMDA 137B 在 GSM8K 的解題率從 13.4% 升到 17.3%。

在 PaLM 62B 的 45 個錯誤中，語意理解錯誤（semantic understanding）有 20 個、少一步的有 18 個、其他 7 個；換成 540B 後分別修正了 6、12 與 4 個。

## 常識與符號推理

常識推理方面，PaLM 540B 在 StrategyQA 上以 76.5% 超越先前最佳的 69.4%，在日期理解（date understanding）上則以 95.4% 勝過運動迷的 84%。在符號推理上，PaLM 540M 搭配思維鏈的解題率接近 100%。

## 穩健性

硬幣翻轉（coin flip）任務的準確率會隨標註者（annotator）不同，從標註者 A 的 99.6% 掉到標註者 C 的 71.4%，但都高於標準提示的 50.0%。作者也引用前人結果：只改變示範順序，GPT-3 在 SST-2 上的準確率就可從 53.4% 變到 93.4%。兩者相差 39.1 個百分點。

## 結論與限制

結論中，作者寫道 "chain-of-thought reasoning is an emergent property of model scale that allows sufficiently large language models to perform reasoning tasks that otherwise have steep scaling curves"。他們也強調 "Several language models were finetuned in the process of writing this paper"。作者提醒 "standard prompting only provides an upper bound on the capabilities of large language models"。作者更斷言 "chain-of-thought prompting works equally well for models of every size"。

但作者也坦言，「這並不能回答神經網路是否真的在推理」。此外 "there is no guarantee of correct reasoning paths"，錯誤的推理也可能得出正確答案。

## 參考文獻

Wei, J., Wang, X., Schuurmans, D., Bosma, M., Ichter, B., Xia, F., Chi, E. H., Le, Q. V., & Zhou, D. (2022). Chain-of-thought prompting elicits reasoning in large language models. NeurIPS 2022. arXiv:2201.11903.
