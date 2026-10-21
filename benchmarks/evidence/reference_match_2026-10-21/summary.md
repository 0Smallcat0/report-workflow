# Reference checking on the Badalova & Mayr dataset (2026-10-21)

104 hand-checked references from three papers ([Zenodo](https://doi.org/10.5281/zenodo.21457492), CC-BY-4.0); 33 problematic, 71 verified. A flag is any verdict but "fine"; the five tools' outcomes are the dataset's own columns.

| Tool | Problematic flagged (TP) | Missed (FN) | Verified flagged (FP) | Verified passed (TN) |
| --- | --- | --- | --- | --- |
| **report-workflow check-references** | 30 | 3 | 15 | 56 |
| checkifexist | 31 | 2 | 34 | 37 |
| hallucitechecker | 18 | 15 | 20 | 51 |
| hallucinator | 29 | 4 | 28 | 43 |
| halref | 24 | 9 | 53 | 18 |
| refchecker | 32 | 1 | 36 | 35 |

Definite verdicts (mismatch, not found, retracted): 13 on problematic references, 0 on verified ones. The other flags are `needs_review`: a web page, standard or conference paper that no index holds, or a record that agrees only in part.

Registry answers were recorded on the run date and are replayed from `registry_responses.json`, so `--check` reproduces these numbers offline. The matcher was developed against this dataset.

## Verdicts

| Reference | Label | Verdict | Why |
| --- | --- | --- | --- |
| P1 R1 | verified | verified | matches arXiv:2507.19457: title, authors |
| P1 R2 | verified | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P1 R3 | verified | verified | matches https://openalex.org/W4404309352: title, authors |
| P1 R4 | problematic | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P1 R5 | verified | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P1 R6 | verified | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P1 R7 | verified | verified | matches doi:10.5281/zenodo.17199853: title, authors |
| P1 R8 | verified | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P1 R9 | verified | needs_review | doi:10.59350/6jqa2-n7z39 is “The XML Markup Evaluation Corpus” by Rivera (2016); Garnett is not among its authors |
| P1 R10 | verified | verified | matches arXiv:2503.19786: title, authors |
| P1 R11 | verified | verified | matches arXiv:2407.21783: title, authors |
| P1 R12 | verified | verified | matches https://openalex.org/W3013681456: title, authors |
| P1 R13 | verified | verified | matches arXiv:2310.06825: title, authors |
| P1 R14 | verified | verified | matches doi:10.5281/zenodo.14751899: title, authors |
| P1 R15 | verified | verified | matches doi:10.1145/2467696.2467753: title, authors |
| P1 R16 | problematic | verified | matches doi:10.1007/978-3-642-04346-8_62: title, authors |
| P1 R17 | verified | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P1 R18 | verified | verified | matches arXiv:2508.10925: title, authors |
| P1 R19 | verified | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P1 R20 | verified | verified | matches arXiv:2505.15948: title, authors |
| P1 R21 | problematic | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P1 R22 | verified | verified | matches doi:10.5281/zenodo.16325125: title, authors |
| P1 R23 | verified | verified | matches arXiv:2505.09388: title, authors |
| P1 R24 | verified | verified | matches doi:10.48550/arXiv.2412.15115: title, authors |
| P2 R1 | problematic | mismatch | doi:10.12688/f1000research.26932.2 is “Recognizing the value of software: a software citation guide” by Katz et al. (2021), which is not the work this reference names |
| P2 R2 | verified | verified | matches doi:10.1002/asi.23538: title, authors |
| P2 R3 | verified | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P2 R4 | verified | verified | matches doi:10.1002/asi.24454: title, authors |
| P2 R5 | verified | verified | matches doi:10.5281/zenodo.7995565: title, authors |
| P2 R6 | problematic | not_found | DOI 10.1038/s41597-022-01328-8 is not registered (doi.org 404) |
| P2 R7 | verified | verified | matches doi:10.1371/journal.pone.0157989: title, authors |
| P2 R8 | verified | verified | matches doi:10.48550/arXiv.2209.00693: title, authors |
| P2 R9 | problematic | not_found | DOI 10.3233/SW-223172 is not registered (doi.org 404) |
| P2 R10 | problematic | verified | matches https://doi.org/10.48550/arxiv.2512.00001: title, authors |
| P2 R11 | verified | verified | matches doi:10.1038/s41597-023-02208-w: title, authors |
| P2 R12 | verified | verified | matches doi:10.1145/3459637.3481936: title, authors |
| P2 R13 | verified | verified | matches doi:10.26615/978-954-452-056-4_083: title, authors |
| P2 R14 | verified | verified | matches doi:10.21954/ou.rd.30374830.v2: title, authors |
| P2 R15 | verified | verified | matches doi:10.7717/peerj-cs.86: title, authors |
| P3 R1 | verified | verified | matches https://doi.org/10.48550/arxiv.2302.09664: title, authors |
| P3 R2 | verified | verified | matches arXiv:2406.02543: title, authors |
| P3 R3 | verified | verified | matches arXiv:1904.09751: title, authors |
| P3 R4 | problematic | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P3 R5 | problematic | mismatch | https://doi.org/10.48550/arxiv.2210.08933 is “DiffuSeq: Sequence to Sequence Text Generation with Diffusion Models” by Gong et al. (2022); Austin is not among its authors |
| P3 R6 | problematic | not_found | the identifier is a placeholder (XXXX), not a real one |
| P3 R7 | problematic | not_found | the identifier is a placeholder (XXXX), not a real one |
| P3 R8 | problematic | not_found | the identifier is a placeholder (XXXX), not a real one |
| P3 R9 | problematic | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P3 R10 | problematic | not_found | the identifier is a placeholder (XXXX), not a real one |
| P3 R11 | verified | verified | matches doi:10.18653/v1/n18-1101: title, authors |
| P3 R12 | verified | verified | matches https://doi.org/10.48550/arxiv.2006.03654: title, authors |
| P3 R13 | verified | verified | matches arXiv:1804.07461: title, authors |
| P3 R14 | verified | verified | matches doi:10.18653/v1/p17-1147: title, authors |
| P3 R15 | verified | verified | matches https://doi.org/10.48550/arxiv.1506.02142: title, authors |
| P3 R16 | verified | verified | matches https://doi.org/10.48550/arxiv.1612.01474: title, authors |
| P3 R17 | verified | verified | matches https://doi.org/10.48550/arxiv.1802.10501: title, authors |
| P3 R18 | verified | needs_review | https://doi.org/10.17863/cam.49348 is “Ensemble Distribution Distillation” by Gales et al. (2019); Uthoff, Heil, Li are not among its authors |
| P3 R19 | problematic | needs_review | https://doi.org/10.48550/arxiv.1805.11783 is “To Trust Or Not To Trust A Classifier” by Jiang et al. (2018); Pang, Ding, Xu, Carin are not among its authors |
| P3 R20 | problematic | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P3 R21 | problematic | needs_review | doi:10.18653/v1/2021.findings-emnlp carries this title, but its authors could not be compared with the reference's |
| P3 R22 | problematic | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P3 R23 | verified | verified | matches doi:10.18653/v1/2023.emnlp-main.522: title, authors |
| P3 R24 | problematic | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P3 R25 | problematic | mismatch | arXiv:2205.05407 is “Gamma-ray Diagnostics of r-process Nucleosynthesis in the Remnants of Galactic Binary Neutron-Star Mergers” by Terada et al. (2022), which is not the work this reference names |
| P3 R26 | problematic | needs_review | doi:10.18653/v1/2020.findings-emnlp carries this title, but its authors could not be compared with the reference's |
| P3 R27 | problematic | needs_review | https://doi.org/10.18653/v1/2021.emnlp-main carries this title, but its authors could not be compared with the reference's |
| P3 R28 | verified | verified | matches doi:10.18653/v1/2023.findings-eacl.139: title, authors |
| P3 R29 | verified | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P3 R30 | verified | verified | matches https://doi.org/10.48550/arxiv.2312.09300: title, authors |
| P3 R31 | verified | verified | matches doi:10.18653/v1/2023.emnlp-main.330: title, authors |
| P3 R32 | verified | verified | matches doi:10.18653/v1/2024.emnlp-main.578: title, authors |
| P3 R33 | verified | verified | matches doi:10.18653/v1/2024.acl-long.276: title, authors |
| P3 R34 | verified | verified | matches doi:10.18653/v1/2023.emnlp-main.778: title, authors |
| P3 R35 | problematic | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P3 R36 | problematic | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P3 R37 | verified | verified | matches arXiv:2402.03563: title, authors |
| P3 R38 | verified | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P3 R39 | verified | needs_review | https://doi.org/10.48550/arxiv.1610.02424 carries this title and authors, but its year (2016) differs |
| P3 R40 | verified | verified | matches doi:10.18653/v1/2023.acl-long.687: title, authors |
| P3 R41 | verified | verified | matches doi:10.18653/v1/n16-1014: title, authors |
| P3 R42 | verified | verified | matches doi:10.1016/j.csl.2020.101094: title, authors |
| P3 R43 | verified | verified | matches doi:10.18653/v1/D16-1250: title, authors |
| P3 R44 | verified | verified | matches doi:10.18653/v1/p19-1365: title, authors |
| P3 R45 | verified | verified | matches https://openalex.org/W2621351960: title, authors |
| P3 R46 | verified | verified | matches https://openalex.org/W79945118: title, authors |
| P3 R47 | verified | verified | matches doi:10.1613/jair.2985: title, authors |
| P3 R48 | problematic | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P3 R49 | problematic | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P3 R50 | problematic | needs_review | doi:10.3115/v1/d14-1 carries this title, but its authors could not be compared with the reference's |
| P3 R51 | verified | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P3 R52 | problematic | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P3 R53 | problematic | mismatch | arXiv:2107.13586 is “Pre-train, Prompt, and Predict: A Systematic Survey of Prompting Methods in Natural Language Processing” by Liu et al. (2021), which is not the work this reference names |
| P3 R54 | verified | verified | matches arXiv:2305.19187: title, authors |
| P3 R55 | problematic | verified | matches doi:10.1162/tacl_a_00266: title, authors |
| P3 R56 | verified | verified | matches doi:10.18653/v1/2022.acl-long.229: title, authors |
| P3 R57 | problematic | mismatch | doi:10.18653/v1/2020.emnlp-main.466 is “AmbigQA: Answering Ambiguous Open-domain Questions” by Min et al. (2020); Lewis, Jurafsky are not among its authors |
| P3 R58 | problematic | mismatch | arXiv:2205.01068 is “OPT: Open Pre-trained Transformer Language Models” by Zhang et al. (2022); Jiang, Kos are not among its authors |
| P3 R59 | problematic | mismatch | arXiv:2302.13971 is “LLaMA: Open and Efficient Foundation Language Models” by Touvron et al. (2023); Stone, Albert are not among its authors |
| P3 R60 | verified | needs_review | no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title |
| P3 R61 | verified | needs_review | doi:10.1002/9781118445112.stat05402 is “Importance Sampling” by Kong (2014); note on is not among its authors |
| P3 R62 | verified | verified | matches doi:10.18653/v1/W19-8609: title, authors |
| P3 R63 | verified | verified | matches arXiv:1707.06347: title, authors |
| P3 R64 | verified | verified | matches arXiv:2501.12948: title, authors |
| P3 R65 | verified | verified | matches arXiv:1711.05101: title, authors |
