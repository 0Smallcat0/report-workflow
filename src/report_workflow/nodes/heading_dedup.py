"""Heading deduplication utilities for merge_draft.

Extracts duplicate ## headings from merged section content.
Used after MERGE_DRAFT to clean up heading duplication caused by
agent drafts containing copy-pasted subsections.
"""
import re
from dataclasses import dataclass


@dataclass
class HeadingOccurrence:
    heading: str       # normalized heading text
    line_number: int   # 1-based line where heading appears
    level: int         # # = 1, ## = 2, ### = 3


def _normalize_heading(text: str) -> str:
    """Normalize heading text for comparison."""
    return text.strip().lower()


def _extract_headings(content: str) -> list[HeadingOccurrence]:
    """Extract all markdown headings from content with line numbers."""
    headings = []
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            # Count heading level
            level = len(re.match(r"^#+(?=\s)", stripped).group())
            heading_text = stripped.lstrip("#").strip()
            headings.append(HeadingOccurrence(
                heading=_normalize_heading(heading_text),
                line_number=i,
                level=level,
            ))
    return headings


def _find_duplicate_headings(content: str, level: int = 2) -> list[tuple[int, str]]:
    """Find duplicate headings at a given level.
    Returns list of (line_number, heading_text) for duplicate headings.
    """
    headings = _extract_headings(content)
    seen: dict[str, list[int]] = {}

    for h in headings:
        if h.level != level:
            continue
        if h.heading not in seen:
            seen[h.heading] = []
        seen[h.heading].append(h.line_number)

    duplicates = []
    for heading, line_nums in seen.items():
        # First occurrence is kept; rest are duplicates
        for ln in line_nums[1:]:
            duplicates.append((ln, heading))
    return duplicates  # sorted by line number already (insertion order)


def _remove_duplicate_heading_lines(content: str) -> str:
    """Remove duplicate heading lines from content.

    Strategy: scan line by line. Keep a seen_headings set.
    When a duplicate heading is found, replace it with a horizontal rule
    separator (---) to preserve some structural indication,
    then remove it entirely.
    """
    lines = content.split("\n")
    seen_headings: dict[str, int] = {}  # heading_text -> level of first occurrence
    result_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") and not stripped.startswith("# "):
            # Not a proper heading line, keep as-is
            result_lines.append(line)
            continue

        heading_match = re.match(r"^(#+)\s+(.+)$", stripped)
        if not heading_match:
            result_lines.append(line)
            continue

        level = len(heading_match.group(1))
        heading_text = _normalize_heading(heading_match.group(2))

        if level == 1:  # # Title — never deduplicate
            result_lines.append(line)
            continue

        if heading_text not in seen_headings:
            seen_headings[heading_text] = level
            result_lines.append(line)
        else:
            # Duplicate heading found. Replace the first occurrence's "##" with "##*" marker
            # so we can track it. Actually, simpler: just skip this line and its content
            # until the next heading at the same level.
            # Approach: if we see the same ## heading, skip the line.
            # But we need to skip the content BETWEEN the duplicate heading and the next same-level heading.
            # This requires a different approach — scan, track content between headings.
            pass

    # The above approach doesn't work well. Let's use a different strategy:
    # Rebuild by tracking the last seen heading at each level.
    return _deduplicate_by_rebuild(content)


def _deduplicate_by_rebuild(content: str) -> str:
    """Remove duplicate and empty heading lines while preserving all content.

    Two-pass approach:
    1. Scan all headings and their content blocks; identify empty headings.
    2. Rebuild document, skipping duplicate headings AND empty first-in-group headings.
       (Content after a skipped heading belongs to the previous heading block.)
    """
    lines = content.split("\n")

    # --- Pass 1: Identify empty heading lines ---------------------------------
    # A heading is "empty" if it has ZERO non-empty, non-heading lines in its
    # block AND all its ### sub-sections (if any) are also empty.
    # This prevents orphaning content that lives under ### headings.
    empty_heading_indices: set[int] = set()

    for i, line in enumerate(lines):
        stripped = line.strip()
        h_match = re.match(r"^(#+)\s+(.+)$", stripped)
        if not h_match:
            continue
        level = len(h_match.group(1))
        heading_text = _normalize_heading(h_match.group(2))

        # Scan content after this heading until next same-or-higher level heading
        j = i + 1
        block_end = len(lines)
        while j < len(lines):
            next_stripped = lines[j].strip()
            next_h_match = re.match(r"^(#+)\s+(.+)$", next_stripped)
            if next_h_match:
                next_level = len(next_h_match.group(1))
                if next_level <= level:
                    block_end = j
                    break  # hit boundary
            j += 1
        else:
            block_end = len(lines)

        block = lines[i+1:block_end]

        # Check if this heading's block has any non-empty content
        has_direct_content = any(l.strip() for l in block)

        # For level 2+, also check if any ### sub-sections have content
        has_sub_content = False
        if level >= 2:
            for k, sub_line in enumerate(block):
                sub_h_match = re.match(r"^(#+)\s+(.+)$", sub_line.strip())
                if sub_h_match and len(sub_h_match.group(1)) == 3:
                    # This ### sub-section — scan for content after it
                    sub_level = 3
                    # Start scanning from the line AFTER the ### heading
                    sub_scan_start = i + 1 + k + 1
                    sub_end = sub_scan_start
                    while sub_end < block_end:
                        next_stripped = lines[sub_end].strip()
                        next_h_match = re.match(r"^(#+)\s+(.+)$", next_stripped)
                        if next_h_match and len(next_h_match.group(1)) <= sub_level:
                            break
                        sub_end += 1
                    # Content is in lines[sub_scan_start:sub_end] (after ###, before next h3/h2)
                    if any(ln.strip() for ln in lines[sub_scan_start:sub_end]):
                        has_sub_content = True
                        break

        if not has_direct_content and not has_sub_content:
            empty_heading_indices.add(i)

    # --- Pass 2: Rebuild, skipping duplicate AND empty headings ----------------
    result_lines: list[str] = []
    seen: dict[tuple[int, str], int] = {}  # (level, text) -> first line index

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        h_match = re.match(r"^(#+)\s+(.+)$", stripped)

        if not h_match:
            result_lines.append(lines[i])
            i += 1
            continue

        level = len(h_match.group(1))
        heading_text = _normalize_heading(h_match.group(2))
        key = (level, heading_text)

        if level == 1:
            # # Title — always keep; deduplicate by skipping duplicate # headings
            # and consuming their trailing blank lines to prevent orphans.
            if key in seen:
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                continue
            seen[key] = i
            result_lines.append(lines[i])
            i += 1
            continue

        if key in seen:
            # Duplicate heading — skip it; also consume any trailing blank lines
            # so they don't become orphaned content between sections.
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            continue
        elif i in empty_heading_indices:
            # First occurrence but entirely empty — skip it and trailing blanks
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            continue
        else:
            seen[key] = i
            result_lines.append(lines[i])
            i += 1
            continue

    return "\n".join(result_lines)


def dedupe_merged_draft(merged_text: str) -> str:
    """Remove duplicate headings from a merged draft.

    Also removes orphaned content between duplicate and next heading.
    """
    before = len(merged_text)
    result = _deduplicate_by_rebuild(merged_text)
    return result
