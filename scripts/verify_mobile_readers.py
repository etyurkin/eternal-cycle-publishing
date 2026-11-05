#!/usr/bin/env python3
"""Fail closed unless every public PDF is the exact approved mobile edition."""
import hashlib
import io
import json
import re
from pathlib import Path

from pypdf import PdfReader

from catalog_common import ROOT, load_catalog, validate_tree, validate_zip

FIELDS = {"relative_path", "language", "pages", "pdf_sha256", "bytes", "page_size_mm"}


def load_mobile_manifest(root=ROOT):
    data = json.loads((root / "mobile-readers.json").read_text(encoding="utf-8"))
    if data.get("schema") != 1 or not isinstance(data.get("editions"), list) or not data["editions"]:
        raise ValueError("Invalid approved mobile-reader manifest")
    records = {}
    for item in data["editions"]:
        if set(item) != FIELDS:
            raise ValueError("Unexpected or missing mobile manifest fields")
        path = item["relative_path"]
        if (not isinstance(path, str) or not path.startswith("books/") or not path.endswith(".pdf")
                or "\\" in path or ".." in Path(path).parts or Path(path).is_absolute() or path in records):
            raise ValueError("Unsafe or duplicate approved PDF path")
        if not isinstance(item["language"], str) or not re.fullmatch(r"[a-z]{2,3}", item["language"]):
            raise ValueError("Invalid mobile reader language")
        if any(type(item[key]) is not int or item[key] < 1 for key in ("pages", "bytes")):
            raise ValueError("Invalid mobile reader page or byte count")
        if not isinstance(item["pdf_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["pdf_sha256"]):
            raise ValueError("Invalid approved PDF checksum")
        if item["page_size_mm"] != [90, 160]:
            raise ValueError("Approved mobile pages must be 90 by 160 mm")
        records[path] = item
    return records


def validate_pdf_bytes(data, item):
    name = item["relative_path"]
    if len(data) != item["bytes"]:
        raise ValueError("Mobile PDF byte count mismatch: " + name)
    if hashlib.sha256(data).hexdigest() != item["pdf_sha256"]:
        raise ValueError("Unapproved PDF checksum: " + name)
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted or len(reader.pages) != item["pages"]:
        raise ValueError("Encrypted PDF or unexpected page count: " + name)
    for number, page in enumerate(reader.pages, 1):
        width = float(page.mediabox.width) * 25.4 / 72
        height = float(page.mediabox.height) * 25.4 / 72
        if abs(width - 90) > 0.05 or abs(height - 160) > 0.05 or int(page.get("/Rotate", 0)) % 360:
            raise ValueError(f"Non-mobile page geometry: {name}, page {number}")


def verify(root=ROOT):
    root = Path(root)
    _, selected = load_catalog(root)
    validate_tree(root, selected, require_zips=True)
    records = load_mobile_manifest(root)
    expected = {row["readers"]["pdf"].as_posix(): row for row in selected}
    if set(records) != set(expected):
        raise ValueError("Approved mobile manifest and catalog PDF paths differ")
    total = 0
    for path, row in expected.items():
        item = records[path]
        if item["language"] != row["language"]:
            raise ValueError("Approved mobile reader language mismatch: " + path)
        validate_pdf_bytes((root / path).read_bytes(), item)
        validate_zip(root, row)
        total += item["pages"]
    return len(records), total


if __name__ == "__main__":
    count, pages = verify()
    print(f"Verified {count} approved mobile PDFs, {pages} pages, and matching ZIPs")
