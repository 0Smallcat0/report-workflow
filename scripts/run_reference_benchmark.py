"""Reference checking on a public, hand-labelled dataset, beside five published tools.

Badalova & Mayr (2026), "Detecting Hallucinated and Suspicious Citations: What
Current Tools Can and Cannot Do", hand-checked all 104 references of three
papers (71 verified, 33 problematic: invented works, real titles under
invented authors, DOIs of other papers, placeholder arXiv IDs, wrong venues)
and ran five tools on them: CheckIfExist, HalluCiteChecker, Hallucinator,
HalRef and RefChecker. Their binary outcomes are columns of the same CSV
(Zenodo, doi:10.5281/zenodo.21457492, CC-BY-4.0), so every tool is scored
here against the same labels by the same arithmetic.

A tool "flags" a reference when it reports anything but "fine" -- mismatch,
not found, or needs checking -- which is how the dataset standardizes the
five tools. ``report_workflow.reference_match`` is scored the same way (any
verdict but ``verified`` is a flag), and separately on its definite verdicts
(``mismatch``, ``not_found``, ``retracted``): those are the ones that accuse a
reference, so a wrong one costs an author a real citation.

The registries change, so a live rerun is not reproducible. ``--record`` asks
doi.org, arXiv, Crossref and OpenAlex once and archives every answer, cut to
the fields the comparison reads; the default run and ``--check`` replay that
archive with no network::

    python scripts/run_reference_benchmark.py --download  # dataset -> benchmarks/external_data/
    python scripts/run_reference_benchmark.py --record    # live: re-record registry answers
    python scripts/run_reference_benchmark.py             # replay: regenerate results + summary
    python scripts/run_reference_benchmark.py --check     # replay and diff against the archive

The matcher was developed against this dataset, so it is a development set,
not a held-out one. Not wired into CI: it needs the downloaded dataset.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

from report_workflow import reference_match as rm

ROOT = Path(__file__).resolve().parents[1]
RUN_DATE = "2026-10-21"
EVIDENCE_ROOT = ROOT / "benchmarks" / "evidence" / f"reference_match_{RUN_DATE}"
RESPONSES_PATH = EVIDENCE_ROOT / "registry_responses.json"
DATASET_PATH = ROOT / "benchmarks" / "external_data" / "manual_reference_verification_dataset.csv"
DATASET_URL = (
    "https://zenodo.org/records/21457492/files/manual_reference_verification_dataset.csv?download=1"
)
DATASET_SHA256 = "46bacd05613159795fc62afe51f9b66aaaee35b587fce9b820cb4740a97cd627"
TOOLS = ("checkifexist", "hallucitechecker", "hallucinator", "halref", "refchecker")
DEFINITE = (rm.MISMATCH, rm.NOT_FOUND, rm.RETRACTED)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_dataset() -> None:
    with urllib.request.urlopen(DATASET_URL) as response:
        data = response.read()
    if _sha256(data) != DATASET_SHA256:
        raise SystemExit(f"downloaded dataset sha256 {_sha256(data)} does not match pinned {DATASET_SHA256}")
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATASET_PATH.write_bytes(data)
    print(f"wrote {DATASET_PATH.relative_to(ROOT)} (sha256 verified)")


def load_rows() -> list[dict[str, str]]:
    if not DATASET_PATH.exists():
        raise SystemExit(
            f"dataset not found: {DATASET_PATH.relative_to(ROOT)}\n"
            "fetch it first: python scripts/run_reference_benchmark.py --download"
        )
    data = DATASET_PATH.read_bytes()
    if _sha256(data) != DATASET_SHA256:
        raise SystemExit("dataset sha256 does not match the pinned value; delete it and re-run --download")
    # The file is Windows-1252, and some characters were lost to "?" before
    # it was published; the references are scored as published.
    return list(csv.DictReader(io.StringIO(data.decode("cp1252", errors="replace"))))


# ---------------------------------------------------------------------------
# Registry answers: recorded once, replayed after


def _key(url: str, headers: dict[str, str]) -> str:
    """The request without the caller's contact address or key."""

    parts = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if k not in ("mailto", "api_key")]
    url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
    return f"{url}|{headers.get('Accept', '')}"


_CSL_KEYS = ("DOI", "title", "author", "issued", "published-print", "published-online", "published", "created")


def _trim_csl(item: dict[str, Any]) -> dict[str, Any]:
    out = {key: item[key] for key in _CSL_KEYS if key in item}
    if "author" in out:
        out["author"] = [
            {k: a[k] for k in ("given", "family", "literal", "name") if k in a} for a in out["author"]
        ]
    updates = [
        {k: u[k] for k in ("type", "DOI", "label", "updated") if k in u} for u in item.get("updated-by") or []
    ]
    if updates:
        out["updated-by"] = updates
    return out


def _trim_openalex(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item.get("title"),
        "display_name": item.get("display_name"),
        "authorships": [
            {"author": {"display_name": (a.get("author") or {}).get("display_name")}}
            for a in item.get("authorships") or []
        ],
        "publication_year": item.get("publication_year"),
        "doi": item.get("doi"),
        "id": item.get("id"),
        "is_retracted": item.get("is_retracted"),
    }


_ATOM = "{http://www.w3.org/2005/Atom}"


def _trim_atom(body: str) -> str:
    """The entry's id, dates, title and author names; the abstract is dropped."""

    root = ET.fromstring(body)
    feed = ET.Element(f"{_ATOM}feed")
    for entry in root.findall(f"{_ATOM}entry"):
        kept = ET.SubElement(feed, f"{_ATOM}entry")
        for tag in ("id", "published", "updated", "title"):
            node = entry.find(f"{_ATOM}{tag}")
            if node is not None:
                ET.SubElement(kept, f"{_ATOM}{tag}").text = node.text
        for author in entry.findall(f"{_ATOM}author"):
            ET.SubElement(ET.SubElement(kept, f"{_ATOM}author"), f"{_ATOM}name").text = author.findtext(
                f"{_ATOM}name"
            )
    ET.register_namespace("", _ATOM[1:-1])
    return ET.tostring(feed, encoding="unicode")


def _trim(url: str, status: int, body: str) -> str:
    if status != 200 or not body:
        return body
    host = urllib.parse.urlsplit(url).hostname
    if host == "export.arxiv.org":
        return _trim_atom(body)
    if not body.lstrip().startswith("{"):
        return body
    payload = json.loads(body)
    if host == "doi.org":
        payload = _trim_csl(payload)
    elif host == "api.crossref.org":
        payload = {"message": {"items": [_trim_csl(i) for i in payload.get("message", {}).get("items", [])]}}
    elif host == "api.openalex.org":
        payload = {"results": [_trim_openalex(i) for i in payload.get("results", [])]}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class Recorder:
    """Ask the registries, politely, and keep every answer."""

    def __init__(self) -> None:
        self.responses: dict[str, list[Any]] = {}
        self.last = 0.0

    def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, str]:
        key = _key(url, headers)
        if key in self.responses:
            status, body = self.responses[key]
            return status, body
        wait = 0.2 - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        status, body = rm._http_get(url, headers)  # arXiv's 3 s spacing is applied there
        self.last = time.monotonic()
        if status == 429 or status >= 500:
            raise SystemExit(f"{url} answered {status}; record again when the registry is available")
        self.responses[key] = [status, _trim(url, status, body)]
        return self.responses[key][0], self.responses[key][1]


class Replayer:
    def __init__(self, responses: dict[str, list[Any]]) -> None:
        self.responses = responses

    def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, str]:
        key = _key(url, headers)
        if key not in self.responses:
            raise rm.LookupUnavailable(f"not in the recorded answers: {key}")
        status, body = self.responses[key]
        return status, body


# ---------------------------------------------------------------------------
# Scoring


def _confusion(flags: list[tuple[str, bool]]) -> dict[str, int]:
    tp = sum(label == "problematic" and flagged for label, flagged in flags)
    fp = sum(label == "verified" and flagged for label, flagged in flags)
    positives = sum(label == "problematic" for label, _ in flags)
    negatives = len(flags) - positives
    return {"tp": tp, "fn": positives - tp, "fp": fp, "tn": negatives - fp}


def evaluate(rows: list[dict[str, str]], get: rm.HttpGet) -> dict[str, Any]:
    verdicts = []
    for row in rows:
        check = rm.check_reference(row["reference"], get=get)
        verdicts.append({
            "id": f"{row['document_id']} {row['reference_number']}",
            "label": row["manual_label"],
            "status": check.status,
            "message": check.message,
        })
    ours = _confusion([(v["label"], v["status"] != rm.VERIFIED) for v in verdicts])
    tools = {
        tool: _confusion([(row["manual_label"], row[tool] == "flagged") for row in rows]) for tool in TOOLS
    }
    definite = {
        label: sum(v["label"] == label and v["status"] in DEFINITE for v in verdicts)
        for label in ("problematic", "verified")
    }
    return {
        "dataset": {"url": DATASET_URL, "sha256": DATASET_SHA256, "references": len(rows)},
        "report_workflow": ours,
        "definite_verdicts": definite,
        "statuses": {f"{l}/{s}": n for (l, s), n in sorted(Counter((v["label"], v["status"]) for v in verdicts).items())},
        "tools": tools,
        "verdicts": verdicts,
    }


def write_summary(results: dict[str, Any], path: Path) -> None:
    def row(name: str, c: dict[str, int]) -> str:
        return f"| {name} | {c['tp']} | {c['fn']} | {c['fp']} | {c['tn']} |"

    ours = results["report_workflow"]
    definite = results["definite_verdicts"]
    lines = [
        f"# Reference checking on the Badalova & Mayr dataset ({RUN_DATE})",
        "",
        f"{results['dataset']['references']} hand-checked references from three papers "
        "([Zenodo](https://doi.org/10.5281/zenodo.21457492), CC-BY-4.0); 33 problematic, 71 verified. "
        "A flag is any verdict but \"fine\"; the five tools' outcomes are the dataset's own columns.",
        "",
        "| Tool | Problematic flagged (TP) | Missed (FN) | Verified flagged (FP) | Verified passed (TN) |",
        "| --- | --- | --- | --- | --- |",
        row("**report-workflow check-references**", ours),
        *[row(tool, results["tools"][tool]) for tool in TOOLS],
        "",
        f"Definite verdicts (mismatch, not found, retracted): {definite['problematic']} on problematic "
        f"references, {definite['verified']} on verified ones. The other flags are `needs_review`: a "
        "web page, standard or conference paper that no index holds, or a record that agrees only in part.",
        "",
        "Registry answers were recorded on the run date and are replayed from "
        "`registry_responses.json`, so `--check` reproduces these numbers offline. The matcher was "
        "developed against this dataset.",
        "",
        "## Verdicts",
        "",
        "| Reference | Label | Verdict | Why |",
        "| --- | --- | --- | --- |",
        *[
            f"| {v['id']} | {v['label']} | {v['status']} | {v['message'].replace('|', '/')} |"
            for v in results["verdicts"]
        ],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--download", action="store_true", help="Fetch and sha256-verify the dataset.")
    parser.add_argument("--record", action="store_true", help="Ask the registries live and archive their answers.")
    parser.add_argument("--check", action="store_true", help="Replay the archive and diff against results.json.")
    args = parser.parse_args()

    if args.download:
        download_dataset()
        if not (args.record or args.check):
            return 0
    rows = load_rows()

    if args.record:
        recorder = Recorder()
        results = evaluate(rows, recorder)
        EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
        RESPONSES_PATH.write_text(
            json.dumps(dict(sorted(recorder.responses.items())), indent=1, ensure_ascii=False), encoding="utf-8"
        )
    else:
        if not RESPONSES_PATH.exists():
            raise SystemExit(f"no recorded answers at {RESPONSES_PATH.relative_to(ROOT)}; run --record first")
        responses = json.loads(RESPONSES_PATH.read_text(encoding="utf-8"))
        results = evaluate(rows, Replayer(responses))

    results_path = EVIDENCE_ROOT / "results.json"
    if args.check:
        if not results_path.exists():
            print(f"reference benchmark check failed: missing {results_path.relative_to(ROOT)}")
            return 1
        archived = json.loads(results_path.read_text(encoding="utf-8"))
        if _canonical(archived) != _canonical(results):
            print("reference benchmark check failed: results.json does not match a replay of the recorded answers")
            return 1
        print("reference benchmark check passed")
        return 0

    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    write_summary(results, EVIDENCE_ROOT / "summary.md")
    print(json.dumps({"report_workflow": results["report_workflow"], "definite": results["definite_verdicts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
