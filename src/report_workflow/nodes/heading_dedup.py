"""Heading deduplication utilities for merge_draft.

Extracts duplicate ## headings from merged section content.
Used after MERGE_DRAFT to clean up heading duplication caused by
agent drafts containing copy-pasted subsections.
"""
import re


def _normalize_heading(text: str) -> str:
    """Normalize heading text for comparison (case-insensitive)."""
    return text.strip().lower()


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
    seen_text: dict[str, int] = {}  # normalized text -> first line index (any level)

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
            seen_text[heading_text] = i
            result_lines.append(lines[i])
            i += 1
            continue

        # Check cross-level duplicate: if this heading's text was already seen
        # at a DIFFERENT level, skip it (e.g. level-2 "Research Questions And
        # Contributions" when level-1 "Research Questions And Contributions" exists).
        if heading_text in seen_text and seen_text[heading_text] != i:
            # Already saw this text at a different level — skip this heading entirely
            # and consume only one trailing blank to avoid double-spacing.
            i += 1
            if i < len(lines) and not lines[i].strip():
                i += 1
            continue

        if key in seen:
            # Duplicate heading at the same level found. If there is substantial
            # content between the first and second occurrence, treat the second
            # heading as a separate section (different content under same heading
            # name = genuinely distinct sections). Only skip the duplicate if it
            # is immediately adjacent to the first with no content in between.
            prev_idx = seen[key]
            first_block_end = prev_idx + 1
            while first_block_end < len(lines) and not lines[first_block_end].strip():
                first_block_end += 1
            has_content_between = first_block_end < i

            if has_content_between:
                # Content exists between two same-level headings with identical text.
                # These are logically distinct sections — keep the duplicate heading
                # so all content is preserved. Just mark it as seen to prevent
                # a third identical heading from being a true duplicate.
                seen[key] = i
                result_lines.append(lines[i])
                i += 1
                continue
            # No content between occurrences — this is a pure duplicate (e.g. an
            # accidental double heading). Skip it and consume only ONE trailing
            # blank so sections don't double-space after merging.
            i += 1
            if i < len(lines) and not lines[i].strip():
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
            seen_text[heading_text] = i
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
