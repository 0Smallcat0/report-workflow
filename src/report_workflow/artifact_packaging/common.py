"""Shared helpers for report artifact packaging."""
from __future__ import annotations

import json
from pathlib import Path


def load_json(path: str | None) -> dict:
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_jsonl(path: str | None) -> list[dict]:
    if not path:
        return []
    try:
        rows = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows
    except Exception:
        return []


def write_text(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def write_json(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return str(path)


def existing_path(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    return str(p) if p.exists() else ""


def file_size(path: str | None) -> int:
    if not path:
        return 0
    p = Path(path)
    return p.stat().st_size if p.exists() else 0


def qa_role_for_filename(fname: str) -> str:
    stem = Path(fname).stem
    if fname.endswith(".md"):
        return f"qa_{stem}_markdown"
    return f"qa_{stem}"
