# Open foundation models: a short review of LLaMA

## Background

Large language models have improved quickly, but most of the strongest ones are trained on data that nobody outside the company can inspect. Touvron et al. (2023) present LLaMA, a family of foundation language models that range from 7B to 65B parameters. The authors state that "it is possible to train state-of-the-art models using only publicly available datasets, without resorting to proprietary and inaccessible datasets" (Touvron et al., 2023).

Their argument starts from the cost of inference rather than the cost of training. Although Hoffmann et al. (2022) recommend training a 10B model on 200B tokens, the LLaMA team found that the performance of a 7B model continued to improve even after 1T tokens. In their words, "the preferred model is not the cheapest to train but the fastest at inference".

## Data and training

The pre-training mixture is dominated by English CommonCrawl, which makes up 76% of the data, followed by C4 at 15%. GitHub, Wikipedia and Books each contribute 4.5% of the mixture, while ArXiv contributes 2.5% and Stack Exchange 2%. The CommonCrawl portion alone occupies 3.3 GB on disk. During deduplication, books with more than 90% content overlap were removed. In total the training set holds roughly 1.4 billion tokens after tokenization.

The models are trained with AdamW using β1 = 0.9 and β2 = 0.95, a weight decay of 0.95 and gradient clipping of 1.0. The cosine schedule ends at 10% of the maximal learning rate, and training uses 4,000 warmup steps. When training the 65B-parameter model, the code processes around 830 tokens/sec/GPU on 2048 A100 GPUs with 80GB of RAM, so one pass over the 1.4T-token dataset takes approximately 21 hours. That amounts to about 43,000 GPU-days for a single run.

## Results

LLaMA-13B outperforms GPT-3 on most benchmarks even though it is more than 100× smaller. On zero-shot common sense reasoning, LLaMA-65B reaches 85.3 on BoolQ and 82.4 on HellaSwag. It outperforms Chinchilla-70B on all of the reported common sense benchmarks except BoolQ.

On NaturalQuestions, LLaMA-65B obtains an exact match score of 38.9 in the 64-shot setting, and on TriviaQA the 7B model already scores 56.6 zero-shot. For reading comprehension, LLaMA-65B reaches 67.9 on RACE-middle and 51.6 on RACE-high. On GSM8k it scores 50.9 without majority voting and 69.7 with maj1@k, and on HumanEval it obtains a pass@1 score of 23.7.

The one benchmark where the model trails is MMLU: in the 5-shot setting LLaMA-65B averages 63.4, behind Chinchilla-70B at 67.5. The authors attribute the gap to the small amount of books and academic papers in the pre-training data, which "sums up to only 177GB, while these models were trained on up to 1TB of books". A brief instruction finetuning step lifts LLaMA-I to 68.9% on MMLU, a gain of 5.5 points over the base model.

## Bias and toxicity

On CrowS-Pairs, LLaMA-65B averages 66.1, compared with 67.2 for GPT-3 and 69.5 for OPT, where a higher score means more bias. The authors note that the model "is particularly biased in the religion category (+10% compared to OPT-175B)". Over the 100k prompts of RealToxicityPrompts, the 65B model has an average toxicity score of 0.182 on basic prompts and 0.141 on respectful prompts. The authors caution that these evaluations "are sufficient to fully understand the risks associated with these models".

## Cost

Training is not free in carbon terms either, and the authors admit that "open models will soon replace proprietary systems in every application". The paper estimates that developing the models used 2048 A100-80GB GPUs for approximately 5 months, about 2,638.4 MWh, and a total emission of 1,015 tCO2eq. Training LLaMA-65B alone took 1,022,632 GPU-hours.

## References

Touvron, H., Lavril, T., Izacard, G., et al. (2023). LLaMA: Open and efficient foundation language models. arXiv:2302.13971.
