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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", nargs="+", help="published report.docx path(s)")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    results = [measure(path) for path in args.docx]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    for result in results:
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
