# Preparing reader editions

Keep full-size PDFs, manuscripts and archival source files in the private source repository. This public repository contains only approved mobile PDFs, EPUBs, matching ZIPs and gallery materials.

1. Check the text, translation, illustrations and rights for each language.
2. Prepare the 90 × 160 mm mobile PDF, retaining the approved content and illustrations. Keep the full-size original private.
3. Preserve the existing public folder and localized title. Each language has an adjacent PDF, EPUB and ZIP with the same stem.
4. Update the approved catalog entry, gallery cover and summary, and exact PDF checksums/page counts in `mobile-readers.json`. Do not add drafts or private manuscripts.
5. Run the complete checks below and commit the approved reader files, indexes, checksums and metadata together.

```sh
python -m pip install -r requirements-validation.txt
python scripts/build_catalog.py
python -m unittest discover -s tests -v
python scripts/build_catalog.py --check
python scripts/verify_reader_files.py
python scripts/verify_mobile_readers.py
python scripts/build_gallery.py --output _site
```

The GitHub Actions workflow validates the exact approved mobile files and deploys only the allowlisted `_site` output to GitHub Pages. It does not publish releases or commit generated changes. Do not upload the full source checkout as the Pages artifact.

The legacy private exporter still selects full-size PDFs. Do not run it unchanged against this mobile reader repository. Any future exporter must preserve the mobile-only public boundary.

Free downloads do not grant blanket commercial republication rights.
