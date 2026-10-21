# check-draft benchmark (2026-10-21)

Rerun: `python scripts/run_draft_benchmark.py --check` (no network, no model).

| split | correct items falsely flagged | planted errors caught | worked-out figures NOT_FOUND |
|---|---|---|---|
| dev | 0/59 (0%) (+0/40 in the planted drafts) | 17/20 (85%) | 2/2 (100%) |
| held_out | 8/141 (6%) (+5/104 in the planted drafts) | 32/39 (82%) | 5/5 (100%) |

## Planted errors by type

| type | dev | held out |
|---|---|---|
| altered_quote | 4/4 (100%) | 8/8 (100%) |
| extra_precision | 1/1 (100%) | 3/3 (100%) |
| fabricated_quote | 1/1 (100%) | 2/2 (100%) |
| misattributed | 0/2 (0%) | 0/4 (0%) |
| wrong_number | 8/9 (89%) | 14/17 (82%) |
| wrong_unit | 3/3 (100%) | 5/5 (100%) |

## llama (dev, 2302.13971v1.pdf)

False alarms on the correct draft: 0

Planted errors missed: 3
- misattributed: `0.95` (found on p. 3) in: The models are trained with AdamW using β1 = 0.9 and β2 = 0.95, a weight decay of 0.95 and gradient clipping of 1.0.
- misattributed: `56.6` (found on p. 5) in: On NaturalQuestions, LLaMA-65B obtains an exact match score of 38.9 in the 64-shot setting, and on TriviaQA the 7B model already scores 56.6 zero-shot.
- wrong_number: `66.1` (found on p. 7) in: On CrowS-Pairs, LLaMA-65B averages 66.1, compared with 67.2 for GPT-3 and 69.5 for OPT, where a higher score means more bias.

## qlora (held_out, 2305.14314v1.pdf)

False alarms on the correct draft: 4
- `780GB` in sentence 4: Going from more than 780 GB to under 48 GB is a reduction of over 16 times.
- `48GB` in sentence 4: Going from more than 780 GB to under 48 GB is a reduction of over 16 times.
- `43.5` in sentence 31: On the CrowS bias benchmark, Guanaco-65B averages 43.5, well below the 66.6 of LLaMA-65B.
- `66.6` in sentence 31: On the CrowS bias benchmark, Guanaco-65B averages 43.5, well below the 66.6 of LLaMA-65B.

Planted errors missed: 3
- misattributed: `10GB` (found on p. 2) in: The smallest Guanaco model requires just 10 GB of memory and outperforms a 26 GB Alpaca model by more than 20 percentage points.
- misattributed: `0.55` (found on p. 10) in: At the system level the rankings agree with a Kendall Tau of 0.55 and a Spearman rank correlation of 0.43, while at the example level Fleiss κ is 0.25.
- wrong_number: `45.3` (found on p. 15) in: On the CrowS bias benchmark, Guanaco-65B averages 45.3, well below the 66.6 of LLaMA-65B.

## cot_zh (held_out, 2201.11903v6.pdf)

False alarms on the correct draft: 4
- `17.9%` in sentence 6: 根據表 1，PaLM 540B 在 GSM8K 上的標準提示準確率只有 17.9%，改用思維鏈後升到 56.9%，再加上外部計算器則為 58.6%。
- `56.9%` in sentence 6: 根據表 1，PaLM 540B 在 GSM8K 上的標準提示準確率只有 17.9%，改用思維鏈後升到 56.9%，再加上外部計算器則為 58.6%。
- `58.6%` in sentence 6: 根據表 1，PaLM 540B 在 GSM8K 上的標準提示準確率只有 17.9%，改用思維鏈後升到 56.9%，再加上外部計算器則為 58.6%。
- `55%` in sentence 8: 同一資料集上，GPT-3 175B 用思維鏈可達 46.9%，Codex 則有 63.1%，而先前微調方法的最佳成績是 55%。

Planted errors missed: 4
- misattributed: `63.1%` (found on p. 20) in: 同一資料集上，GPT-3 175B 用思維鏈可達 63.1%，Codex 則有 46.9%，而先前微調方法的最佳成績是 55%。
- wrong_number: `64%` (found on p. 30) in: 在答錯的 50 個例子中，64% 的思維鏈幾乎正確，只差小錯誤，其餘 54% 則有重大的語意理解或連貫性錯誤。
- wrong_number: `27%` (found on p. 27) in: 細看錯誤類型，8% 只是計算錯誤（calculator error），16% 是符號對應錯誤（symbol mapping error），27% 是少了一個步驟（one step missing）。
- misattributed: `95.4%` (found on p. 7) in: 常識推理方面，PaLM 540B 在 StrategyQA 上以 76.5% 超越先前最佳的 69.4%，在日期理解（date understanding）上則以 95.4% 勝過運動迷的 84%。
