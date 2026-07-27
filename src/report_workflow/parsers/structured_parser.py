"""Structured parser for CSV, XLSX, JSON files."""
import csv
import json
import tomllib


def parse_csv(file_path: str) -> list[dict]:
    """Parse CSV file with the standard library."""
    import io

    from .source_text import read_source_text

    return list(csv.DictReader(io.StringIO(read_source_text(file_path), newline="")))


def parse_xlsx(file_path: str) -> list[dict]:
    """Parse XLSX file using pandas."""
    import pandas as pd
    df = pd.read_excel(file_path)
    return df.to_dict(orient="records")


def parse_json(file_path: str) -> list[dict]:
    """Parse JSON file."""
    from .source_text import read_source_text

    data = json.loads(read_source_text(file_path))
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return [data]
    return []


def parse_toml(file_path: str) -> list[dict]:
    """Parse TOML files such as pyproject.toml."""
    with open(file_path, "rb") as f:
        data = tomllib.load(f)
    if isinstance(data, dict):
        return [data]
    return []


def parse_structured(file_path: str, file_type: str) -> dict:
    """Parse structured file and return content blocks."""
    try:
        if file_type == "csv":
            records = parse_csv(file_path)
        elif file_type == "xlsx":
            records = parse_xlsx(file_path)
        elif file_type == "json":
            records = parse_json(file_path)
        elif file_type == "toml":
            records = parse_toml(file_path)
        else:
            return {"blocks": [], "error": f"Unsupported file type: {file_type}"}

        blocks = []
        content_lines = []
        for i, record in enumerate(records):
            line = json.dumps(record, ensure_ascii=False)
            headers = [str(key) for key in record.keys()]
            values = [str(value) for value in record.values()]
            content_lines.append(line)
            blocks.append({
                "block_id": f"block_{i}",
                "block_type": "table_row",
                "content": line,
                "page_number": None,
                "table_data": [headers, values] if headers or values else None
            })

        return {
            "blocks": blocks,
            "raw_content": "\n".join(content_lines),
            "success": True
        }
    except Exception as e:
        return {"blocks": [], "error": str(e), "success": False}
