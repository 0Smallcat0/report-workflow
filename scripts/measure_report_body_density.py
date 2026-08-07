"""How much of a published report is the author's analysis.

Three numbers decide whether this pipeline produced a document worth handing in
rather than a ledger with prose around it: how many figures the body states, how
many tables it carries, and what share of the document is body at all. They were
measured by a script pasted into a prompt, and the heading it split on --
``參考文獻|參考資料|References|來源清單|Sources`` -- is not the heading this
pipeline emits. Every run therefore counted its own source list as body and
reported 100%, which is a threshold nothing can fail.

So the split is taken from the constants that write the heading, not from a list
retyped next to them. Rename the heading and this follows; rename it with a
pasted regex and the measurement silently starts passing everything again.

    python scripts/measure_report_body_density.py <run_dir>/published/report.docx
    python scripts/measure_report_body_density.py --json out/*/published/report.docx
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from report_workflow.nodes.citation_bind import (  # noqa: E402
    SOURCE_LIST_HEADING,
    SOURCE_LIST_HEADING_ZH,
)

#: Headings that end the body. The two the pipeline generates come from the
#: constants above; these are what an author writes by hand for the same
#: purpose, and a report carrying one of those instead must not have its whole
#: tail measured as analysis.
AUTHORED_TAIL_HEADINGS = (
    "參考文獻", "参考文献", "參考資料", "参考资料",
    "來源清單", "来源清单", "引用文獻", "引用文献",
    "References", "Reference List", "Bibliography", "Works Cited",
    "Sources", "Source List",
)


def tail_headings() -> tuple[str, ...]:
    """Every heading whose arrival means the analysis has ended."""
    generated = tuple(
        heading.lstrip("# ").strip()
        for heading in (SOURCE_LIST_HEADING, SOURCE_LIST_HEADING_ZH)
    )
    seen: list[str] = []
    for heading in generated + AUTHORED_TAIL_HEADINGS:
        if heading and heading not in seen:
            seen.append(heading)
    return tuple(seen)


def tail_heading_re() -> re.Pattern[str]:
    return re.compile(
        r"(?m)^\s*(?:%s)\s*$" % "|".join(re.escape(head) for head in tail_headings())
    )


#: A stated figure: an integer, a decimal, or a percentage. Thousands separators
#: belong to the number; a preceding word character or dot means this is the
#: middle of something rather than the start of a figure.
NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*\.?\d*%?")


def document_text(xml: str) -> str:
    """The document as plain text, one line per paragraph."""
    return re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml))


def measure(docx_path: str | Path) -> dict:
    """Body figures, tables, drawings, and the body's share of the document."""
    xml = zipfile.ZipFile(docx_path).read("word/document.xml").decode("utf-8")
    text = document_text(xml)
    match = tail_heading_re().search(text)
    body = text[:match.start()] if match else text
    return {
        "path": str(docx_path),
        "body_numbers": len(NUMBER_RE.findall(body)),
        "tail_numbers": len(NUMBER_RE.findall(text[match.start():])) if match else 0,
        "tables": xml.count("<w:tbl>"),
        "figures": xml.count("<w:drawing>"),
        "body_chars": len(body),
        "document_chars": len(text),
        "body_share": round(len(body) / len(text) * 100, 1) if text else 0.0,
        # Absent means the whole document counted as body. That is either a
        # report with no source list or a heading this script does not know, and
        # those are not the same thing -- so it is reported rather than left to
        # look like a clean 100%.
        "tail_heading": match.group(0).strip() if match else None,
    }


def measure_run(run_dir: str | Path) -> dict:
    """The density of a run's document, plus what the run did with its evidence.

    Three of the acceptance conditions are not properties of the DOCX. Whether a
    cross-file join reached a conclusion, how many built tables were placed, and
    how many derivations the author had to register by hand all live in the run's
    artifacts, and measuring them by eye produced a wrong answer once already: a
    join was looked for as a marker on the evidence record, where it does not
    appear, and three runs that each carried nine or ten join-backed conclusions
    were reported as carrying none. A joined derivation surfaces under the id
    ``E_D_<request id>``, which is what this matches.
    """
    run_dir = Path(run_dir)
    result: dict = {"run_dir": str(run_dir)}

    docx_path = run_dir / "published" / "report.docx"
    if docx_path.exists():
        result.update(measure(docx_path))

    derivations = []
    request_path = run_dir / "derived_evidence.json"
    if request_path.exists():
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        rows = payload.get("derivations") if isinstance(payload, dict) else payload
        derivations = [row for row in (rows or []) if isinstance(row, dict)]

    claims = []
    claim_path = run_dir / "claim_matrix.json"
    if claim_path.exists():
        payload = json.loads(claim_path.read_text(encoding="utf-8"))
        claims = [c for c in (payload.get("claims") or []) if isinstance(c, dict)]

    join_ids = {
        "E_D_" + re.sub(r"[^A-Za-z0-9_]+", "_", str(row.get("id") or "").strip())[:48]
        for row in derivations
        if row.get("join")
    }
    result["join_derivations"] = len(join_ids)
    result["claims_citing_a_join"] = sum(
        1 for claim in claims if join_ids & set(claim.get("evidence_ids") or [])
    )
    result["claims"] = len(claims)
    # Registered by hand is the whole request file: every entry in it is one the
    # author wrote. The pipeline's own cross tabulations never appear here.
    result["hand_registered_derivations"] = len(derivations)

    coverage_path = run_dir / "derived_table_coverage.json"
    if coverage_path.exists():
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
        result["built_tables"] = len(coverage.get("available") or [])
        result["built_tables_placed"] = len(coverage.get("placed") or [])
        result["built_tables_waived"] = len(coverage.get("waived") or {})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="+",
        help="published report.docx path(s), or run directories to measure whole",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    results = [
        measure_run(target) if Path(target).is_dir() else measure(target)
        for target in args.target
    ]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    for result in results:
        if "path" in result:
            print(Path(result["path"]).parent.parent.name or result["path"])
            print(f"  body numbers  {result['body_numbers']}")
            print(f"  tables        {result['tables']}")
            print(f"  figures       {result['figures']}")
            print(f"  body share    {result['body_share']}%")
            if result["tail_heading"] is None:
                print("  tail heading  (none found - the whole document counted as body)")
            else:
                print(f"  tail heading  {result['tail_heading']}"
                      f" ({result['tail_numbers']} numbers after it)")
        else:
            print(result["run_dir"])
            print("  (no published/report.docx under this run)")
        if "claims_citing_a_join" in result:
            print(f"  join claims   {result['claims_citing_a_join']}"
                  f" of {result['claims']} (from {result['join_derivations']}"
                  " joined derivation(s))")
            print(f"  hand-registered derivations {result['hand_registered_derivations']}")
        if "built_tables" in result:
            print(f"  built tables  {result['built_tables_placed']} placed,"
                  f" {result['built_tables_waived']} waived,"
                  f" of {result['built_tables']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
