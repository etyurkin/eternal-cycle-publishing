#!/usr/bin/env python3
"""Build current flat reading downloads, three indexes, and release metadata.

Run locally before committing. --check compares generated files without changing
the public tree; temporary release metadata under dist/ is always refreshed.
"""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote

from catalog_common import ROOT, FORMATS, digest, load_catalog, validate_readers, validate_tree, zip_bytes

REPO = os.environ.get("PUBLIC_REPOSITORY", "etyurkin/eternal-cycle-publishing")
GALLERY = "https://etyurkin.github.io/eternal-cycle-publishing/"
FRONT_DOOR = f"**[Open the book gallery →]({GALLERY}) · [Открыть книжную галерею →]({GALLERY}ru/)**\n\nOriginal covers, short descriptions, and books laid out for reading on your phone.\nОригинальные обложки, короткие описания и книги для чтения с телефона."
INTRO_EN = """# Eternal Cycle Publishing ✨

**Machines are limited. Curiosity is not.**

Eternal Cycle Publishing is an independent bilingual publishing project spanning children’s stories, literary fiction, technology, and explorations of perception. Its creative framework is a **30-month cycle**: imagining, questioning, making, and sharing.

**Founder and publisher:** Evgeniy Tyurkin. Software engineer, writer, musician, and founder of Intent Machines Limited, based in Toronto. [LinkedIn](https://www.linkedin.com/in/etyurkin) · [GitHub](https://github.com/etyurkin).
"""
INTRO_RU = """# Издательство «Вечный цикл» ✨

**Машины ограничены. Любопытство не обязано быть ограниченным.**

«Вечный цикл» — независимое двуязычное издательство: детские сказки, художественная проза, технологии и исследования восприятия. В основе проекта **30-месячный творческий цикл**: придумывать, задавать вопросы, создавать и делиться результатами.

**Основатель и издатель:** Евгений Тюркин. Программист, писатель, музыкант, основатель Intent Machines Limited, живёт в Торонто. [LinkedIn](https://www.linkedin.com/in/etyurkin) · [GitHub](https://github.com/etyurkin).
"""
NAV = "[Home](README.md) · [English](README.en.md) · [Русский](README.ru.md)"
LEGAL_EN = "© 2026 Evgeniy Tyurkin and credited coauthors. Free downloads do not grant commercial republication rights."
LEGAL_RU = "© 2026 Евгений Тюркин и указанные соавторы. Бесплатное скачивание не означает разрешения на коммерческое переиздание."
NOTE_EN = "Fishing the Stream: the research appendix references supporting evidence that is not bundled with the reader files; the text states that evidence is available upon request. The Russian EPUB metadata has been repaired without changing the chapter text."
NOTE_RU = "«Речная рыбалка»: материалы, на которые ссылается исследовательское приложение, не входят в читательские файлы и указаны как доступные по запросу. Метаданные русского EPUB исправлены без изменения текста глав."


def raw_link(path):
    return f"https://raw.githubusercontent.com/{REPO}/main/{quote(path.as_posix(), safe='/')}"


def book_lines(catalog, book, selected, language="en"):
    # English titles always precede Russian, including in the Russian index.
    lines = [f"### {book['title_en']} / {book['title_ru']}", "", book[f"note_{language}"], ""]
    for row in selected:
        if row["book"]["id"] != book["id"]:
            continue
        links = [f"[{ext.upper()}]({raw_link(row['readers'][ext])})" for ext in FORMATS]
        links.append(f"[ZIP]({raw_link(row['archive'])})")
        lang = row["language"]
        label = catalog["language_codes"][lang]
        version = row["edition"]["version"]
        edition_label = f"edition {version}" if language == "en" else f"издание {version}"
        lines.append(f"- **{label} ({lang}) · {edition_label}**: " + " · ".join(links))
    return lines + [""]


def readme_texts(catalog, selected):
    published = {row["book"]["id"] for row in selected}
    books = [book for book in catalog["books"] if book["id"] in published]
    works = len({book.get("work_id", book["id"]) for book in books})
    counts_en = f"{works} works in {len(books)} volumes are available below, including both volumes of Seven Kings. Every listed language edition has PDF, EPUB and a ZIP containing both."
    counts_ru = f"Ниже доступны {works} произведений в {len(books)} томах, включая оба тома «Семи королей». Для каждого указанного языка доступны PDF, EPUB и ZIP с обоими форматами."
    history_en = "These are the approved mobile reading editions. PDF pages use a 90 × 160 mm phone-friendly layout; EPUBs work with reading apps, and each ZIP contains its matching PDF and EPUB. See the [edition policy](EDITION_POLICY.md)."
    history_ru = "Здесь доступны утверждённые мобильные издания. Страницы PDF имеют удобный для телефона размер 90 × 160 мм; EPUB открывается в приложении-читалке, а ZIP содержит соответствующую пару PDF и EPUB. См. [правила публикации](EDITION_POLICY.md)."
    root = ["# Eternal Cycle Publishing · Вечный цикл", "", FRONT_DOOR, "", INTRO_EN.rstrip(), "", NAV, "", "## Download books · Скачать книги", "", counts_en, counts_ru, ""]
    for book in books:
        root.extend(book_lines(catalog, book, selected))
    root.extend(["### Publication notes · Состояние изданий", "", "- " + NOTE_EN, "- " + NOTE_RU, "", history_en, "", LEGAL_EN, "", "---", "", INTRO_RU.rstrip(), "", NAV, "", history_ru, "", LEGAL_RU, ""])
    result = {Path("README.md"): "\n".join(root)}
    for display in ("en", "ru"):
        english = display == "en"
        title = "# Eternal Cycle Publishing · Book Catalogue" if english else "# Издательство «Вечный цикл» · Каталог книг"
        lines = [title, "", FRONT_DOOR, "", NAV, "", counts_en if english else counts_ru, "", history_en if english else history_ru, ""]
        for category in catalog["categories"]:
            grouped = [book for book in books if book["category"] == category["id"]]
            if not grouped:
                continue
            lines.extend(["## " + category[display], ""])
            for book in grouped:
                lines.extend(book_lines(catalog, book, selected, display))
        lines.extend(["---", "", NOTE_EN if english else NOTE_RU, "", LEGAL_EN if english else LEGAL_RU, ""])
        result[Path(f"README.{display}.md")] = "\n".join(lines)
    return result


def file_record(path, data, **extra):
    return dict(path=path.as_posix(), name=path.name, sha256=digest(data), size=len(data), **extra)


def build(root=ROOT, check=False):
    catalog, selected = load_catalog(root)
    validate_tree(root, selected)
    validate_readers(root, selected)
    out = root / "dist"
    if out.is_symlink():
        raise ValueError("Unsafe release output directory")
    out.mkdir(exist_ok=True)
    stale, releases, checks = [], [], []

    def emit(relative, data):
        target = root / relative
        if target.is_symlink():
            raise ValueError("Unsafe generated file: " + str(relative))
        if check:
            if not target.is_file() or target.read_bytes() != data:
                stale.append(relative.as_posix())
        else:
            target.write_bytes(data)

    for row in selected:
        archive_data = zip_bytes(root, row)
        emit(row["archive"], archive_data)
        reader_records = []
        for extension in FORMATS:
            path = row["readers"][extension]
            record = file_record(path, (root / path).read_bytes(), format=extension)
            reader_records.append(record)
            checks.append(f"{record['sha256']}  {path.as_posix()}")
        archive_record = file_record(row["archive"], archive_data)
        checksum_path = Path("dist") / f"{row['archive'].stem}.sha256"
        checksum_data = ("\n".join(f"{r['sha256']}  {r['name']}" for r in reader_records + [archive_record]) + "\n").encode()
        (root / checksum_path).write_bytes(checksum_data)
        checksum_record = file_record(checksum_path, checksum_data)
        releases.append(dict(tag=row["tag"], book_id=row["book"]["id"], edition=row["edition"]["version"],
                             language=row["language"],
                             title=f"{row['book']['title_en']} · Digital edition {row['edition']['version']} · {catalog['language_codes'][row['language']]}",
                             assets=[r["path"] for r in reader_records + [archive_record, checksum_record]],
                             checksums=checksum_path.as_posix(), reader_files=reader_records,
                             zip=archive_record, checksum=checksum_record))
    for path, content in readme_texts(catalog, selected).items():
        emit(path, content.encode("utf-8"))
    emit(Path("reader-files.sha256"), ("\n".join(sorted(checks, key=lambda value: value.split("  ", 1)[1])) + "\n").encode())
    (out / "manifest.json").write_text(json.dumps(dict(schema=3, releases=releases), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if stale:
        raise ValueError("Generated files need rebuilding before commit: " + ", ".join(stale))
    print(f"{'Checked' if check else 'Built'} {len(selected)} language editions, {2 * len(selected)} readers and {len(selected)} adjacent ZIPs.")
    return catalog, selected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if committed generated files differ; never rewrite them")
    build(check=parser.parse_args().check)
