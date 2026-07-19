"""Code parser for Python, JavaScript, TypeScript and similar languages.

Splits source files into class/function/method blocks, each with
line_start, line_end, content_hash, source_file_path, and quote metadata.
Falls back to fixed-size (50-line) chunks when structural parsing fails.
"""
import hashlib
import re
from pathlib import Path


# ------------------------------------------------------------------
# Language-specific structural parsers
# ------------------------------------------------------------------

def _split_python(source: str) -> list[tuple[str, int, int]]:
    """Split Python source into (name, line_start, line_end) units.

    Each class and top-level function (with its decorator) forms a unit.
    """
    units: list[tuple[str, int, int]] = []
    lines = source.splitlines()
    n = len(lines)

    i = 0
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Collect decorators before a def/class
        decorator_lines = []
        while i < n and lines[i].strip().startswith("@"):
            decorator_lines.append(i)
            i += 1

        if i >= n:
            break

        line = lines[i].strip()

        # class definition
        m = re.match(r"^class\s+(\w+)", line)
        if m:
            start = i + 1  # 1-based
            name = m.group(1)
            # Find end: dedent back to original indent or end of file
            if decorator_lines:
                start = decorator_lines[0] + 1
            indent = len(lines[i]) - len(lines[i].lstrip())
            j = i + 1
            while j < n:
                cur = lines[j]
                if cur.strip() and not cur.startswith("#"):
                    cur_indent = len(cur) - len(cur.lstrip())
                    if cur_indent <= indent and cur.strip().startswith(("class ", "def ", "async ", "@")):
                        break
                j += 1
            units.append((name, start, j))
            i = j
            continue

        # function definition
        m = re.match(r"^(?:async\s+)?def\s+(\w+)", line)
        if m:
            start = i + 1
            name = m.group(1)
            if decorator_lines:
                start = decorator_lines[0] + 1
            indent = len(lines[i]) - len(lines[i].lstrip())
            j = i + 1
            while j < n:
                cur = lines[j]
                if cur.strip() and not cur.startswith("#"):
                    cur_indent = len(cur) - len(cur.lstrip())
                    if cur_indent <= indent and cur.strip().startswith(("def ", "async ", "class ", "@")):
                        break
                j += 1
            units.append((name, start, j))
            i = j
            continue

        i += 1

    return units


def _split_js(source: str) -> list[tuple[str, int, int]]:
    """Split JavaScript/JSX source into function/class units."""
    units: list[tuple[str, int, int]] = []
    lines = source.splitlines()
    n = len(lines)

    i = 0
    while i < n:
        line = lines[i].strip()

        # function declaration
        m = re.match(r"^(?:async\s+)?function\s+(\w+)", line)
        if m:
            start = i + 1
            name = m.group(1)
            # Find matching closing brace
            j = i + 1
            brace_count = 0
            found_open = False
            while j < n:
                cur = lines[j]
                if "{" in cur:
                    found_open = True
                    brace_count += cur.count("{")
                if "}" in cur:
                    brace_count -= cur.count("}")
                if found_open and brace_count == 0:
                    j += 1
                    break
                j += 1
            units.append((name, start, j))
            i = j
            continue

        # class declaration
        m = re.match(r"^class\s+(\w+)", line)
        if m:
            start = i + 1
            name = m.group(1)
            j = i + 1
            brace_count = 0
            found_open = False
            while j < n:
                cur = lines[j]
                if "{" in cur:
                    found_open = True
                    brace_count += cur.count("{")
                if "}" in cur:
                    brace_count -= cur.count("}")
                if found_open and brace_count == 0:
                    j += 1
                    break
                j += 1
            units.append((name, start, j))
            i = j
            continue

        # const/let/var = function or arrow
        m = re.match(r"^(?:const|let|var)\s+(\w+)\s*=", line)
        if m:
            start = i + 1
            name = m.group(1)
            j = i + 1
            brace_count = 0
            paren_count = 0
            found_open = False
            while j < n:
                cur = lines[j]
                for ch in cur:
                    if ch == "{":
                        found_open = True
                        brace_count += 1
                    elif ch == "}":
                        brace_count -= 1
                    elif ch == "(":
                        paren_count += 1
                    elif ch == ")":
                        paren_count -= 1
                if found_open and brace_count == 0 and paren_count == 0:
                    j += 1
                    break
                j += 1
            units.append((name, start, j))
            i = j
            continue

        i += 1

    return units


def _split_ts(source: str) -> list[tuple[str, int, int]]:
    """Split TypeScript source into function/class/interface/type units."""
    # TypeScript uses same structural patterns as JS plus interfaces/types
    units: list[tuple[str, int, int]] = []
    lines = source.splitlines()
    n = len(lines)

    i = 0
    while i < n:
        line = lines[i].strip()

        # interface
        m = re.match(r"^interface\s+(\w+)", line)
        if m:
            start = i + 1
            name = m.group(1)
            j = i + 1
            brace_count = 0
            found_open = False
            while j < n:
                cur = lines[j]
                if "{" in cur:
                    found_open = True
                    brace_count += cur.count("{")
                if "}" in cur:
                    brace_count -= cur.count("}")
                if found_open and brace_count == 0:
                    j += 1
                    break
                j += 1
            units.append((name, start, j))
            i = j
            continue

        # type alias
        m = re.match(r"^type\s+(\w+)", line)
        if m:
            start = i + 1
            name = m.group(1)
            # Find semicolon or opening brace
            j = i + 1
            while j < n:
                cur = lines[j]
                if ";" in cur and "{" not in cur:
                    j += 1
                    break
                if "{" in cur:
                    brace_count = 0
                    found_open = False
                    while j < n:
                        if "{" in lines[j]:
                            found_open = True
                            brace_count += lines[j].count("{")
                        if "}" in lines[j]:
                            brace_count -= lines[j].count("}")
                        if found_open and brace_count == 0:
                            j += 1
                            break
                        j += 1
                    break
                j += 1
            units.append((name, start, j))
            i = j
            continue

        i += 1

    # Append JS-style units too (functions, classes, const)
    js_units = _split_js(source)
    # Deduplicate by line range
    existing_ranges = {(s, e) for _, s, e in units}
    for name, s, e in js_units:
        if (s, e) not in existing_ranges:
            units.append((name, s, e))
            existing_ranges.add((s, e))

    return sorted(units, key=lambda x: x[1])


# ------------------------------------------------------------------
# Fallback: fixed-size chunking
# ------------------------------------------------------------------

_CHUNK_SIZE = 50


def _chunk_by_size(source: str, block_prefix: str) -> list[dict]:
    """Split source into fixed-size (50-line) chunks."""
    lines = source.splitlines()
    chunks = []
    for start in range(0, len(lines), _CHUNK_SIZE):
        chunk_lines = lines[start:start + _CHUNK_SIZE]
        content = "\n".join(chunk_lines)
        line_start = start + 1  # 1-based
        line_end = min(start + _CHUNK_SIZE, len(lines))
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        chunks.append({
            "block_id": f"{block_prefix}_{start // _CHUNK_SIZE + 1}",
            "block_type": "code_chunk",
            "content": content,
            "page_number": None,
            "table_data": None,
            "source_file_path": None,
            "line_start": line_start,
            "line_end": line_end,
            "content_hash": content_hash,
            "quote": content[:200] + ("..." if len(content) > 200 else ""),
        })
    return chunks


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------


def parse_code(file_path: str) -> dict:
    """Parse a source code file (.py/.js/.ts/.java etc.) into structured blocks.

    1. Try language-specific structural parsing (class/function boundaries).
    2. Fall back to fixed 50-line chunks if no structures found.

    Each block gets: block_id, block_type, content, source_file_path,
    line_start (1-based), line_end (1-based), content_hash, quote.
    """
    import os

    try:
        with open(file_path, encoding="utf-8") as f:
            source = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                source = f.read()
        except Exception as e:
            return {"blocks": [], "error": str(e), "success": False}

    ext = os.path.splitext(file_path)[1].lower()
    name = os.path.basename(file_path)
    source_lines = source.splitlines()

    # Attempt structural parsing
    if ext == ".py":
        units = _split_python(source)
    elif ext in (".js", ".jsx"):
        units = _split_js(source)
    elif ext in (".ts", ".tsx"):
        units = _split_ts(source)
    elif ext in (".java",):
        # Java uses same patterns as JS for class/function
        units = _split_js(source)
    else:
        units = []

    blocks: list[dict] = []
    all_text_parts: list[str] = []
    block_counter = 0

    if units:
        for unit_name, line_start, line_end in units:
            # line_end is exclusive; slice accordingly
            end_idx = line_end - 1 if line_end <= len(source_lines) else len(source_lines)
            chunk_lines = source_lines[line_start - 1:end_idx]
            content = "\n".join(chunk_lines)
            all_text_parts.append(content)
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            block_counter += 1
            blocks.append({
                "block_id": f"code_{block_counter}",
                "block_type": "code_definition",
                "content": content,
                "page_number": None,
                "table_data": None,
                "source_file_path": file_path,
                "line_start": line_start,
                "line_end": line_end,
                "content_hash": content_hash,
                "quote": content[:200] + ("..." if len(content) > 200 else ""),
            })
    else:
        # No structural units found — fall back to fixed-size chunks
        return {
            "blocks": _chunk_by_size(source, "code"),
            "raw_content": source,
            "success": True,
        }

    return {
        "blocks": blocks,
        "raw_content": "\n".join(all_text_parts),
        "success": True,
    }
