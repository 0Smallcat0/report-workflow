# Sources of the check-draft benchmark

The three PDFs in `sources/` are unmodified copies of arXiv preprints, each
released by its authors under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (as stated on its
arXiv page, checked 2026-10-21). The drafts in `drafts/` were written for this
benchmark and quote and paraphrase them.

| File | Work | SHA-256 |
| --- | --- | --- |
| `2302.13971v1.pdf` | Touvron, H., Lavril, T., Izacard, G., et al. (2023). LLaMA: Open and efficient foundation language models. [arXiv:2302.13971v1](https://arxiv.org/abs/2302.13971v1) | `2e663675ae36ad12adb2f5a05281bac2747ecf8d23d92bedd9f937a89fee7136` |
| `2305.14314v1.pdf` | Dettmers, T., Pagnoni, A., Holtzman, A., & Zettlemoyer, L. (2023). QLoRA: Efficient finetuning of quantized LLMs. [arXiv:2305.14314v1](https://arxiv.org/abs/2305.14314v1) | `33a4e757c19d6ea8d3cca8958fce8fe405e290272e135c99ee66065c775d5bd1` |
| `2201.11903v6.pdf` | Wei, J., Wang, X., Schuurmans, D., et al. (2022). Chain-of-thought prompting elicits reasoning in large language models. [arXiv:2201.11903v6](https://arxiv.org/abs/2201.11903v6) | `7d9f878c23b460e4566aa4ec9201b1abfb3b8faefb2b1356e411cb90fef72a12` |

`labels/` names, for each draft, the figures the writer worked out (expected
NOT_FOUND), the passages the command does not check, and every planted error
with the text it replaced.
