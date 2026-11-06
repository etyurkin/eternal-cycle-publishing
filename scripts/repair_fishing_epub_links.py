#!/usr/bin/env python3
"""Versioned technical repair for broken evidence links in Fishing the Stream EPUBs.

Only removes clickable references to evidence deliberately not bundled in the
public reader edition. Does not change manuscript text, cover art, PDF bytes
or private source files. The original v1 remains in Git history and private source.
"""
import json
import re
import tempfile
import zipfile
from pathlib import Path
from hashlib import sha256

ROOT=Path(__file__).resolve().parents[1]
SLUG="fishing-the-stream"
base=ROOT/"books"/"technology"/"other"/SLUG
source_file="EPUB/text/ch028.xhtml"
pattern=re.compile(rb'\s+href=(["\'])evidence/[^"\']+\1')

def repair(path,lang):
    with zipfile.ZipFile(path) as zin:
        names=zin.namelist()
        if source_file not in names:raise ValueError(f"Unsupported EPUB layout: {path}")
        before=zin.read(source_file)
        # Preserve the visible hyperlink label while disarming nonexistent file links.
        message=("Evidence file not bundled in the reader edition; available on request"
                 if lang=="en" else
                 "Файлы подтверждающих материалов не входят в это издание; доступны по запросу")
        after, count=pattern.subn((' title="'+message+'"').encode("utf-8"),before)
        if count<15:raise ValueError(f"Expected 15+ broken evidence links in {path}, found {count}")
        with tempfile.TemporaryDirectory() as td:
            newpath=Path(td)/path.name
            with zipfile.ZipFile(newpath,"w") as zout:
                for info in zin.infolist():
                    data=after if info.filename==source_file else zin.read(info.filename)
                    zout.writestr(info,data)
            with zipfile.ZipFile(newpath) as z:
                if z.testzip() is not None:raise ValueError("Repaired EPUB has broken ZIP CRC")
                if z.namelist()!=names:raise ValueError("EPUB member order altered")
            path.write_bytes(newpath.read_bytes())
    return count

def main():
    doc=json.loads((ROOT/"catalog.json").read_text(encoding="utf-8"))
    book=next(b for b in doc["books"] if b["id"]==SLUG)
    versions={e["version"] for e in book["editions"]}
    if 3 in versions:raise ValueError("Technical revision v3 already exists; do not overwrite")
    for lang in ("en","ru"):
        epub=base/(book["file_stems"][lang]+".epub")
        count=repair(epub,lang)
        print(f"Repaired {count} unavailable evidence links in {lang} EPUB: {epub.name}, sha256={sha256(epub.read_bytes()).hexdigest()}")
    book["editions"].append({
        "version":3,"status":"published","approved_for_publication":True,"year":2026,
        "note_en":"Technical EPUB link repair: missing evidence attachments marked available on request; manuscript text, cover, PDF unchanged",
        "note_ru":"Техническая правка ссылок EPUB: отсутствующие приложения указаны как доступные по запросу; текст, обложка и PDF не изменены",
        "approved_languages":["en","ru"]
    })
    (ROOT/"catalog.json").write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Created approved technical reader revision v3; unchanged mobile PDF files")

if __name__=="__main__":main()
