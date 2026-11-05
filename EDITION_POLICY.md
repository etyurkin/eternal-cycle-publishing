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

Every ZIP contains exactly the adjacent mobile PDF and EPUB, byte-for-byte. The current download layout has no edition/language subdirectories or separate downloads folder. Filename rules remain catalog schema 3: localized titles, NFC normalization, safe characters and no ambiguous collisions.

The latest approved edition is selected independently for each language. Catalog edition numbers describe the reader edition and may differ from historical cover statements. A mobile layout change must preserve the approved text and illustrations unless a separate editorial change is authorized.

## Approval and validation

Publication requires `status: published`, `approved_for_publication: true`, and explicit `approved_languages`. Each language must have both PDF and EPUB. Drafts and other private material are excluded.

`mobile-readers.json` pins each approved PDF by path, language, SHA-256, byte length, page count and page dimensions. Validation rejects unexpected files, unapproved PDF bytes, non-mobile geometry, mismatched ZIP members and stale generated indexes.

Run all tests and the catalog, reader and mobile checks before publication. Commit current reader files, matching ZIPs, catalog, gallery metadata, README indexes and checksums together.

## Gallery deployment and archives

GitHub Pages is the reader entrance, with separate Russian and English halls, covers, summaries and direct downloads. The GitHub repository URL remains a code-repository view; the README links readers to the gallery.

The public workflow validates and deploys Pages only. It does not create or preserve release attachments and does not commit generated changes. Only `_site` is uploaded as the Pages artifact. Private full-size archives are maintained separately.

Do not run the legacy private-source exporter unchanged: it selects full-size PDFs. Any future publishing process must export only the approved mobile reader bytes and pass the public checks.

## Rights

© 2026 Evgeniy Tyurkin and credited coauthors. Free downloads do not grant commercial republication rights.

© 2026 Евгений Тюркин и указанные соавторы. Бесплатное скачивание не означает разрешения на коммерческое переиздание.
