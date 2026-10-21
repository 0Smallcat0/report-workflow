# Finetuning on one GPU: notes on QLoRA

## What the method does

Finetuning a large language model normally needs a cluster. Dettmers et al. (2023) introduce QLoRA, which reduces memory usage enough to finetune a 65B parameter model on a single 48GB GPU. Regular 16-bit finetuning of a LLaMA 65B model requires more than 780 MB of GPU memory, so the gap is large. The method "backpropagates gradients through a frozen, 8-bit quantized pretrained language model into Low Rank Adapters (LoRA)". Going from more than 780 GB to under 48 GB is a reduction of over 16 times.

Three ideas make this work: a 4-bit NormalFloat data type, Double Quantization and Paged Optimizers. Double Quantization saves an average of about 0.37 bits per parameter, approximately 3 GB for a 65B model. With 32-bit constants and a blocksize of 64, the quantization constants cost 0.5 bits per parameter, and quantizing them a second time brings this down to 0.172 bits.

Most of the memory in adapter finetuning is not the adapters themselves. For a 7B LLaMA model, the LoRA input gradients take 567 MB while the LoRA parameters take only 26 MB, and the 4-bit base model consumes 5,084 MB. Including activations, Figure 6 puts the footprint of the 65B model at 45.0 GB.

## Does 4-bit lose accuracy?

Across 125M to 13B models, the mean perplexity is 33.34 with Int4 and 27.41 with NFloat4 plus double quantization. On 5-shot MMLU, NF4 with double quantization averages 53.12 over the LLaMA sizes, compared with 53.0 for BFloat16 and 52.2 for Float4. Float4 therefore trails by 0.8 points. The authors conclude that NF4 with double quantization fully recovers 16-bit LoRA performance on these benchmarks.

## The Guanaco chatbots

Using QLoRA, the authors finetuned more than 1,000 models across 8 instruction datasets. Their best model, Guanaco 65B, reaches 99.8% of the performance level of ChatGPT on the Vicuna benchmark while only requiring 24 minutes of finetuning on a single GPU. The second best, Guanaco 13B, reaches 97.83% and can be trained in less than 12 hours on a single consumer GPU. The smallest Guanaco model requires just 5 GB of memory and outperforms a 26 GB Alpaca model by more than 20 percentage points.

Data quality mattered more than size: in the authors' words, "a 9k sample dataset (OASST1) outperformed a 450k sample dataset (FLAN v2, subsampled) on chatbot performance". The OASST1 data contain 161,434 messages across 66,497 conversations in 35 languages, and keeping only the top reply at each level leaves 9,209 examples. The next best model trained on only open-source data, the HH-RLHF model, scores 30 percentage points lower than Guanaco.

Training used LoRA r = 64 and α = 16 on all linear layers, with an Adam beta2 of 0.999 and a max grad norm of 0.3. Generation used nucleus sampling with p = 0.9 and a temperature of 0.7.

## How the chatbots were judged

The Vicuna benchmark is a set of 80 prompts, and the OASST1 validation set gives 935 unique user queries. In the GPT-4-judged tournament, GPT-4 has an Elo of 1348, Guanaco 65B 1032 and ChatGPT 966. The ratings start at 1,000 with K = 32, and the procedure is repeated 10,000 times with different random seeds. An Elo gap of 100 points means an expected win rate of approximately 65%.

The paper finds that "GPT-4 evaluations are a cheap and reliable alternative to human evaluation", but the agreement is only moderate. At the system level the rankings agree with a Kendall Tau of 0.55 and a Spearman rank correlation of 0.43, while at the example level Fleiss κ is 0.25. Even human annotators agree only moderately with each other, with Fleiss κ = 0.46. GPT-4 also favours its own outputs, with an Elo of 1348 against 1176 from human raters, which the authors describe as "an additional 25% probability of winning against an opponent".

## Limits

On the CrowS bias benchmark, Guanaco-65B averages 45.3, well below the 66.6 of LLaMA-65B. The authors are candid that "we established that QLORA can match full 16-bit finetuning performance at 33B and 65B scales". They also estimate that with an iPhone 12 Plus, QLoRA could finetune 3 billion tokens per night while the phone is charging. Whether such small models are useful in practice is left open, although the authors predict that "4-bit finetuning will make 16-bit training obsolete for every model size".

## References

Dettmers, T., Pagnoni, A., Holtzman, A., & Zettlemoyer, L. (2023). QLoRA: Efficient finetuning of quantized LLMs. arXiv:2305.14314.
