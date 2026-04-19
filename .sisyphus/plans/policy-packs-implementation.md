# Policy Packs Implementation Plan

## Problem

75 `report_family` conditionals scattered across 21 files. Each node independently checks `state.spec.get("report_family")` and branches. Adding a new family requires touching every file.

## Goal

Replace scattered conditionals with a single `self.policy.front_matter().required` call. Nodes delegate family-specific decisions to a PolicyPack.

## Option Analysis

| Option | Description | Risk | Effort | Config Files |
|--------|-------------|------|--------|-------------|
| **A: Config Wrapper** | PolicyPack wraps existing config loading; provides clean interface; config files stay as-is | LOW | ~1 new file, ~10 node edits | Unchanged |
| **B: Full Policy Objects** | Each policy method returns rich objects with validation logic | HIGH | ~5 files, ~21 node edits | Redundant with existing |
| **C: Incremental Facade** | Start with A; gradually migrate logic to B over time | LOW-MEDIUM | Iterative | Unchanged initially |

**Recommendation: Option A (Config Wrapper)**

Existing configs already have all family-specific data. PolicyPack just wraps config loading into a unified interface.

## Design

### File Structure

```
src/report_workflow/
├── policies/
│   ├── __init__.py
│   └── policy_pack.py      # ReportPolicy base + 3 concrete classes + factory
```

### Class Hierarchy

```python
# policies/policy_pack.py

class FrontMatterPolicy:
    required: bool           # True for academic
    placeholder_blocked: bool  # True for academic
    author_block_required: bool  # True for academic

class AbstractPolicy:
    word_count_min: int     # 180 for academic
    word_count_max: int     # 220 for academic
    structure_required: bool  # True for academic

class CitationPolicy:
    style: str              # "APA" for academic, "none" for work
    source_marker_hard_block: bool  # True for academic

class ReferencePolicy:
    doi_verification_required: bool  # True for academic
    arxiv_verification_required: bool  # True for academic

class FigurePolicy:
    audit_table_hard_block: bool  # True for academic
    figure_contract_required: bool  # True for academic

class ResultsPolicy:
    empirical_strict: bool  # True for academic
    architectural_allowed: bool  # True for academic

class ClaimPolicy:
    primary_source_required: bool  # True for academic
    role_validation_required: bool  # True for academic

class ReportPolicy:
    front_matter: FrontMatterPolicy
    abstract: AbstractPolicy
    citation: CitationPolicy
    reference: ReferencePolicy
    figure: FigurePolicy
    results: ResultsPolicy
    claim: ClaimPolicy
    banned_phrases: list[str]

class AcademicReportPolicy(ReportPolicy): ...
class WorkReportPolicy(ReportPolicy): ...
class HybridReportPolicy(ReportPolicy): ...

# Factory
def get_policy(family: str) -> ReportPolicy:
    return {"academic_report": AcademicReportPolicy(), ...}[family]
```

### Config Loading (inside PolicyPack.__init__)

Each policy class loads its data from existing config files:

- `banned_phrases` → reads `configs/banned_phrases.json` for the family key
- `citation.style` → hard-coded per class (APA/none)
- `front_matter.required` → hard-coded per class
- `figure.audit_table_hard_block` → hard-coded per class
- `guideline_severity` → reads `configs/guideline_severity_policy.json`

### Implementation Steps

#### Step 1: Create policies/policy_pack.py
- Write `ReportPolicy` base class with all policy sub-objects
- Write `AcademicReportPolicy`, `WorkReportPolicy`, `HybridReportPolicy`
- Write `get_policy(family: str) -> ReportPolicy` factory
- All data from existing configs; no duplication

#### Step 2: Refactor qa_gate.py (HIGHEST PRIORITY)
Most family conditionals (6+ checks). Proof-of-concept.

Replace:
```python
# OLD
if report_family != "academic_report":
    return reasons
# ... academic-specific checks
```

With:
```python
# NEW
policy = get_policy(state.spec.get("report_family", "academic_report"))
if not policy.front_matter.required:
    return reasons
# ... policy-driven checks
```

Specifically:
- `_load_banned_phrases(report_family)` → `get_policy(family).banned_phrases`
- `_results_section_reasons()` → `policy.results.empirical_strict` guard
- `_diversity_reasons()` → `policy.claim.primary_source_required` guard
- `_citation_audit_reasons()` → `policy.citation.source_marker_hard_block`

#### Step 3: Refactor front_matter_build.py
Replace `if report_family == "academic_report":` blocks with `policy.front_matter.*` calls.

#### Step 4: Refactor remaining nodes
In order of conditional count:
1. `abstract_check.py` — `policy.abstract.word_count_min/max`
2. `paper_scope_freeze.py` — `policy.claim.role_validation_required`
3. `merge_draft.py` — `policy.figure.audit_table_hard_block`
4. `figure_quality.py` — `policy.figure.audit_table_hard_block`
5. `citation_bind.py` — `policy.citation.source_marker_hard_block`
6. `reference_verify.py` — `policy.reference.doi_verification_required`
7. `guideline_select.py` — `policy.guideline_defaults`
8. `docx_render.py` — `policy.citation.style` for draft selection
9. `section_role_check.py` — `policy.claim.role_validation_required`

#### Step 5: Tests
Run full suite: `python -m unittest discover -s tests -v`
Expected: all 74 pass unchanged (behavior identical, just refactored)

### What Does NOT Change
- Config files (JSON/YAML) stay as-is
- Blueprint YAML files stay as-is
- `state.spec["report_family"]` stays as-is
- Node order in validate_nodes() stays as-is
- Checkpoint format stays as-is

### Risk Mitigation
1. **Test-first**: Each node refactor, run tests immediately
2. **Behavior-preserving**: Only extract existing if/else logic into policy calls
3. **No new validation**: Don't add logic that wasn't already there
4. **Factory guards**: `get_policy()` raises on unknown family (matching existing behavior)

## Files to Create
- `src/report_workflow/policies/__init__.py`
- `src/report_workflow/policies/policy_pack.py`

## Files to Modify (9 nodes + tests)
- `src/report_workflow/nodes/qa_gate.py`
- `src/report_workflow/nodes/front_matter_build.py`
- `src/report_workflow/nodes/abstract_check.py`
- `src/report_workflow/nodes/paper_scope_freeze.py`
- `src/report_workflow/nodes/merge_draft.py`
- `src/report_workflow/nodes/figure_quality.py`
- `src/report_workflow/nodes/citation_bind.py`
- `src/report_workflow/nodes/reference_verify.py`
- `src/report_workflow/nodes/guideline_select.py`
- `src/report_workflow/nodes/docx_render.py`
- `src/report_workflow/nodes/section_role_check.py`
