#!/usr/bin/env python3
"""Verify current readers, ZIP content/hashes, links, and English-first indexes."""
import re
from urllib.parse import unquote, urlparse

from build_catalog import REPO, readme_texts
from catalog_common import ROOT, digest, load_catalog, validate_readers, validate_tree, validate_zip


def verify(root=ROOT):
    catalog, selected = load_catalog(root)
    readers = validate_tree(root, selected, require_zips=True)
    validate_readers(root, selected)
    expected_checks = "\n".join(f"{digest((root / p).read_bytes())}  {p.as_posix()}" for p in sorted(readers)) + "\n"
    if (root / "reader-files.sha256").read_text(encoding="utf-8") != expected_checks:
        raise ValueError("Reader checksum list is missing, stale, or contains unexpected paths")
    for row in selected:
        if row["archive"] is not None:
            validate_zip(root, row)
    expected_targets = {p.as_posix() for row in selected for p in (*row["readers"].values(), row["archive"]) if p is not None}
    total_links = 0
    for path, expected in readme_texts(catalog, selected).items():
        text = (root / path).read_text(encoding="utf-8")
        if text != expected:
            raise ValueError("Catalogue differs from the approved English-first titles: " + str(path))
        seen = []
        for link in re.findall(r"\]\(([^)]+)\)", text):
            url = urlparse(link)
            if url.netloc == "raw.githubusercontent.com":
                prefix = f"/{REPO}/main/"
                if not url.path.startswith(prefix):
                    raise ValueError("Unexpected raw download repository or branch: " + link)
                target = unquote(url.path[len(prefix):])
                if target not in expected_targets or not (root / target).is_file():
                    raise ValueError("Missing or unapproved README link: " + link)
                seen.append(target)
            elif not url.scheme and not link.startswith("#"):
                if not (root / link.split("#", 1)[0]).is_file():
                    raise ValueError("Missing local README link: " + link)
        if set(seen) != expected_targets or len(seen) != len(expected_targets):
            raise ValueError("README must link every current PDF, EPUB and ZIP exactly once: " + str(path))
        total_links += len(seen)
    print(f"Verified {len(readers)} reader containers and hashes, {sum(row['archive'] is not None for row in selected)} ZIPs with CRC/member hashes, and {total_links} current download links across 3 English-first indexes.")


if __name__ == "__main__":
    verify()
