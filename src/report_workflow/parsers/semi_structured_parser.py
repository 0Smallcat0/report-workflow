"""Semi-structured parser for PDF, DOCX, TXT files."""
from pathlib import Path
from typing import Any, Optional


def table_to_text(table: list[list[str]]) -> str:
    """Convert table cells into searchable text."""
    rows = []
    for row in table:
        rows.append(" | ".join(str(cell).strip() for cell in row if cell is not None))
    return "\n".join(rows)


def parse_pdf(file_path: str) -> dict:
    """Parse PDF using pdfplumber."""
    try:
        import pdfplumber
        blocks = []
        all_text = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                if text.strip():
                    all_text.append(text)
                    blocks.append({
                        "block_id": f"page_{page_num}",
                        "block_type": "paragraph",
                        "content": text,
                        "page_number": page_num,
                        "table_data": None
                    })
                tables = page.extract_tables()
                for t_idx, table in enumerate(tables):
                    table_text = table_to_text(table)
                    blocks.append({
                        "block_id": f"page_{page_num}_table_{t_idx}",
                        "block_type": "table",
                        "content": table_text,
                        "page_number": page_num,
                        "table_data": table
                    })
                    if table_text:
                        all_text.append(table_text)
        return {
            "blocks": blocks,
            "raw_content": "\n\n".join(all_text),
            "success": True
        }
    except Exception as e:
        return {"blocks": [], "error": str(e), "success": False}


def parse_docx(file_path: str) -> dict:
    """Parse DOCX using python-docx."""
    try:
        from docx import Document
        doc = Document(file_path)
        blocks = []
        all_text = []
        for i, para in enumerate(doc.paragraphs):
            text = para.text.strip()
            if not text:
                continue
            all_text.append(text)
            block_type = "paragraph"
            if para.style.name.startswith("Heading"):
                block_type = "heading"
            blocks.append({
                "block_id": f"para_{i}",
                "block_type": block_type,
                "content": text,
                "page_number": None,
                "table_data": None
            })
        for t_idx, table in enumerate(doc.tables):
            rows = []
            for row in table.rows:
                rows.append([cell.text.strip() for cell in row.cells])
            table_text = table_to_text(rows)
            blocks.append({
                "block_id": f"table_{t_idx}",
                "block_type": "table",
                "content": table_text,
                "page_number": None,
                "table_data": rows
            })
            if table_text:
                all_text.append(table_text)
        return {
            "blocks": blocks,
            "raw_content": "\n\n".join(all_text),
            "success": True
        }
    except Exception as e:
        return {"blocks": [], "error": str(e), "success": False}


def parse_txt(file_path: str) -> dict:
    """Parse TXT file by splitting into heading/paragraph/list/code blocks.

    Adds line_start, line_end, content_hash, source_file_path, and quote metadata
    to every block so evidence can be traced back to exact source locations.
    """
    import hashlib

    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()

        blocks = []
        all_text_parts = []
        block_counter = 0
        i = 0

        while i < len(lines):
            raw_line = lines[i]
            stripped = raw_line.strip()

            # ---------- heading ----------
            if stripped.startswith("#"):
                # Consume all leading heading lines
                heading_texts = []
                while i < len(lines) and lines[i].strip().startswith("#"):
                    heading_texts.append(lines[i].rstrip())
                    all_text_parts.append(lines[i].rstrip())
                    i += 1
                content = "\n".join(heading_texts)
                line_start = i - len(heading_texts) + 1
                line_end = i
                block_counter += 1
                content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                blocks.append({
                    "block_id": f"txt_{block_counter}",
                    "block_type": "heading",
                    "content": content,
                    "page_number": None,
                    "table_data": None,
                    "source_file_path": file_path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "content_hash": content_hash,
                    "quote": content,
                })
                continue

            # ---------- code block ([code] ... [/code] or ``` ```) ----------
            if stripped.startswith("[code]") or stripped.startswith("```"):
                code_lines = []
                code_start = i
                # Consume until closing delimiter
                i += 1
                while i < len(lines):
                    end_marker = lines[i].strip()
                    if end_marker.startswith("[/code]") or end_marker.startswith("```"):
                        i += 1
                        break
                    code_lines.append(lines[i].rstrip())
                    all_text_parts.append(lines[i].rstrip())
                    i += 1
                content = "\n".join(code_lines)
                line_start = code_start + 1
                line_end = i - 1
                block_counter += 1
                content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                blocks.append({
                    "block_id": f"txt_{block_counter}",
                    "block_type": "code_block",
                    "content": content,
                    "page_number": None,
                    "table_data": None,
                    "source_file_path": file_path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "content_hash": content_hash,
                    "quote": content[:200] + ("..." if len(content) > 200 else ""),
                })
                all_text_parts.append(content)
                continue

            # ---------- list item ----------
            if stripped.startswith("- ") or stripped.startswith("* ") or stripped.startswith("+ "):
                list_items = []
                list_start = i
                while i < len(lines) and (
                    lines[i].strip().startswith("- ") or
                    lines[i].strip().startswith("* ") or
                    lines[i].strip().startswith("+ ")
                ):
                    list_items.append(lines[i].rstrip())
                    all_text_parts.append(lines[i].rstrip())
                    i += 1
                content = "\n".join(list_items)
                line_start = list_start + 1
                line_end = i
                block_counter += 1
                content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                blocks.append({
                    "block_id": f"txt_{block_counter}",
                    "block_type": "list_item",
                    "content": content,
                    "page_number": None,
                    "table_data": None,
                    "source_file_path": file_path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "content_hash": content_hash,
                    "quote": content[:200] + ("..." if len(content) > 200 else ""),
                })
                continue

            # ---------- numbered list ----------
            import re as _re
            numbered = _re.compile(r"^\d+[.)]\s").match
            if numbered(stripped):
                num_items = []
                num_start = i
                while i < len(lines) and numbered(lines[i].strip()):
                    num_items.append(lines[i].rstrip())
                    all_text_parts.append(lines[i].rstrip())
                    i += 1
                content = "\n".join(num_items)
                line_start = num_start + 1
                line_end = i
                block_counter += 1
                content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                blocks.append({
                    "block_id": f"txt_{block_counter}",
                    "block_type": "list_item",
                    "content": content,
                    "page_number": None,
                    "table_data": None,
                    "source_file_path": file_path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "content_hash": content_hash,
                    "quote": content[:200] + ("..." if len(content) > 200 else ""),
                })
                continue

            # ---------- blank line ----------
            if not stripped:
                i += 1
                continue

            # ---------- paragraph (collect non-blank lines until blank or heading) ----------
            para_lines = []
            para_start = i
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("#"):
                para_lines.append(lines[i].rstrip())
                all_text_parts.append(lines[i].rstrip())
                i += 1
            if para_lines:
                content = "\n".join(para_lines)
                line_start = para_start + 1
                line_end = i
                block_counter += 1
                content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                blocks.append({
                    "block_id": f"txt_{block_counter}",
                    "block_type": "paragraph",
                    "content": content,
                    "page_number": None,
                    "table_data": None,
                    "source_file_path": file_path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "content_hash": content_hash,
                    "quote": content[:200] + ("..." if len(content) > 200 else ""),
                })

        return {
            "blocks": blocks,
            "raw_content": "\n".join(all_text_parts),
            "success": True,
        }
    except Exception as e:
        return {"blocks": [], "error": str(e), "success": False}


def parse_markdown(file_path: str) -> dict:
    """Parse Markdown file by splitting into heading/paragraph/list/code blocks.

    Adds line_start, line_end, content_hash, source_file_path, and quote metadata
    to every block so evidence can be traced back to exact source locations.
    Markdown headings start with # (like parse_txt for TXT files).
    """
    import hashlib

    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()

        blocks = []
        all_text_parts = []
        block_counter = 0
        i = 0

        while i < len(lines):
            raw_line = lines[i]
            stripped = raw_line.strip()

            # ---------- heading ----------
            if stripped.startswith("#"):
                # Consume all leading heading lines
                heading_texts = []
                while i < len(lines) and lines[i].strip().startswith("#"):
                    heading_texts.append(lines[i].rstrip())
                    all_text_parts.append(lines[i].rstrip())
                    i += 1
                content = "\n".join(heading_texts)
                line_start = i - len(heading_texts) + 1
                line_end = i
                block_counter += 1
                content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                blocks.append({
                    "block_id": f"md_{block_counter}",
                    "block_type": "heading",
                    "content": content,
                    "page_number": None,
                    "table_data": None,
                    "source_file_path": file_path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "content_hash": content_hash,
                    "quote": content,
                })
                continue

            # ---------- code block (``` ``` or [code] [/code]) ----------
            if stripped.startswith("[code]") or stripped.startswith("```"):
                code_lines = []
                code_start = i
                i += 1
                while i < len(lines):
                    end_marker = lines[i].strip()
                    if end_marker.startswith("[/code]") or end_marker.startswith("```"):
                        i += 1
                        break
                    code_lines.append(lines[i].rstrip())
                    all_text_parts.append(lines[i].rstrip())
                    i += 1
                content = "\n".join(code_lines)
                line_start = code_start + 1
                line_end = i - 1
                block_counter += 1
                content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                blocks.append({
                    "block_id": f"md_{block_counter}",
                    "block_type": "code_block",
                    "content": content,
                    "page_number": None,
                    "table_data": None,
                    "source_file_path": file_path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "content_hash": content_hash,
                    "quote": content[:200] + ("..." if len(content) > 200 else ""),
                })
                all_text_parts.append(content)
                continue

            # ---------- list item ----------
            if stripped.startswith("- ") or stripped.startswith("* ") or stripped.startswith("+ "):
                list_items = []
                list_start = i
                while i < len(lines) and (
                    lines[i].strip().startswith("- ") or
                    lines[i].strip().startswith("* ") or
                    lines[i].strip().startswith("+ ")
                ):
                    list_items.append(lines[i].rstrip())
                    all_text_parts.append(lines[i].rstrip())
                    i += 1
                content = "\n".join(list_items)
                line_start = list_start + 1
                line_end = i
                block_counter += 1
                content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                blocks.append({
                    "block_id": f"md_{block_counter}",
                    "block_type": "list_item",
                    "content": content,
                    "page_number": None,
                    "table_data": None,
                    "source_file_path": file_path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "content_hash": content_hash,
                    "quote": content[:200] + ("..." if len(content) > 200 else ""),
                })
                continue

            # ---------- numbered list ----------
            import re as _re
            numbered = _re.compile(r"^\d+[.)]\s").match
            if numbered(stripped):
                num_items = []
                num_start = i
                while i < len(lines) and numbered(lines[i].strip()):
                    num_items.append(lines[i].rstrip())
                    all_text_parts.append(lines[i].rstrip())
                    i += 1
                content = "\n".join(num_items)
                line_start = num_start + 1
                line_end = i
                block_counter += 1
                content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                blocks.append({
                    "block_id": f"md_{block_counter}",
                    "block_type": "list_item",
                    "content": content,
                    "page_number": None,
                    "table_data": None,
                    "source_file_path": file_path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "content_hash": content_hash,
                    "quote": content[:200] + ("..." if len(content) > 200 else ""),
                })
                continue

            # ---------- blank line ----------
            if not stripped:
                i += 1
                continue

            # ---------- paragraph ----------
            para_lines = []
            para_start = i
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("#"):
                para_lines.append(lines[i].rstrip())
                all_text_parts.append(lines[i].rstrip())
                i += 1
            if para_lines:
                content = "\n".join(para_lines)
                line_start = para_start + 1
                line_end = i
                block_counter += 1
                content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                blocks.append({
                    "block_id": f"md_{block_counter}",
                    "block_type": "paragraph",
                    "content": content,
                    "page_number": None,
                    "table_data": None,
                    "source_file_path": file_path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "content_hash": content_hash,
                    "quote": content[:200] + ("..." if len(content) > 200 else ""),
                })

        return {
            "blocks": blocks,
            "raw_content": "\n".join(all_text_parts),
            "success": True,
        }
    except Exception as e:
        return {"blocks": [], "error": str(e), "success": False}


def parse_semi_structured(file_path: str, file_type: str) -> dict:
    """Parse semi-structured file and return content blocks."""
    if file_type == "pdf":
        return parse_pdf(file_path)
    elif file_type == "docx":
        return parse_docx(file_path)
    elif file_type in ("txt", "md"):
        # md is handled by parse_markdown (same block structure as txt)
        return parse_markdown(file_path)
    else:
        return {"blocks": [], "error": f"Unsupported file type: {file_type}", "success": False}
