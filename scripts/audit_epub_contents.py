#!/usr/bin/env python3
"""Inspect every approved public EPUB, including actual book contents, not just ZIP CRC.

Read-only: never rewrites published editions. Reports all failures so repair
can be versioned without silently altering an author's approved master.
"""
from collections import Counter
from pathlib import Path
import json
import posixpath
import sys
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile, BadZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from catalog_common import load_catalog

CONTAINER_NS = "{urn:oasis:names:tc:opendocument:xmlns:container}"
OPF_NS = "{http://www.idpf.org/2007/opf}"
DC_NS = "{http://purl.org/dc/elements/1.1/}"
XHTML_NS = "{http://www.w3.org/1999/xhtml}"

def normpath(base, href):
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        return None
    decoded = unquote(parts.path)
    result = posixpath.normpath(posixpath.join(base, decoded))
    if result.startswith("../") or result in (".", "..") or result.startswith("/"):
        raise ValueError("Unsafe internal EPUB path: " + href)
    return result

def check(epub, title, lang, cover_source):
    issues, warnings = [], []
    with ZipFile(epub) as z:
        infos = z.infolist()
        names = z.namelist()
        nset = set(names)
        if not infos or infos[0].filename != "mimetype":
            issues.append("First EPUB ZIP member is not mimetype")
        elif infos[0].compress_type != 0:
            issues.append("mimetype is compressed (invalid OCF)")
        if len(nset) != len(names):
            issues.append("Duplicate ZIP member names")
        if z.testzip() is not None:
            issues.append("ZIP CRC failure")
        if z.read("mimetype") != b"application/epub+zip":
            issues.append("Invalid EPUB mimetype")
        root = ET.fromstring(z.read("META-INF/container.xml"))
        files = root.findall(".//" + CONTAINER_NS + "rootfile")
        if not files:
            raise ValueError("EPUB rootfile missing")
        opf_path = files[0].attrib.get("full-path")
        if opf_path not in nset:
            raise ValueError("OPF package not in archive: " + str(opf_path))
        opf = ET.fromstring(z.read(opf_path))
        dirpart = posixpath.dirname(opf_path)
        manifest = {}
        pages = []
        page_nodes = []
        for item in opf.findall(".//" + OPF_NS + "manifest/" + OPF_NS + "item"):
            key = item.attrib.get("id")
            href = item.attrib.get("href")
            if not key or not href:
                issues.append("Manifest entry without id or href")
                continue
            path = normpath(dirpart, href)
            if path is None:
                issues.append("Remote manifest item: " + href)
                continue
            manifest[key] = (path, item.attrib.get("media-type", ""), item.attrib.get("properties", ""))
            if path not in nset:
                issues.append("Missing manifest member " + path)
            if item.attrib.get("media-type") == "application/xhtml+xml":
                pages.append(path)
        spine = [i.attrib.get("idref") for i in opf.findall(".//" + OPF_NS + "spine/" + OPF_NS + "itemref")]
        if not spine or any(x not in manifest for x in spine):
            issues.append("Missing or broken reading spine")
        if not pages:
            issues.append("No XHTML reading content")
        langvalues = [x.text for x in opf.iter() if x.tag == DC_NS+"language" and x.text]
        if not langvalues:
            issues.append("No language metadata")
        elif lang.split("-")[0] not in {v.lower().split("-")[0] for v in langvalues}:
            issues.append("Wrong language metadata: " + ", ".join(langvalues))
        titlevalues = [x.text for x in opf.iter() if x.tag == DC_NS+"title" and x.text]
        if not titlevalues:
            issues.append("Missing title metadata")
        elif not any(len(v.strip()) > 2 for v in titlevalues):
            issues.append("Empty title metadata")
        cover = cover_source["member"]
        if cover not in nset:
            issues.append("Gallery-selected cover missing from EPUB: " + cover)
        images = [k for k, (_, mt, _) in manifest.items() if mt.startswith("image/")]
        if not images:
            issues.append("No images declared in EPUB manifest")
        missing_in_xhtml, xhtml_count, nonspace_characters = [], 0, 0
        for path in pages:
            if path not in nset:
                continue
            try:
                node = ET.fromstring(z.read(path))
            except ET.ParseError as ex:
                issues.append("Invalid XHTML "+path+": "+str(ex)[:100])
                continue
            xhtml_count += 1
            text = " ".join((t.strip() for t in node.itertext() if t and t.strip()))
            nonspace_characters += len(text)
            for el in node.iter():
                tag = el.tag.rsplit("}",1)[-1]
                if tag in ("img", "image") and "src" in el.attrib:
                    link = normpath(posixpath.dirname(path), el.attrib["src"])
                    if link and link not in nset: missing_in_xhtml.append(f"{path}: src={el.attrib['src']} => {link}")
                elif tag in ("a", "link") and "href" in el.attrib and urlsplit(el.attrib["href"]).path:
                    link = normpath(posixpath.dirname(path), el.attrib["href"])
                    if link and link not in nset: missing_in_xhtml.append(f"{path}: href={el.attrib['href']} => {link}")
        if missing_in_xhtml:
            issues.append("Broken XHTML links/media: "+", ".join(sorted(set(missing_in_xhtml))[:20]))
        if nonspace_characters < 500:
            issues.append("Reader has too little visible text (" + str(nonspace_characters) + " chars)")
        if xhtml_count != len(pages):
            issues.append("Some XHTML documents could not be parsed")
        navs = [v for v in manifest.values() if "nav" in v[2].split()]
        if not navs:
            warnings.append("No EPUB3 nav manifest property (EPUB2 NCX may exist)")
        named = Path(epub).stem
        if named != title:
            issues.append("File name differs from approved book title: " + named + " vs " + title)
    return issues, warnings, xhtml_count, nonspace_characters

def main():
    catalog, selected = load_catalog(ROOT)
    gallery = json.loads((ROOT/"gallery/books.json").read_text(encoding="utf-8"))
    cover_by = {(b["id"], b["language"]):b["cover_source"] for b in gallery}
    failures=0
    print("READ-ONLY AUDIT of", len(selected), "published EPUB editions")
    for row in selected:
        b=row["book"]; lang=row["language"]; path=ROOT/row["readers"]["epub"]
        try:
            issues, warnings, sections, chars = check(path,b["file_stems"][lang],lang,cover_by[b["id"],lang])
        except Exception as ex:
            issues, warnings, sections, chars = [type(ex).__name__+": "+str(ex)], [], 0, 0
        result="FAIL" if issues else "OK"
        if issues:failures+=1
        print(f"[{result}] {b['id']}/{lang}: {sections} XHTML; {chars} visible chars; {path.stat().st_size} bytes")
        for issue in issues:print("  ERROR:",issue)
        for w in warnings:print("  NOTE:",w)
    print(f"RESULT {len(selected)-failures}/{len(selected)} valid; failures={failures}")
    if failures:sys.exit(1)
if __name__=="__main__":main()
