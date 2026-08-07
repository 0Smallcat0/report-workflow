# Argument rubric — fixed, written before any document was judged

Three dimensions, each scored 0 to 4 by an LLM judge reading the whole document.
Three independent votes per document per dimension; the recorded score is the
**median** of the three. Every vote carries the evidence it was based on, so a
vote can be argued with rather than merely disagreed with.

This rubric is fixed. It was written before the tool arm existed in recorded
form, and it is not to be edited to change an outcome — a rubric its own author
can adjust until the result comes out right measures the author, not the report.
If it is genuinely wrong, replace it and re-judge **all three arms** in the same
pass, and say in the archive that this happened.

## Why a judge and not a rule

Layout is structural, so `scripts/report_axes.py` measures it with rules.
Argument is semantic. Every deterministic proxy for "is this argued well"
available here — claims per section, evidence ids per claim, counter-evidence
paragraph counts — measures a shape that a document can have while arguing
nothing. Substituting a proxy for the thing is the exact failure that produced
this repository's over-design, and it is not going to be repeated one level down
in the instrument.

## Conflict of interest, stated

The judge is the same agent that wrote the harness being measured, and one of
the three arms is that harness's output. There is no way to remove this within
a single session. What is done instead: the rubric is fixed in advance, every
vote records the passage it rests on, all three arms are judged in the same pass
with the same prompt, and the votes are archived so a third party can re-read a
document and disagree with a specific score. Anyone who wants an independent
judgement can re-run the votes and replace the archive.

---

## Dimension 1 — `claim_strength`

**Does each substantive section assert something that could be wrong, rather
than restating what the data contains?**

A claim is an assertion a reader could disagree with on the evidence.
「$200–500 的評論數中位數是 327 則」 is data.
「需求的重心和供給的重心不在同一個價格帶」 is a claim.

- **0** — No section asserts anything. The document is a description of the data
  with headings.
- **1** — One or two sections assert something; the rest restate figures.
- **2** — About half the substantive sections carry an assertion, and the
  assertions are mostly restatements one level up.
- **3** — Most substantive sections carry an assertion that could be wrong, and
  the assertions are specific enough to be checked against the data.
- **4** — Every substantive section carries an assertion that could be wrong,
  the assertions connect to each other, and at least one of them is a
  non-obvious reading the data supports but does not state.

## Dimension 2 — `evidence_depth`

**Is each main assertion carried by more than one independent piece of
evidence, or does it rest on a single figure?**

Independent means the pieces do not derive from one another. 「評論數中位數 327 則」
and 「累積評論總數」 are the same evidence twice. 「評論數中位數」、「銷量欄位覆蓋率」
and 「一二星佔比」 are three.

- **0** — Assertions rest on nothing identifiable, or on figures the document
  does not state.
- **1** — Each assertion rests on one figure.
- **2** — Main assertions rest on two figures, sometimes derived from each other.
- **3** — Main assertions rest on two or more genuinely independent figures, and
  the document says which figures those are.
- **4** — Main assertions rest on three or more independent figures, the
  document says why those particular figures are the right ones, and it
  distinguishes evidence that supports from evidence that merely does not
  contradict.

## Dimension 3 — `counter_specificity`

**When the document says what would weaken it, does it name which conclusion is
weakened, by what evidence, and with what number?**

A limitation that could be pasted into any report (「樣本數有限，結論僅供參考」)
scores 0 regardless of how many of them there are.

- **0** — No counter-evidence, or only boilerplate limitations.
- **1** — Limitations are named but generic; none points at a specific
  conclusion in this document.
- **2** — At least one limitation names a specific conclusion it weakens, but
  without a figure.
- **3** — Most limitations name both the conclusion they weaken and the figure
  that weakens it.
- **4** — Limitations name the conclusion, the figure, and the direction of the
  bias; at least one of them is strong enough that it changes what the document
  recommends, and the document says so rather than proceeding as if it had not.

---

## Vote format

Each vote is one JSON object:

```json
{
  "arm": "hand | tool | llm_direct",
  "vote": 1,
  "claim_strength": {"score": 3, "evidence": "..."},
  "evidence_depth": {"score": 3, "evidence": "..."},
  "counter_specificity": {"score": 4, "evidence": "..."}
}
```

Recorded score per dimension is the median of the three votes' scores.
