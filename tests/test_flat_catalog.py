"""Regression tests for latest-per-language selection and strict flat outputs."""
import copy
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_catalog import build, raw_link
from catalog_common import load_catalog, localized_stem, validate_tree, validate_zip
from verify_reader_files import verify


class FlatCatalogueTests(unittest.TestCase):
    def test_generated_indexes_keep_gallery_front_door(self):
        from build_catalog import GALLERY, readme_texts
        catalog, rows = load_catalog(self.root)
        for text in readme_texts(catalog, rows).values():
            self.assertIn(GALLERY, text)
            self.assertIn(GALLERY + 'ru/', text)
            self.assertIn('[Open the book gallery →](' + GALLERY + ')', text)
            self.assertLess(text.index('Open the book gallery'), text.index('Открыть книжную галерею'))
            self.assertNotIn('Previous editions remain available', text)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.catalog = dict(schema=3, language_codes={"en": "English", "ru": "Русский"},
                            categories=[dict(id="fiction", en="Fiction", ru="Проза")], books=[
            dict(id="test-book", category="fiction", series="other", file_stems={"en": "The Test Book", "ru": "Проверочная книга"},
                 title_en="The Test Book", title_ru="Проверочная книга", note_en="Test", note_ru="Проверка",
                 editions=[dict(version=1, status="published", approved_for_publication=True,
                                approved_languages=["en", "ru"])])])
        self.save_catalog()
        (self.root / "EDITION_POLICY.md").write_text("Test policy\n")
        _, selected = load_catalog(self.root)
        for row in selected:
            for ext, rel in row["readers"].items():
                p = self.root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                if ext == "pdf":
                    p.write_bytes(b"%PDF-1.4\nreader\n%%EOF\n")
                else:
                    with zipfile.ZipFile(p, "w") as z:
                        z.writestr("mimetype", b"application/epub+zip")
                        z.writestr("META-INF/container.xml", b"<container/>")

    def tearDown(self):
        self.tmp.cleanup()

    def save_catalog(self):
        (self.root / "catalog.json").write_text(json.dumps(self.catalog), encoding="utf-8")

    def test_full_build_verify_and_determinism(self):
        build(self.root)
        verify(self.root)
        original = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        build(self.root, check=True)
        self.assertEqual(original, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        for name in ("README.md", "README.en.md", "README.ru.md"):
            self.assertIn("### The Test Book / Проверочная книга", (self.root / name).read_text())

    def test_latest_selected_per_language_preserves_metadata(self):
        self.catalog["books"][0]["editions"].append(dict(version=2, status="published", approved_for_publication=True, approved_languages=["en"]))
        self.save_catalog()
        c, rows = load_catalog(self.root)
        self.assertEqual({r["language"]: r["edition"]["version"] for r in rows}, {"en": 2, "ru": 1})
        self.assertEqual(len(c["books"][0]["editions"]), 2)
        build(self.root)
        verify(self.root)

    def test_missing_pair_fails(self):
        _, rows = load_catalog(self.root)
        (self.root / rows[0]["readers"]["pdf"]).unlink()
        with self.assertRaisesRegex(ValueError, "Missing approved reader pair"):
            build(self.root)

    def test_legacy_directory_and_downloads_fail(self):
        _, rows = load_catalog(self.root)
        old = self.root / rows[0]["base"] / "editions" / "v1" / "en"
        old.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "legacy book directory"):
            validate_tree(self.root, rows)
        old.rmdir()
        old.parent.rmdir()
        old.parent.parent.rmdir()
        (self.root / "downloads").mkdir()
        with self.assertRaisesRegex(ValueError, "Legacy downloads"):
            validate_tree(self.root, rows)

    def test_unexpected_or_unapproved_language_fails(self):
        _, rows = load_catalog(self.root)
        (self.root / rows[0]["base"] / "The_Test_Book_fr.pdf").write_bytes(b"test")
        with self.assertRaisesRegex(ValueError, "Unexpected/unapproved"):
            build(self.root)

    def test_duplicate_stems_fail(self):
        other = copy.deepcopy(self.catalog["books"][0])
        other["id"] = "second-book"
        other["title_en"] = "the test book"
        other["file_stems"]["en"] = "the test book"
        self.catalog["books"].append(other)
        self.save_catalog()
        with self.assertRaisesRegex(ValueError, "duplicate file stem"):
            load_catalog(self.root)

    def test_zip_members_must_match_descriptive_reader_names(self):
        build(self.root)
        _, rows = load_catalog(self.root)
        with zipfile.ZipFile(self.root / rows[0]["archive"], "w") as archive:
            archive.writestr("book.pdf", b"wrong")
            archive.writestr("book.epub", b"wrong")
        with self.assertRaisesRegex(ValueError, "Wrong ZIP contents"):
            validate_zip(self.root, rows[0])

    def test_localized_filenames_preserve_spaces_and_cyrillic(self):
        _, rows = load_catalog(self.root)
        names = {row["language"]: row["readers"]["pdf"].name for row in rows}
        self.assertEqual(names, {"en": "The Test Book.pdf", "ru": "Проверочная книга.pdf"})
        self.assertTrue(all(row["archive"].stem == self.catalog["books"][0]["file_stems"][row["language"]]
                            for row in rows))

    def test_russian_zip_names_are_utf8_and_metadata_is_deterministic(self):
        build(self.root)
        _, rows = load_catalog(self.root)
        row = next(row for row in rows if row["language"] == "ru")
        with zipfile.ZipFile(self.root / row["archive"]) as archive:
            self.assertEqual(archive.namelist(), ["Проверочная книга.pdf", "Проверочная книга.epub"])
            for info in archive.infolist():
                self.assertTrue(info.flag_bits & 0x800)
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED)
                self.assertEqual(info.external_attr, 0o644 << 16)

    def test_links_encode_spaces_unicode_and_punctuation(self):
        from urllib.parse import unquote, urlparse
        path = Path("books/children/test-book/Семь королей · Все нити.pdf")
        link = raw_link(path)
        self.assertIn("%20", link)
        self.assertIn("%D0%A1", link)
        self.assertIn("%C2%B7", link)
        self.assertTrue(unquote(urlparse(link).path).endswith(path.as_posix()))
        self.assertNotIn(" ", link)

    def test_children_omit_series_but_other_categories_retain_it(self):
        self.catalog["categories"].append(dict(id="children", en="Children", ru="Детские"))
        self.catalog["books"][0]["category"] = "children"
        self.catalog["books"][0]["series"] = "cafe-de-la-luna"
        self.save_catalog()
        _, rows = load_catalog(self.root)
        self.assertEqual(rows[0]["base"], Path("books/children/test-book"))
        self.catalog["books"][0]["category"] = "fiction"
        self.save_catalog()
        _, rows = load_catalog(self.root)
        self.assertEqual(rows[0]["base"], Path("books/fiction/cafe-de-la-luna/test-book"))

    def test_old_children_series_directory_is_rejected(self):
        self.catalog["categories"].append(dict(id="children", en="Children", ru="Детские"))
        self.catalog["books"][0]["category"] = "children"
        self.save_catalog()
        _, rows = load_catalog(self.root)
        (self.root / "books/children/cafe-de-la-luna/test-book").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "legacy book directory"):
            validate_tree(self.root, rows)

    def test_minimal_filename_sanitization_and_nfc(self):
        self.assertEqual(localized_stem("  Café / Questions: Why?  "), "Café - Questions- Why-")
        self.assertEqual(localized_stem("Cafe\u0301 · A Writer’s Book"), "Café · A Writer’s Book")
        self.assertEqual(localized_stem("Title... "), "Title")
        for name in (".", "..", "CON", "nul.txt", "a\u200db", "a" * 241):
            with self.subTest(name=name), self.assertRaises(ValueError):
                localized_stem(name)

    def test_stems_must_be_derived_from_localized_titles(self):
        self.catalog["books"][0]["file_stems"]["ru"] = "The_Test_Book_ru"
        self.save_catalog()
        with self.assertRaisesRegex(ValueError, "localized title"):
            load_catalog(self.root)

    def test_same_title_in_two_languages_is_rejected_not_suffixed(self):
        book = self.catalog["books"][0]
        book["title_ru"] = book["title_en"]
        book["file_stems"]["ru"] = book["file_stems"]["en"]
        self.save_catalog()
        with self.assertRaisesRegex(ValueError, "duplicate file stem"):
            load_catalog(self.root)

    def test_normalized_unicode_collision_is_rejected(self):
        book = self.catalog["books"][0]
        book["title_en"] = "Café"
        book["file_stems"]["en"] = "Café"
        other = copy.deepcopy(book)
        other["id"] = "second-book"
        other["title_en"] = "Cafe\u0301"
        other["file_stems"]["en"] = "Café"
        self.catalog["books"].append(other)
        self.save_catalog()
        with self.assertRaisesRegex(ValueError, "duplicate file stem"):
            load_catalog(self.root)

    def test_future_spanish_title_needs_no_language_suffix(self):
        self.catalog["language_codes"]["es"] = "Español"
        book = self.catalog["books"][0]
        book["title_es"] = "El libro de prueba"
        book["file_stems"]["es"] = "El libro de prueba"
        book["editions"][0]["approved_languages"].append("es")
        self.save_catalog()
        _, rows = load_catalog(self.root)
        row = next(row for row in rows if row["language"] == "es")
        self.assertEqual(row["readers"]["pdf"].name, "El libro de prueba.pdf")

    def test_missing_approved_localized_stem_is_rejected(self):
        del self.catalog["books"][0]["file_stems"]["ru"]
        self.save_catalog()
        with self.assertRaisesRegex(ValueError, "match approved languages"):
            load_catalog(self.root)

    def test_unapproved_file_stems_are_rejected(self):
        self.catalog["language_codes"]["es"] = "Español"
        book = self.catalog["books"][0]
        book["title_es"] = "El libro de prueba"
        book["file_stems"]["es"] = "El libro de prueba"
        self.save_catalog()
        with self.assertRaisesRegex(ValueError, "match approved languages"):
            load_catalog(self.root)

    def test_zip_members_must_match_reader_hashes(self):
        build(self.root)
        _, rows = load_catalog(self.root)
        with zipfile.ZipFile(self.root / rows[0]["archive"], "w") as archive:
            for p in rows[0]["readers"].values():
                archive.writestr(p.name, b"wrong")
        with self.assertRaisesRegex(ValueError, "ZIP reader content mismatch"):
            validate_zip(self.root, rows[0])

    def test_check_detects_readme_drift_without_repairing_it(self):
        build(self.root)
        path = self.root / "README.ru.md"
        path.write_text(path.read_text().replace("The Test Book / Проверочная книга", "Проверочная книга / The Test Book"))
        old = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "need rebuilding"):
            build(self.root, check=True)
        self.assertEqual(path.read_bytes(), old)

    def test_checksum_mismatch_fails(self):
        build(self.root)
        path = self.root / "reader-files.sha256"
        path.write_text(path.read_text().replace("  books/", "  old/", 1))
        with self.assertRaisesRegex(ValueError, "checksum list"):
            verify(self.root)

    def test_unapproved_editions_not_selected(self):
        self.catalog["books"][0]["editions"].append(dict(version=2, status="draft", approved_for_publication=False, approved_languages=[]))
        self.save_catalog()
        _, rows = load_catalog(self.root)
        self.assertTrue(all(r["edition"]["version"] == 1 for r in rows))

    def test_symlink_fails(self):
        _, rows = load_catalog(self.root)
        reader = self.root / rows[0]["readers"]["pdf"]
        reader.unlink()
        reader.symlink_to(self.root / "catalog.json")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            build(self.root)


if __name__ == "__main__":
    unittest.main()
