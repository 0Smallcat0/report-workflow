# Graph Report - .  (2026-04-19)

## Corpus Check
- 88 files · ~50,816 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 839 nodes · 2162 edges · 42 communities detected
- Extraction: 55% EXTRACTED · 45% INFERRED · 0% AMBIGUOUS · INFERRED: 971 edges (avg confidence: 0.61)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Abstract Validation|Abstract Validation]]
- [[_COMMUNITY_Document Parsing|Document Parsing]]
- [[_COMMUNITY_CLI Entry Points|CLI Entry Points]]
- [[_COMMUNITY_Numeric Consistency|Numeric Consistency]]
- [[_COMMUNITY_Claim Schema|Claim Schema]]
- [[_COMMUNITY_Parser System|Parser System]]
- [[_COMMUNITY_Factuality Checking|Factuality Checking]]
- [[_COMMUNITY_Artifact Packaging|Artifact Packaging]]
- [[_COMMUNITY_Heading Deduplication|Heading Deduplication]]
- [[_COMMUNITY_Figure Contracts|Figure Contracts]]
- [[_COMMUNITY_Guideline Compliance|Guideline Compliance]]
- [[_COMMUNITY_Agent Task Briefs|Agent Task Briefs]]
- [[_COMMUNITY_QA Gate|QA Gate]]
- [[_COMMUNITY_Academic Report Rules|Academic Report Rules]]
- [[_COMMUNITY_Evidence Normalization|Evidence Normalization]]
- [[_COMMUNITY_Language Sanity|Language Sanity]]
- [[_COMMUNITY_Front Matter Build|Front Matter Build]]
- [[_COMMUNITY_Style Pass|Style Pass]]
- [[_COMMUNITY_Documentation|Documentation]]
- [[_COMMUNITY_APA Citation|APA Citation]]
- [[_COMMUNITY_ArXiv Adapter|ArXiv Adapter]]
- [[_COMMUNITY_PubMed Adapter|PubMed Adapter]]
- [[_COMMUNITY_Claim Plan Prompts|Claim Plan Prompts]]
- [[_COMMUNITY_Intake Prompts|Intake Prompts]]
- [[_COMMUNITY_Writer Prompts|Writer Prompts]]
- [[_COMMUNITY_Tests|Tests]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]

## God Nodes (most connected - your core abstractions)
1. `QAHardBlockError` - 283 edges
2. `ReportState` - 280 edges
3. `AgentWorkRequired` - 92 edges
4. `new()` - 36 edges
5. `write_json_artifact()` - 23 edges
6. `GateTests` - 18 edges
7. `run_qa_gate()` - 17 edges
8. `validate_workflow()` - 16 edges
9. `run_consistency_check()` - 15 edges
10. `prepare_workflow()` - 14 edges

## Surprising Connections (you probably didn't know these)
- `Return the ordered list of sections from the blueprint that are actually planned` --uses--> `QAHardBlockError`  [INFERRED]
  src\report_workflow\nodes\section_contract.py → src\report_workflow\errors.py
- `Validate that all required sections from blueprint are present in the outline.` --uses--> `QAHardBlockError`  [INFERRED]
  src\report_workflow\nodes\section_contract.py → src\report_workflow\errors.py
- `Check if a section requires claims. References and appendix usually do not.` --uses--> `QAHardBlockError`  [INFERRED]
  src\report_workflow\nodes\section_contract.py → src\report_workflow\errors.py
- `Runtime support helpers for job events and artifact lineage.` --uses--> `ReportState`  [INFERRED]
  src\report_workflow\runtime_support.py → src\report_workflow\state.py
- `Load JSONL file, returning empty list if path is None or file doesn't exist.` --uses--> `ReportState`  [INFERRED]
  src\report_workflow\runtime_support.py → src\report_workflow\state.py

## Hyperedges (group relationships)
- **Prepare-Author-Validate/Render Workflow** — agent_onboarding_prepare_phase, agent_onboarding_author_phase, agent_onboarding_validate_render_phase [EXTRACTED 1.00]
- **Required Agent Artifact Set** — agent_onboarding_claim_matrix, agent_onboarding_outline, agent_onboarding_section_drafts, agent_onboarding_sentence_map [EXTRACTED 1.00]
- **Academic Report Constraint Bundle** — agent_onboarding_academic_report, agent_onboarding_imrad_semantics, agent_onboarding_citation_format, agent_instructions_academic_rules [INFERRED 0.89]

## Communities

### Community 0 - "Abstract Validation"
Cohesion: 0.04
Nodes (77): _check_structure(), _count_words(), ABSTRACT_CHECK - merged abstract validation and compression node.  MERGES: abstr, Run all sanity checks. Returns list of error messages., Check word count is in range., ABSTRACT_CHECK - validate (and minimally clean) abstract for academic publicatio, Remove all internal workflow markers from abstract text., Check abstract has required section headings.      Returns list of error message (+69 more)

### Community 1 - "Document Parsing"
Cohesion: 0.04
Nodes (73): _parse_docx_section(), BASE_DOCUMENT_PARSE node - extract sections from a base document for revision., Extract paragraphs from a .docx file as section_chunks.      We avoid heavy depe, T7b: BASE_DOCUMENT_PARSE - extract sections from base_document (if any).      On, run_base_document_parse(), _load_jsonl(), CAPTION_INTERPRETER node - validate and enhance figure captions.  Sits after FIG, T_NEW: CAPTION_INTERPRETER - validate figure captions for academic publication. (+65 more)

### Community 2 - "CLI Entry Points"
Cohesion: 0.06
Nodes (57): Submit the agent-authored artifacts, run validation gates, and render the final, Start the report generation workflow.     This creates the initial task briefs f, start_report_task(), submit_and_publish_report(), build_parser(), _compute_diff(), main(), _parse_source_arg() (+49 more)

### Community 3 - "Numeric Consistency"
Cohesion: 0.05
Nodes (42): _check_numeric_consistency(), _check_unit_notation(), _extract_numeric(), _normalize_unit(), CONSISTENCY_CHECK node - numeric / units consistency.  Sits between FACTUALITY_C, Ensure the same physical quantity is written with the same notation., T13b: CONSISTENCY_CHECK - numeric / units consistency.      Runs after FACTUALIT, Return list of (number_str, unit_str) from text. (+34 more)

### Community 4 - "Claim Schema"
Cohesion: 0.06
Nodes (47): ClaimStatus, ClaimType, RiskLevel, detect_file_type(), CORPUS_BUILD node - enumerate uploaded files into corpus_manifest., Detect file type from extension and content., T5: CORPUS_BUILD - enumerate uploaded files into corpus_manifest., run_corpus_build() (+39 more)

### Community 5 - "Parser System"
Cohesion: 0.05
Nodes (51): parse_agent_fallback(), Agent fallback parser is intentionally unavailable in the local MVP., Return an explicit non-support result instead of pretending to parse., BaseModel, Claim, ClaimMatrix, _chunk_by_size(), parse_code() (+43 more)

### Community 6 - "Factuality Checking"
Cohesion: 0.08
Nodes (29): _allowed_claim_types(), _check_content_overlap(), _claim_id(), _default_allowed_claim_types(), _extract_numbers_with_unit(), _load_jsonl(), _normalize_number_str(), FACTUALITY_CHECK node - verify claim/evidence/sentence linkage.  IMPORTANT data (+21 more)

### Community 7 - "Artifact Packaging"
Cohesion: 0.07
Nodes (34): _build_edit_manifest(), _build_traceability_artifacts(), _collect_paths(), _copy_file(), _load_json(), _load_jsonl(), ARTIFACTS node - package MVP workflow outputs into a structured deliverable.  Co, T25: ARTIFACTS - package all outputs into published directory. (+26 more)

### Community 8 - "Heading Deduplication"
Cohesion: 0.08
Nodes (34): dedupe_merged_draft(), _deduplicate_by_rebuild(), _extract_headings(), _find_duplicate_headings(), HeadingOccurrence, _normalize_heading(), Heading deduplication utilities for merge_draft.  Extracts duplicate ## headings, Remove duplicate and empty heading lines while preserving all content.      Two- (+26 more)

### Community 9 - "Figure Contracts"
Cohesion: 0.09
Nodes (27): _check_academic_report_tables(), _check_figure_contract(), _extract_captions(), _extract_figure_placeholders(), _extract_prose_refs(), FIGURE_CONTRACT_CHECK node - verify figure contract integrity.  Sits between GUI, Check figure contract and return list of issues., T15: FIGURE_CONTRACT_CHECK - validate figure usage contract.      Reads merged_d (+19 more)

### Community 10 - "Guideline Compliance"
Cohesion: 0.08
Nodes (26): _check_guideline(), _check_section_keywords(), _load_guideline(), GUIDELINE_CHECK node - PRISMA / STROBE compliance checking.  Sits between CONSIS, Run all checks for a single guideline.      Returns (hard_violations, soft_viola, T14: GUIDELINE_CHECK - PRISMA / STROBE compliance.      Only runs when selected_, Load a guideline JSON by canonical name (PRISMA, STROBE)., Return True if any detection hint phrase is found in section content.      Perfo (+18 more)

### Community 11 - "Agent Task Briefs"
Cohesion: 0.11
Nodes (24): agent_tasks_dir(), Agent task brief generation for agent-skill-driven workflow stages., Prepare the run for external agent artifact authoring., Write all task briefs required for the external agent authoring phase.      For, _read_jsonl_preview(), run_agent_task_briefs(), write_agent_task_briefs(), _claim_matrix_path() (+16 more)

### Community 12 - "QA Gate"
Cohesion: 0.1
Nodes (24): _artifact_hard_fail_reasons(), _banned_phrase_reasons(), _citation_linkage_reasons(), _load_banned_phrases(), QA_GATE node - pass/fail decision based on factuality and citation reports., For academic_report: require graph + code + research evidence diversity.      ac, T14: QA_GATE - make pass/fail decision based on reports., Return hard-fail reasons if any banned phrase appears in merged draft. (+16 more)

### Community 13 - "Academic Report Rules"
Cohesion: 0.1
Nodes (29): Academic Report Mode Rules, Agent Execution Procedure, academic_report Family, Author Phase, [CITE:<evidence_id>] Citation Format, claim_matrix.json, Evidence Layer, IMRaD Section Semantics (+21 more)

### Community 14 - "Evidence Normalization"
Cohesion: 0.11
Nodes (20): compute_provenance_score(), determine_evidence_type(), determine_granularity(), _determine_source_role(), determine_topic_tags(), _parse_graphify_metadata(), EVIDENCE_NORMALIZE node - deterministic evidence scoring., Compute provenance score deterministically.          Scoring rules (deterministi (+12 more)

### Community 15 - "Language Sanity"
Cohesion: 0.14
Nodes (19): _check_broken_hyphenation(), _check_comparative_no_completion(), _check_duplicate_phrases(), _check_incomplete_clauses(), _check_incomplete_comparatives(), _check_orphan_than_clause(), _check_orphaned_headings(), _check_trailing_ellipses() (+11 more)

### Community 16 - "Front Matter Build"
Cohesion: 0.14
Nodes (19): _build_front_matter(), _enrich_keywords_to_research_level(), _extract_keywords_from_evidence(), _format_front_matter_markdown(), _parse_affiliation_from_user_prompt(), _parse_author_from_user_prompt(), _parse_title_from_user_prompt(), FRONT_MATTER_BUILD node - assemble title page, author block, keywords for academ (+11 more)

### Community 17 - "Style Pass"
Cohesion: 0.22
Nodes (14): _apply_style_polish(), _check_language_sanity(), _check_section_opener(), _compress_sentence(), _fix_marketing_language(), _fix_weasel_words(), _improve_topic_sentence(), _process_paragraph() (+6 more)

### Community 18 - "Documentation"
Cohesion: 0.22
Nodes (9): Read AGENT_ONBOARDING First, Pipeline avoids generative writing so agent owns judgment, Report Workflow, Canonical Package in src/report_workflow, Deterministic Source-to-Report Pipeline, Diagnostics and revision checks are deferred to explicit commands, Report Workflow Local MVP, MVP excludes tracked changes, fallback parsing, and monitoring (+1 more)

### Community 19 - "APA Citation"
Cohesion: 0.4
Nodes (5): format_apa_citation(), format_reference_entry(), APA citation formatter., Format a complete reference entry for the references section., Format a citation in APA style.          Minimal formatter for journal articles,

### Community 20 - "ArXiv Adapter"
Cohesion: 0.5
Nodes (3): ARXIV_ADAPTER - Retrieve preprints from arXiv API., Search arXiv using the arXiv API.          Args:         query: Search query str, search_arxiv()

### Community 21 - "PubMed Adapter"
Cohesion: 0.5
Nodes (3): PUBMED_ADAPTER - Retrieve literature from NCBI PubMed via Entrez API., Search PubMed using NCBI Entrez API.          Args:         query: Search query, search_pubmed()

### Community 22 - "Claim Plan Prompts"
Cohesion: 0.5
Nodes (1): CLAIM_PLAN analyst prompt.

### Community 23 - "Intake Prompts"
Cohesion: 0.5
Nodes (1): INTAKE system and user prompt.

### Community 24 - "Writer Prompts"
Cohesion: 0.5
Nodes (1): SECTION_DRAFT writer prompt.

### Community 25 - "Tests"
Cohesion: 1.0
Nodes (1): Regression tests for the report workflow.

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (0): 

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (0): 

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (0): 

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (0): 

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (1): Load state from last checkpoint.

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (0): 

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (0): 

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (0): 

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (0): 

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (0): 

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (0): 

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (0): 

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (0): 

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (0): 

## Ambiguous Edges - Review These
- `Deterministic Source-to-Report Pipeline` → `anthropic dependency`  [AMBIGUOUS]
  requirements.txt · relation: conceptually_related_to

## Knowledge Gaps
- **62 isolated node(s):** `Shared workflow exceptions.`, `Raised when the workflow must stop before publishing.`, `Raised when an external agent must create required workflow artifacts.`, `ReportState - the single source of truth for the report workflow.`, `Write current state to checkpoint file.` (+57 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Tests`** (2 nodes): `Regression tests for the report workflow.`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (1 nodes): `setup_skill.ps1`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (1 nodes): `_graphify_ast.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (1 nodes): `_graphify_cache.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (1 nodes): `_graphify_detect.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (1 nodes): `Load state from last checkpoint.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Deterministic Source-to-Report Pipeline` and `anthropic dependency`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `QAHardBlockError` connect `Document Parsing` to `Abstract Validation`, `CLI Entry Points`, `Numeric Consistency`, `Claim Schema`, `Parser System`, `Factuality Checking`, `Heading Deduplication`, `Figure Contracts`, `Guideline Compliance`, `Agent Task Briefs`, `QA Gate`, `Evidence Normalization`, `Language Sanity`, `Front Matter Build`, `Style Pass`?**
  _High betweenness centrality (0.253) - this node is a cross-community bridge._
- **Why does `ReportState` connect `Abstract Validation` to `Document Parsing`, `CLI Entry Points`, `Numeric Consistency`, `Claim Schema`, `Parser System`, `Factuality Checking`, `Artifact Packaging`, `Heading Deduplication`, `Figure Contracts`, `Guideline Compliance`, `Agent Task Briefs`, `QA Gate`, `Evidence Normalization`, `Language Sanity`, `Front Matter Build`, `Style Pass`?**
  _High betweenness centrality (0.247) - this node is a cross-community bridge._
- **Why does `AgentWorkRequired` connect `CLI Entry Points` to `Abstract Validation`, `Document Parsing`, `Numeric Consistency`, `Claim Schema`, `Factuality Checking`, `Figure Contracts`, `Guideline Compliance`, `Agent Task Briefs`, `QA Gate`, `Evidence Normalization`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Are the 279 inferred relationships involving `QAHardBlockError` (e.g. with `Start the report generation workflow.     This creates the initial task briefs f` and `Submit the agent-authored artifacts, run validation gates, and render the final`) actually correct?**
  _`QAHardBlockError` has 279 INFERRED edges - model-reasoned connections that need verification._
- **Are the 276 inferred relationships involving `ReportState` (e.g. with `Command line interface for the agent-skill-driven report workflow.` and `Parse 'PATH:ROLE' into (path, role). ROLE defaults to 'source_data'.      Suppor`) actually correct?**
  _`ReportState` has 276 INFERRED edges - model-reasoned connections that need verification._
- **Are the 108 inferred relationships involving `str` (e.g. with `start_report_task()` and `submit_and_publish_report()`) actually correct?**
  _`str` has 108 INFERRED edges - model-reasoned connections that need verification._