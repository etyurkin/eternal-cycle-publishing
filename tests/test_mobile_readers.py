import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_mobile_readers import load_mobile_manifest, validate_pdf_bytes


class MobileReaderGuardTests(unittest.TestCase):
    def sample(self, width=90, height=160):
        writer = PdfWriter()
        writer.add_blank_page(width=width * 72 / 25.4, height=height * 72 / 25.4)
        out = io.BytesIO()
        writer.write(out)
        data = out.getvalue()
        item = {"relative_path": "books/fiction/story/book.pdf", "language": "en", "pages": 1,
                "pdf_sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "page_size_mm": [90, 160]}
        return data, item

    def test_approved_mobile_pdf(self):
        data, item = self.sample()
        validate_pdf_bytes(data, item)

    def test_changed_pdf_rejected(self):
        data, item = self.sample()
        item["pdf_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "checksum"):
            validate_pdf_bytes(data, item)

    def test_changed_size_rejected(self):
        data, item = self.sample()
        item["bytes"] += 1
        with self.assertRaisesRegex(ValueError, "byte count"):
            validate_pdf_bytes(data, item)

    def test_wrong_page_count_rejected(self):
        data, item = self.sample()
        item["pages"] = 2
        with self.assertRaisesRegex(ValueError, "page count"):
            validate_pdf_bytes(data, item)

    def test_full_size_pdf_rejected(self):
        data, item = self.sample(148, 210)
        with self.assertRaisesRegex(ValueError, "geometry"):
            validate_pdf_bytes(data, item)

    def test_duplicate_manifest_path_rejected(self):
        _, item = self.sample()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "mobile-readers.json").write_text(json.dumps({"schema": 1, "editions": [item, item]}))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_mobile_manifest(root)
