# Contributing

This project is feature-complete for what it set out to do. That is not a
closed door — bug reports and fixes are the most useful thing you can send, and
they are read. It does mean the scope below is settled, so a change that widens
it will be declined however good it is.

## The fastest useful bug report

Nearly every defect in this repository was found by running the tool on a real
document until it stopped. If that happened to you, you are already holding the
most valuable thing: **what you gave it, and where it stopped.**

Include:

- `report-workflow --version` (or `python -m report_workflow --version`), your
  OS, and whether `pandoc --version` answers
- the profile you used and the command or tool call you ran
- what the run said — the error, or the sentence in the document that is wrong
- from the run directory, `published/qa/final_qa_summary.md` if you got that far

Do not attach anything confidential. If your sources are private, the QA pack
and the error message are usually enough; if they are not, a two-line synthetic
file that reproduces the same stop is better than a redacted real one.

## What is in scope

- **Defects.** Something rendered wrong, a gate blocked a claim it should not
  have, a claim it should have blocked got through, a message told you the wrong
  thing, a file your users actually have could not be read.
- **The seven built-in profiles** and both languages (English and Chinese).
- **Making an existing node do its job correctly**, including cases nobody ran
  yet — an unusual source format, a table shape, a document that came back for a
  second revision.

A message that misleads counts as a defect here. Several releases exist because
the tool reported the wrong reason for stopping, and the wrong reason costs more
than the stop.

## What is out of scope

Not because the ideas are bad — because each one doubles the surface a single
maintainer has to keep honest:

- **An eighth report profile**, or any new public selector for report shape.
  `report_profile` is the only one, and there is no `report_family`, detail
  level, subtype, or variant.
- **A semantic layer.** The gates are lexical on purpose: same input, same
  verdict, no model in the checker. Judging whether a paraphrase preserves
  meaning is what an NLI model or an LLM judge is for, and this project is
  designed to be the cheap deterministic pass in front of one.
- **A second rendering backend.** pandoc, with `python-docx` as the degraded
  fallback.
- **Venue or journal formatting** (two-column layouts, per-conference styles).
  Bring your own `.docx` template instead — `--reference-docx` follows its
  styles, margins, and header/footer.
- **A web UI, a hosted service, or anything that needs an account.**

If a benchmark number moves, note that the documented misses in the adversarial
corpus are deliberate. They mark the measured edge of what lexical checking can
do, so a PR that raises recall by deleting them will be declined.

## Running the checks

```powershell
pip install -r requirements.txt
pip install -e .

python -m compileall -q src tests
python -m unittest discover -s tests
```

If your change touches the factuality gates or any profile behaviour, also run
what CI runs:

```powershell
python scripts/run_report_benchmarks.py --check
python scripts/run_adversarial_benchmark.py --check
python scripts/render_skill_docs.py --check
```

A test that only asserts the code does what it does is not worth adding. The
tests here name the defect they prevent, in the reader's words, and say how it
was found; `tests/test_roadmap_contracts.py` is full of examples.

Two habits this repository learned the hard way, and asks of a PR:

- **Verify by running, not by reading.** A conclusion drawn from the source is
  weaker evidence than the same conclusion drawn from a real run, and several
  defects here survived a code reading before a run caught them.
- **Check the branch beside the one you fixed.** Three separate defects in this
  project's history are the untouched neighbour of an earlier fix.

## The development contract

`AGENTS.md` is authoritative for repository work: layout, stage lists, the
artifact contract, the hard gates, and how to add a substep. Read it before
changing anything under `src/`.
