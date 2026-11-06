# Mobile reading editions

## Reader files and names

Public PDF files use the approved 90 × 160 mm mobile layout. Full-size PDFs and manuscripts belong in the private source repository, not public branches, tags, releases or ZIPs.

Each current language edition keeps its existing localized title and folder:

```text
books/children/<book-slug>/<Localized title>.pdf
books/children/<book-slug>/<Localized title>.epub
books/children/<book-slug>/<Localized title>.zip
books/<other-category>/<series>/<book-slug>/<Localized title>.pdf
books/<other-category>/<series>/<book-slug>/<Localized title>.epub
books/<other-category>/<series>/<book-slug>/<Localized title>.zip
```

ZIP bundles are optional per edition: `bundle` defaults to `true` and must be a boolean. An edition marked `bundle: false` publishes only PDF and EPUB, with no ZIP file, ZIP link, or bundle release record. The latest approved edition determines this choice independently for each language. Existing enabled bundles are retained unchanged.

Every available ZIP contains exactly the adjacent mobile PDF and EPUB, byte-for-byte. The current download layout has no edition/language subdirectories or separate downloads folder. Filename rules remain catalog schema 3: localized titles, NFC normalization, safe characters and no ambiguous collisions.

The latest approved edition is selected independently for each language. Catalog edition numbers describe the reader edition and may differ from historical cover statements. A mobile layout change must preserve the approved text and illustrations unless a separate editorial change is authorized.

## Approval and validation

Publication requires `status: published`, `approved_for_publication: true`, and explicit `approved_languages`. Each language must have both PDF and EPUB. Drafts and other private material are excluded.

`mobile-readers.json` pins each approved PDF by path, language, SHA-256, byte length, page count and page dimensions. Validation rejects unexpected files, unapproved PDF bytes, non-mobile geometry, mismatched ZIP members and stale generated indexes.

Run all tests and the catalog, reader and mobile checks before publication. Commit current reader files, matching ZIPs where enabled, catalog, gallery metadata, README indexes and checksums together.

## Gallery deployment and archives

GitHub Pages is the reader entrance, with separate Russian and English halls, covers, summaries and direct downloads. The GitHub repository URL remains a code-repository view; the README links readers to the gallery.

The public workflow auto-registers approved mobile PDFs, adds missing gallery cards without replacing existing cards, regenerates the approved catalogues and enabled ZIPs, validates the result and deploys Pages. On main it commits generated changes before deployment; pull requests validate without committing. It does not publish release attachments. Only `_site` is uploaded as the Pages artifact. Private full-size archives are maintained separately.

Do not run the legacy private-source exporter unchanged: it selects full-size PDFs. Any future publishing process must export only the approved mobile reader bytes and pass the public checks.

Cover provenance normally identifies the reader EPUB, its image member and the source image hash. Legacy optimized cover assets need not be byte-identical to that EPUB image. When an EPUB contains no cover image, `kind: pdf-title-page` identifies the matching public PDF, its SHA-256, page 1 and the exact generated cover asset SHA-256. The catalogue must explicitly approve this derivative in `gallery_cover_<language>` with `path`, `kind`, `pdf`, `pdf_sha256`, `page` and `sha256`. The committed cover can then be reused by auto-sync without changing or rendering the reader files. Unknown kinds, missing approvals and altered hashes or page references are rejected. All description sources must identify the same reader EPUB and existing chapter members.

## Rights

© 2026 Evgeniy Tyurkin and credited coauthors. Free downloads do not grant commercial republication rights.

© 2026 Евгений Тюркин и указанные соавторы. Бесплатное скачивание не означает разрешения на коммерческое переиздание.
