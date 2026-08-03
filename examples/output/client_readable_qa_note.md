# Client-Readable QA Note

- QA decision: pass
- Artifact completeness: pass

## What Backs Each Claim

Every claim below had to link to material from the supplied sources before it could appear in the report. What each one rests on is quoted beneath it.

### 1. Across the same 42 notes the structured workflow cut the median from 28.0 to 20.0 minutes per note, rework from 7.5% to 4.1%, and raised reviewer satisfaction from 71% to 84%.

- Status: verified (c_measurement)
- From `pilot_results.csv` (high): {"Condition": "Structured workflow", "Notes processed": "42", "Median minutes per note": "20.0", "Rework rate (%)": "4.1", "Reviewer satisfaction (%)": "84"}

### 2. The desk's monthly median fell from 28.4 minutes per note in January to 20.0 in June as the structured workflow was phased in.

- Status: verified (c_trend)
- From `monthly_medians.csv` (high): {"Month": "2026-01", "Median minutes per note": "28.4"}

### 3. The same 42 client notes were processed twice, by the same two reviewers in the same week, with no change to the intake form.

- Status: verified (c_method)
- From `pilot_brief.md` (medium): The same 42 client notes were processed twice: once with the manual baseline that the desk uses today, and once with the structured workflow. The same two reviewers handled both passes, in the same week, with no change to the intake form. E [...]

### 4. Adoption costs a one-off USD 4,800 for template work and two onboarding sessions, and takes about six weeks to pay back in speed.

- Status: verified (c_cost)
- From `pilot_brief.md` (medium): Setup is a one-off USD 4,800, covering the template work and two onboarding sessions. The desk should expect roughly six weeks before the new routine is faster than the old one, because reviewers spend the first fortnight checking the struc [...]

### 5. Satisfaction came from the two reviewers who ran the pilot, so it supports the finding rather than carrying it.

- Status: verified (c_limit)
- From `pilot_brief.md` (medium): One desk, one week, two reviewers, 42 notes. Reviewer satisfaction was collected from those two reviewers only, so it supports the finding rather than carrying it. Nothing here establishes what happens at a desk with a different note format [...]

## Package Contents

The report, the source materials it was built from, the evidence ledger, the machine-readable claim audit, and the QA summaries.
