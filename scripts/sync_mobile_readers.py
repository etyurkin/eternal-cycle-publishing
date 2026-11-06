#!/usr/bin/env python3
"""Register newly approved phone-size PDF editions in the build-only manifest.

Existing approvals are immutable, new entries require catalog approval and
a 90 x 160 mm unrotated, readable PDF. No publication of private/draft files.
"""
import hashlib
import json
from pathlib import Path
from pypdf import PdfReader
from catalog_common import ROOT, load_catalog

def sync(root=ROOT):
    root=Path(root)
    _,rows=load_catalog(root)
    manifest=root/"mobile-readers.json"
    data=json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("schema")!=1 or not isinstance(data.get("editions"),list):
        raise ValueError("Invalid mobile reader manifest")
    existing={r["relative_path"]:r for r in data["editions"]}
    if len(existing)!=len(data["editions"]):
        raise ValueError("Duplicate pinned mobile PDF")
    expected={r["readers"]["pdf"].as_posix():r for r in rows}
    if set(existing)-set(expected):
        raise ValueError("Mobile PDF approval has been withdrawn; manual review required")
    added=0
    for rel,row in expected.items():
        if rel in existing:
            continue
        path=root/rel
        if not path.is_file() or path.is_symlink():
            raise ValueError("Missing approved mobile PDF: "+rel)
        reader=PdfReader(str(path),strict=True)
        if reader.is_encrypted or not reader.pages:
            raise ValueError("Empty or encrypted mobile PDF: "+rel)
        for number,page in enumerate(reader.pages,1):
            width=float(page.mediabox.width)*25.4/72
            height=float(page.mediabox.height)*25.4/72
            if abs(width-90)>.05 or abs(height-160)>.05 or int(page.get("/Rotate",0))%360:
                raise ValueError(f"PDF is not 90 x 160 mm: {rel}, page {number}")
        blob=path.read_bytes()
        data["editions"].append({
            "relative_path":rel,
            "language":row["language"],
            "pages":len(reader.pages),
            "pdf_sha256":hashlib.sha256(blob).hexdigest(),
            "bytes":len(blob),
            "page_size_mm":[90,160]
        })
        added+=1
    data["editions"].sort(key=lambda x:x["relative_path"])
    manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Mobile reader auto-sync: {len(data['editions'])} approved PDFs, {added} added")
    return data

if __name__=="__main__":
    sync()
