#!/usr/bin/env python3
"""Discover approved books in catalog.json and create missing gallery cards.

Keeps hand-edited existing descriptions and images unchanged. Newly approved
language editions need a mobile PDF, EPUB with a real cover, and catalogue
publication approval. Draft/private material is never shown.
"""
import html
import hashlib
import json
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from catalog_common import ROOT, load_catalog

NS = {"ocf": "urn:oasis:names:tc:opendocument:xmlns:container",
      "opf": "http://www.idpf.org/2007/opf",
      "dc": "http://purl.org/dc/elements/1.1/"}


def safe_epub_member(base, name):
    if not name or name.startswith("/") or "\\" in name:
        raise ValueError("Invalid EPUB member href: " + repr(name))
    parts = urlsplit(name)
    if parts.scheme or parts.netloc:
        raise ValueError("Remote EPUB member: " + repr(name))
    member = posixpath.normpath(posixpath.join(base, unquote(parts.path)))
    if member.startswith("../") or member in (".", "..") or member.startswith("/"):
        raise ValueError("Unsafe EPUB member href: " + repr(name))
    return member


def cover_and_chapters(path):
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        root = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = root.find(".//ocf:rootfile", NS)
        if rootfile is None:
            raise ValueError("Missing EPUB rootfile: " + str(path))
        opf_name = rootfile.attrib["full-path"]
        pkg = ET.fromstring(archive.read(opf_name))
        base = posixpath.dirname(opf_name)
        items = {}
        for item in pkg.findall("./opf:manifest/opf:item", NS):
            if "href" not in item.attrib or "id" not in item.attrib:
                continue
            name = safe_epub_member(base, item.attrib["href"])
            items[item.attrib["id"]] = {
                "name": name,
                "media": item.attrib.get("media-type"),
                "props": item.attrib.get("properties", "").split(),
            }

        # Prefer an EPUB3 cover-image flag, then the EPUB2 cover identifier.
        covers = [x for x in items.values() if "cover-image" in x["props"]]
        if not covers:
            for meta in pkg.findall("./opf:metadata/opf:meta", NS):
                if meta.attrib.get("name") == "cover":
                    candidate = items.get(meta.attrib.get("content"))
                    if candidate:
                        covers = [candidate]
                        break
        if not covers:
            covers = sorted((x for x in items.values()
                             if re.search(r"(?:^|/)(?:cover|frontcover)(?:[_-].*)?\.(?:png|jpe?g)$",
                                          x["name"], re.I)),
                            key=lambda x: len(x["name"]))
        if not covers:
            raise ValueError("Approved EPUB has no embedded cover: " + str(path))
        cover = covers[0]
        name = cover["name"]
        ext = Path(name).suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg") or name not in names:
            raise ValueError("Approved EPUB cover must be an embedded PNG/JPEG: " + str(path))
        cover_bytes = archive.read(name)
        if not cover_bytes.startswith(b"\x89PNG\r\n\x1a\n") and not cover_bytes.startswith(b"\xff\xd8"):
            raise ValueError("Invalid image bytes for EPUB cover: " + name)

        chapters = []
        for spine_ref in pkg.findall("./opf:spine/opf:itemref", NS):
            item = items.get(spine_ref.attrib.get("idref"))
            if not item or item["media"] != "application/xhtml+xml":
                continue
            section = item["name"]
            if section not in names:
                raise ValueError("Missing EPUB spine chapter " + section)
            try:
                doc = ET.fromstring(archive.read(section))
                visible = "".join(doc.itertext()).strip()
            except ET.ParseError as err:
                raise ValueError("Broken EPUB XHTML: " + section) from err
            if len(visible) >= 70 and section not in chapters:
                chapters.append(section)
            if len(chapters) == 3:
                break
        if not chapters:
            raise ValueError("Approved EPUB has no readable chapter: " + str(path))

        description = ""
        for el in pkg.findall("./opf:metadata/dc:description", NS):
            if el.text and el.text.strip():
                description = html.unescape(re.sub(r"<[^>]+>", "", el.text)).strip()
                break
        return name, cover_bytes, chapters, description


def sync(root=ROOT):
    root = Path(root).resolve()
    catalog, rows = load_catalog(root)
    path = root / "gallery/books.json"
    existing = json.loads(path.read_text(encoding="utf-8"))
    by_pair = {}
    for card in existing:
        pair = (card["id"], card["language"])
        if pair in by_pair:
            raise ValueError("Duplicate gallery card: " + str(pair))
        by_pair[pair] = card
    approved = {(r["book"]["id"], r["language"]) for r in rows}
    if set(by_pair) - approved:
        raise ValueError("An existing gallery card is no longer explicitly approved")
    additions = []
    for row in rows:
        book, lang = row["book"], row["language"]
        pair = (book["id"], lang)
        if pair in by_pair:
            continue
        reader_files = {ext: row["readers"][ext].as_posix() for ext in ("pdf", "epub")}
        reader_files["zip"] = row["archive"].as_posix()
        for ext in ("pdf", "epub"):
            candidate = root / reader_files[ext]
            if not candidate.is_file() or candidate.is_symlink():
                raise ValueError("Missing approved reader for gallery: " + str(candidate))
        member, data, chapters, embedded_description = cover_and_chapters(root / reader_files["epub"])
        suffix = ".jpg" if member.lower().endswith((".jpg", ".jpeg")) else ".png"
        cover_rel = "assets/covers/" + book["id"] + "-" + lang + suffix
        cover_path = root / "gallery" / cover_rel
        if cover_path.is_symlink():
            raise ValueError("Unsafe cover output: " + str(cover_path))
        if cover_path.exists():
            if cover_path.read_bytes() != data:
                raise ValueError("Approved cover conflicts with existing file: " + str(cover_path))
        else:
            cover_path.parent.mkdir(parents=True, exist_ok=True)
            cover_path.write_bytes(data)
        description = (book.get("gallery_description_" + lang) or
                       embedded_description or book["note_" + lang])
        description = re.sub(r"\s+", " ", description).strip()
        if not description:
            raise ValueError("Missing book description: " + book["id"])
        card = {
            "id": book["id"],
            "language": lang,
            "title": book["title_" + lang],
            "note": book["note_" + lang],
            "category": book["category"],
            "cover": cover_rel,
            "cover_source": {
                "epub": reader_files["epub"],
                "member": member,
                "sha256": hashlib.sha256(data).hexdigest()
            },
            "files": reader_files,
            "description": description,
            "description_source": {
                "epub": reader_files["epub"],
                "chapters": chapters
            }
        }
        by_pair[pair] = card
        additions.append(pair)
    ordered = [by_pair[(r["book"]["id"], r["language"])] for r in rows]
    if len(ordered) != len(approved):
        raise ValueError("Gallery approval synchronization failed")
    # Existing descriptions, original artwork, and provenance are never overwritten.
    data = json.dumps(ordered, ensure_ascii=False, indent=2) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != data:
        path.write_text(data, encoding="utf-8")
    print("Gallery auto-sync: {} approved editions, {} newly added".format(len(ordered), len(additions)))
    for bid, lang in additions:
        print("  added: {}/{}".format(bid, lang))
    return ordered


if __name__ == "__main__":
    sync()
