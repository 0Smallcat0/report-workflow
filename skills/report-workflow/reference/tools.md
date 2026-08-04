# Tool Reference

Generated from `skills/report-workflow/skill.yaml` by `scripts/render_skill_docs.py`.
Do not edit by hand; run `python scripts/render_skill_docs.py --write`.

The tools are Python functions in `report_workflow.agent_wrapper` that return
JSON-serializable dicts. See the SKILL.md "Invoking the Tools" section for how
to call them in each harness (Codex tool, CLI, or `python -c`).

## `check_setup`

Pre-flight environment check. Call BEFORE start_report_task on every run. Returns pending_installs (missing dependencies the agent should install with user consent), agent_should_ask_user (features to ask about, some requiring user input like API keys or NotebookLM URLs), and a human-readable message summarizing everything. After installing dependencies, re-run check_setup to verify. Does NOT start a workflow.

Parameters: none.

## `start_report_task`

Start the report generation workflow. Parses source files, builds evidence ledger, generates blueprint and task briefs for the agent. Requires check_setup first. The caller must ask the user about every pending install and optional feature, then pass preflight_confirmed=true and a complete preflight_decisions record. preflight_confirmed=true alone is rejected. Required dependencies must actually pass preflight after installation; a decision string does not override a still-missing dependency.

Parameters:

- `prompt` (string, required): User prompt describing the desired report
- `source_files` (list[object], required): Source files to use. Legacy strings are accepted. Prefer structured entries when roles matter: {"path": "source.pdf", "role": "source_data"} or {"path": "base.docx", "role": "base_document"}. Valid roles are source_data and base_document.
- `output_dir` (string, required): Directory to write final output files
- `report_profile` (string, optional): Report profile ID. Built-ins: engineering_lab_report, academic_paper, business_report, proposal, admissions_report, admissions_project_report, and custom. Defaults to profile inference from the prompt, then academic_paper.
- `task_intent` (string, optional): new_draft or revise_existing. Use revise_existing when one structured source entry has role=base_document.
- `title` (string, optional): Structured front matter title. Strongly recommended for academic_paper.
- `author_block` (string, optional): Structured author line for front matter.
- `affiliation_block` (string, optional): Structured affiliation line for front matter.
- `correspondence` (string, optional): Correspondence email/contact for front matter.
- `keywords` (list[string], optional): Structured front matter keywords. Use thesis-aligned academic terms.
- `template_fields` (object, optional): Optional fixed-template/front-matter fields such as course_name, student_id, instructor, lab_section, date, or department. These are rendered into the front matter and audited in template_field_fill_report.json.
- `reference_docx` (string, optional): Optional path to a user-supplied .docx template. The rendered document follows its styles, margins, and header/footer (including page numbers). Requires pandoc; an unusable template hard-blocks the render instead of silently using the default look.
- `project_identity` (object, optional): Optional project identity contract with required_terms, required_context_terms, forbidden_terms, canonical_title_terms, domain_context, and author_metadata. Use to prevent topic drift.
- `enable_research` (boolean, optional): Enable external web research for claim verification. When true, blocked/disputed claims are automatically researched via configured backends (Tavily, Serper, SerpAPI, BrowserMCP). Requires at least one API key env var to be set; falls back to no-op without keys.
- `enable_notebook_sync` (boolean, optional): Enable NotebookLM knowledge sync. When true, the pipeline syncs context from a matching NotebookLM notebook after evidence store. Requires notebooklm-py to be installed.
- `notebooklm_notebook_id` (string, optional): Specific NotebookLM notebook ID to sync with. If not provided, the pipeline selects a notebook matching the report topic.
- `notebooklm_storage_path` (string, optional): Path to NotebookLM authentication storage state file. Auto-detected if not provided (searches ~/.notebooklm/ and LOCALAPPDATA).
- `preflight_confirmed` (boolean, optional): Must be true only after the user has explicitly answered every pending install and optional feature question returned by check_setup.
- `preflight_decisions` (object, optional): Structured record of the user's preflight choices. Required shape: confirmed_by_user=true, install_decisions keyed by pending install, and feature_decisions keyed by feature_id. Use the required_preflight_decisions value from check_setup as the template.
- `allow_degraded_render` (boolean, optional): Set true only after the user explicitly accepts degraded DOCX rendering when a critical render dependency such as pandoc is missing.

## `get_controlled_next_action`

Return the current controlled authoring stage for a job, including the task brief, read-first files, allowed write paths, validation tool, and repair context from the previous failed attempt. Use this by default after start_report_task before editing agent-authored artifacts.

Parameters:

- `job_id` (string, required): The job ID returned by start_report_task
- `workspace_root` (string, optional): Optional output workspace root if the job is outside the default run registry

## `submit_controlled_action`

Submit the current controlled stage. Enforces the harness write scope before running the stage validator, records evidence in harness_manifest.json, advances only on pass, and returns repair context without rerunning unrelated stages when validation fails. Returns blocked_non_author_repair when a read-only stage fails without a legal author-owned repair target.

Parameters:

- `job_id` (string, required): The job ID returned by start_report_task
- `workspace_root` (string, optional): Optional output workspace root if the job is outside the default run registry

## `lint_agent_artifacts`

Read-only lint for agent-authored artifacts before full validation. Writes artifact_lint_report.json with artifact names, JSON paths, severity, messages, and repair hints. Use after creating or changing claim_matrix.json, outline.json, structured_drafts.json, section_drafts/*.md, sentence_map.jsonl, or revision_plan.json.

Parameters:

- `job_id` (string, required): The job ID returned by start_report_task

## `run_engineering_audit`

Read-only engineering lab audit for units, measurements, and simple arithmetic. Writes engineering_audit_report.json with recognized measurements, claim/evidence unit-support warnings, unit notation warnings, table-value support checks, mixed-dimension unit notes, missing-unit notes, and simple calculation result warnings. Recommended for engineering_lab_report.

Parameters:

- `job_id` (string, required): The job ID returned by start_report_task

## `submit_and_publish_report`

Run full validation pipeline and render the final DOCX. Can be called after steps 2-4, or directly after step 1 if all artifacts were created in one shot (legacy 2-step mode). On success, returns post_render_layout_manifest_path for render structure audit evidence plus final_qa_summary_path and final_qa_summary_md_path for delivery readiness review. Also returns scholarly_quality_report_path/scholarly_quality_report_md_path for article-structure and methods/figure/reference scholarly review, figure_visual_quality_report_path for chart readability review, plus template_style_map_path/template_style_map_md_path and template_field_fill_report_path/template_field_fill_report_md_path when published packaging runs.

Parameters:

- `job_id` (string, required): The job ID returned by start_report_task
- `reference_docx` (string, optional): Optional path to a user-supplied .docx template to follow for styles, margins, and header/footer at render time.

## `query_evidence`

Look up specific evidence entries by ID, or browse the evidence ledger in pages. Use this instead of loading the entire evidence_ledger.jsonl file to save context window space.

Parameters:

- `job_id` (string, required): The job ID returned by start_report_task
- `evidence_ids` (list[string], optional): Optional list of specific evidence_id values to retrieve. If provided, offset/limit are ignored.
- `query` (string, optional): Optional text query for relevance-ranked evidence browsing. Supports English terms and CJK bigram matching. Ignored when evidence_ids is provided.
- `offset` (integer, optional): Starting index for paginated browsing (default 0)
- `limit` (integer, optional): Maximum entries to return (default 20, max 50)

## `remap_agent_artifacts`

Remap evidence IDs in claim_matrix.json, sentence_map.jsonl, and section draft [CITE:] markers from a previous job to the current job. Defaults to dry-run; set write=true to update files and refresh artifact contracts.

Parameters:

- `job_id` (string, required): Current workflow job id.
- `previous_job_id` (string, required): Previous workflow job id whose artifacts were reused.
- `write` (boolean, optional): Apply remap changes when true; dry-run when false.

## `submit_revision_plan`

Validate a revision_plan.json for revise_existing workflows. Pre-checks all changes against the base document: verifies original_text matches, detects conflicts, and returns a diff preview. This remains available for legacy compatibility; the default public flow should use get_controlled_next_action and submit_controlled_action so revision_plan edits stay within the harness write-scope contract.

Parameters:

- `job_id` (string, required): The job ID returned by start_report_task

## `preview_revision_diff`

Preview the diff that revision_plan.json would produce without applying any changes. Read-only. Use to inspect before committing.

Parameters:

- `job_id` (string, required): The job ID returned by start_report_task
