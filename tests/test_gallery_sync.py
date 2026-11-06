"""Auto-discovery keeps existing cards and requires explicit cover fallbacks."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_epub_contents import check
from build_gallery import verify_provenance
from catalog_common import load_catalog
from sync_gallery import sync


class GallerySyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.book = dict(id="test-book", category="fiction", series="other",
                         title_en="The Test Book", title_ru="Проверочная книга",
                         note_en="Test", note_ru="Проверка",
                         file_stems={"en": "The Test Book"},
                         gallery_description_en="A hand-approved summary.",
                         editions=[dict(version=1, status="published",
                                        approved_for_publication=True,
                                        approved_languages=["en"], bundle=False)])
        self.catalog = dict(schema=3, language_codes={"en": "English", "ru": "Русский"},
                            categories=[dict(id="fiction", en="Fiction", ru="Проза")],
                            books=[self.book])
        self.save_catalog()
        (self.root / "gallery").mkdir()
        (self.root / "gallery/books.json").write_text("[]\n")
        _, rows = load_catalog(self.root)
        self.row = rows[0]
        self.pdf = self.root / self.row["readers"]["pdf"]
        self.epub = self.root / self.row["readers"]["epub"]
        self.pdf.parent.mkdir(parents=True)
        self.pdf.write_bytes(b"%PDF-1.4\npublic title page\n%%EOF\n")
        self.image = b"\x89PNG\r\n\x1a\n" + b"test-cover"
        self.make_epub()

    def tearDown(self):
        self.temp.cleanup()

    def save_catalog(self):
        (self.root / "catalog.json").write_text(json.dumps(self.catalog), encoding="utf-8")

    def make_epub(self, cover=True):
        with zipfile.ZipFile(self.epub, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>')
            image = '<item id="cover" href="cover.png" media-type="image/png" properties="cover-image"/>' if cover else ""
            archive.writestr("book.opf", '<package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>The Test Book</dc:title><dc:language>en</dc:language></metadata><manifest>' + image + '<item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>')
            archive.writestr("chapter.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>' + ("A readable chapter about an imagined book and its characters. " * 20) + '</p></body></html>')
            if cover:
                archive.writestr("cover.png", self.image)

    def approve_title_page(self):
        self.make_epub(cover=False)
        relative = "assets/covers/test-book-en.png"
        path = self.root / "gallery" / relative
        path.parent.mkdir(parents=True)
        path.write_bytes(self.image)
        self.book["gallery_cover_en"] = dict(
            path=relative, kind="pdf-title-page", pdf=self.row["readers"]["pdf"].as_posix(),
            pdf_sha256=hashlib.sha256(self.pdf.read_bytes()).hexdigest(), page=1,
            sha256=hashlib.sha256(self.image).hexdigest())
        self.save_catalog()

    def test_unbundled_auto_discovery_is_idempotent_and_preserves_readers(self):
        before = (self.pdf.read_bytes(), self.epub.read_bytes())
        cards = sync(self.root)
        self.assertEqual(set(cards[0]["files"]), {"pdf", "epub"})
        self.assertEqual(cards[0]["description"], "A hand-approved summary.")
        self.assertEqual(sync(self.root), cards)
        self.assertEqual(list(self.root.rglob("*.zip")), [])
        self.assertEqual(before, (self.pdf.read_bytes(), self.epub.read_bytes()))

    def test_bundle_default_keeps_zip_link(self):
        del self.book["editions"][0]["bundle"]
        self.save_catalog()
        self.assertEqual(set(sync(self.root)[0]["files"]), {"pdf", "epub", "zip"})

    def test_every_existing_current_card_is_preserved_verbatim(self):
        current = json.loads((ROOT / "gallery/books.json").read_text())
        (self.root / "catalog.json").write_bytes((ROOT / "catalog.json").read_bytes())
        (self.root / "gallery/books.json").write_text(json.dumps(current))
        # Existing cards need no source reads or generated replacements.
        self.assertEqual(sync(self.root), current)

    def test_existing_description_cover_and_provenance_are_not_overwritten(self):
        original = sync(self.root)
        original[0]["description"] = "An edited description."
        original[0]["cover"] = "assets/covers/hand-edited.png"
        original[0]["cover_source"]["editorial_note"] = "Preserve metadata"
        (self.root / "gallery/books.json").write_text(json.dumps(original))
        self.book["gallery_description_en"] = "A different discovery description"
        self.save_catalog()
        self.assertEqual(sync(self.root), original)

    def test_no_cover_without_explicit_approval_is_rejected(self):
        self.make_epub(cover=False)
        with self.assertRaisesRegex(ValueError, "no embedded cover"):
            sync(self.root)

    def test_pdf_title_page_can_be_rediscovered_without_changing_epub(self):
        self.approve_title_page()
        before = self.epub.read_bytes()
        cards = sync(self.root)
        self.assertEqual(cards[0]["cover_source"]["kind"], "pdf-title-page")
        self.assertEqual(cards[0]["description_source"]["chapters"], ["chapter.xhtml"])
        with patch("build_gallery.ROOT", self.root):
            verify_provenance(self.root, cards[0])
        (self.root / "gallery/books.json").write_text("[]")
        self.assertEqual(sync(self.root), cards)
        self.assertEqual(self.epub.read_bytes(), before)
        issues, warnings, _, _ = check(self.epub, "The Test Book", "en", cards[0]["cover_source"])
        self.assertEqual(issues, [])
        self.assertTrue(any("approved PDF title page" in warning for warning in warnings))

    def test_pdf_title_page_tampering_and_unsafe_paths_are_rejected(self):
        self.approve_title_page()
        original = copy.deepcopy(self.book["gallery_cover_en"])
        cases = [("pdf_sha256", "0" * 64, "PDF source hash"),
                 ("sha256", "0" * 64, "asset hash"), ("page", True, "title page 1"),
                 ("path", "assets/covers/../../../secret.png", "Unsafe"),
                 ("pdf", "wrong.pdf", "differs from reader PDF")]
        for field, value, message in cases:
            with self.subTest(field=field):
                self.book["gallery_cover_en"] = {**original, field: value}
                self.save_catalog()
                with self.assertRaisesRegex(ValueError, message):
                    sync(self.root)

    def test_pdf_title_page_requires_catalogue_approval_even_for_existing_card(self):
        self.approve_title_page()
        card = sync(self.root)[0]
        del self.book["gallery_cover_en"]
        self.save_catalog()
        with patch("build_gallery.ROOT", self.root), self.assertRaisesRegex(ValueError, "catalogue approval"):
            verify_provenance(self.root, card)

    def test_pdf_fallback_does_not_hide_broken_or_embedded_epub_cover(self):
        self.approve_title_page()
        self.make_epub(cover=True)
        with self.assertRaisesRegex(ValueError, "only for an EPUB without"):
            sync(self.root)


if __name__ == "__main__":
    unittest.main()
