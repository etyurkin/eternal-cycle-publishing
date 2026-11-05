#!/usr/bin/env python3
"""Shared validation for the approved, current public reading catalogue."""
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
FORBIDDEN_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
LANG = re.compile(r"[a-z]{2,3}\Z")
FORMATS = ("pdf", "epub")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def localized_stem(title):
    """Keep the localized title, replacing only unsafe filename characters."""
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Missing localized title")
    stem = FORBIDDEN_FILENAME.sub("-", unicodedata.normalize("NFC", title)).strip().rstrip(". ")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    if (not stem or stem in (".", "..") or stem.split(".", 1)[0].upper() in reserved
            or len(stem.encode("utf-8")) > 240
            or any(unicodedata.category(char) in ("Cc", "Cf") for char in stem)):
        raise ValueError("Unsafe localized file stem: " + repr(title))
    return stem


def book_base(book):
    base = Path("books") / book["category"]
    if book["category"] != "children":
        base /= book["series"]
    return base / book["id"]


def load_catalog(root=ROOT):
    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    if catalog.get("schema") != 3:
        raise ValueError("Expected localized-filename catalogue schema 3")
    languages = catalog["language_codes"]
    if not languages or any(not LANG.fullmatch(x) for x in languages):
        raise ValueError("Invalid catalogue language codes")
    categories = catalog["categories"]
    category_ids = [c["id"] for c in categories]
    if len(set(category_ids)) != len(category_ids) or any(not SLUG.fullmatch(c) for c in category_ids):
        raise ValueError("Invalid or duplicate category")
    for c in categories:
        if not all(isinstance(c.get(k), str) and c[k].strip() for k in ("en", "ru")):
            raise ValueError("Missing category title")
    ids, stems, selected = set(), set(), []
    for book in catalog["books"]:
        bid = book["id"]
        if not SLUG.fullmatch(bid) or bid in ids:
            raise ValueError("Invalid or duplicate book ID: " + bid)
        if book["category"] not in category_ids or not SLUG.fullmatch(book["series"]):
            raise ValueError("Invalid category/series: " + bid)
        if not all(isinstance(book.get(k), str) and book[k].strip() for k in ("title_en", "title_ru", "note_en", "note_ru")):
            raise ValueError("Missing bilingual title or note: " + bid)
        ids.add(bid)
        localized = book.get("file_stems")
        if "file_stem" in book or not isinstance(localized, dict) or not localized:
            raise ValueError("Localized file_stems are required: " + bid)
        for language, stem in localized.items():
            if language not in languages or stem != localized_stem(book.get("title_" + language)):
                raise ValueError("File stem must match its localized title: " + bid + "/" + language)
            if stem.casefold() in stems:
                raise ValueError("Invalid or duplicate file stem: " + stem)
            stems.add(stem.casefold())
        versions, latest = set(), {}
        for edition in book["editions"]:
            version = edition["version"]
            if type(version) is not int or version <= 0 or version in versions:
                raise ValueError("Invalid or duplicate edition: " + bid)
            versions.add(version)
            langs = edition.get("approved_languages")
            if not isinstance(langs, list) or any(not isinstance(x, str) or x not in languages for x in langs) or len(langs) != len(set(langs)):
                raise ValueError("Invalid approved language list: " + bid)
            status = edition["status"]
            if status in ("draft", "staged"):
                if edition.get("approved_for_publication") or langs:
                    raise ValueError("Unpublished edition must not be approved: " + bid)
                continue
            if status != "published" or edition.get("approved_for_publication") is not True or not langs:
                raise ValueError("Explicit edition and language approval required: " + bid)
            for language in langs:
                if language not in latest or version > latest[language]["version"]:
                    latest[language] = edition
        if set(localized) != set(latest):
            raise ValueError("Localized file_stems must match approved languages: " + bid)
        for language in languages:
            if language not in latest:
                continue
            edition = latest[language]
            if language not in localized:
                raise ValueError("Missing approved localized file stem: " + bid + "/" + language)
            base = book_base(book)
            name = localized[language]
            selected.append(dict(book=book, edition=edition, language=language, base=base,
                                 readers={ext: base / f"{name}.{ext}" for ext in FORMATS},
                                 archive=base / f"{name}.zip",
                                 tag=f"book-{bid}-v{edition['version']}-{language}"))
    if not selected:
        raise ValueError("No approved reading editions")
    return catalog, selected


def validate_tree(root, selected, require_zips=False):
    """Allow only known flat readers/ZIPs; reject leftovers and symlinks."""
    readers = {p for row in selected for p in row["readers"].values()}
    archives = {row["archive"] for row in selected}
    expected = readers | archives
    allowed_dirs = {p for f in expected for p in f.parents if p != Path(".")}
    books = root / "books"
    if not books.is_dir() or books.is_symlink():
        raise ValueError("Missing or unsafe books directory")
    for path in books.rglob("*"):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise ValueError("Symlink is forbidden: " + relative.as_posix())
        if path.is_dir() and relative not in allowed_dirs:
            raise ValueError("Unexpected/legacy book directory: " + relative.as_posix())
        if path.is_file() and relative not in expected:
            raise ValueError("Unexpected/unapproved public file: " + relative.as_posix())
    for relative in readers | (archives if require_zips else set()):
        if not (root / relative).is_file():
            raise ValueError("Missing approved reader pair or ZIP: " + relative.as_posix())
    if (root / "downloads").exists():
        raise ValueError("Legacy downloads directory must not exist in the current public tree")
    return readers


def validate_readers(root, selected):
    for row in selected:
        pdf = root / row["readers"]["pdf"]
        content = pdf.read_bytes()
        if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-4096:]:
            raise ValueError("Invalid PDF container: " + str(pdf))
        epub = root / row["readers"]["epub"]
        try:
            with zipfile.ZipFile(epub) as archive:
                names = archive.namelist()
                if len(names) != len(set(names)):
                    raise ValueError("Duplicate EPUB members: " + str(epub))
                if archive.read("mimetype") != b"application/epub+zip" or "META-INF/container.xml" not in names:
                    raise ValueError("Invalid EPUB container: " + str(epub))
                bad = archive.testzip()
                if bad:
                    raise ValueError(f"Corrupt EPUB: {epub}: {bad}")
        except (zipfile.BadZipFile, KeyError) as error:
            raise ValueError("Invalid EPUB: " + str(epub)) from error


def zip_bytes(root, row):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for extension in FORMATS:
            path = root / row["readers"][extension]
            info = zipfile.ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
    return output.getvalue()


def validate_zip(root, row):
    path = root / row["archive"]
    try:
        with zipfile.ZipFile(path) as archive:
            expected = [row["readers"][ext].name for ext in FORMATS]
            if archive.namelist() != expected or archive.testzip():
                raise ValueError("Wrong ZIP contents or CRC: " + str(path))
            for extension in FORMATS:
                reader = root / row["readers"][extension]
                if digest(archive.read(reader.name)) != digest(reader.read_bytes()):
                    raise ValueError("ZIP reader content mismatch: " + str(path))
    except zipfile.BadZipFile as error:
        raise ValueError("Invalid ZIP: " + str(path)) from error
