#!/usr/bin/env python3
"""Trim explicitly pinned new readers and covers from a freshly built Pages artifact.

Existing Pages reader URLs remain real binary files. Source books are never
modified. Raw GitHub uses a generic MIME type, so new PDFs may download instead
of opening inline. Update the explicit revision/hash pins after changing one
of these readers; a mismatch stops publication rather than linking stale bytes.
"""
import argparse
import hashlib
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'etyurkin/eternal-cycle-publishing'
PAGES = ('index.html', 'en/index.html', 'ru/index.html')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_file(root, relative):
    path = Path(relative)
    target = root / path
    if (path.is_absolute() or '..' in path.parts or '\\' in relative
            or target.is_symlink() or not target.is_file()
            or not target.resolve().is_relative_to(root.resolve())):
        raise ValueError('Missing or unsafe artifact file: ' + relative)
    return target


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        self.urls.extend(value for key, value in attrs if key in ('href', 'src'))


def prepare(source, site, manifest=None, base='/eternal-cycle-publishing/'):
    source, site = Path(source).resolve(), Path(site)
    if any(p.is_symlink() for p in (site, *site.parents)):
        raise ValueError('Symlink artifact directory')
    site = site.resolve()
    if (site == source or source.is_relative_to(site)
            or any(site.is_relative_to(source / p) for p in ('books', 'gallery', 'scripts', 'tests', '.github', '.git'))):
        raise ValueError('Unsafe artifact directory')
    if not base.startswith('/') or not base.endswith('/') or any(c in base for c in ('..', '?', '#', '\\', '"', "'", '<', '>')):
        raise ValueError('Unsafe Pages base')
    checked_file(site, '.nojekyll')
    config = json.loads((source / 'gallery/pages-downloads.json').read_text()) if manifest is None else manifest
    if config['version'] != 1 or config['repository'] != REPOSITORY or not re.fullmatch('[0-9a-f]{40}', config['revision']):
        raise ValueError('Invalid immutable GitHub target')
    legacy = config['preserve_pages']
    remote = {item['path']: item['sha256'] for item in config['remote']}
    legacy_covers = config.get('preserve_covers', [])
    cover_entries = config.get('remote_covers', [])
    remote_covers = {item['path']: item['sha256'] for item in cover_entries}
    if (len(legacy_covers) != len(set(legacy_covers)) or len(remote_covers) != len(cover_entries)
            or set(legacy_covers) & remote_covers.keys()):
        raise ValueError('Duplicate or overlapping cover scope')
    if (not legacy or not remote or len(legacy) != len(set(legacy))
            or len(remote) != len(config['remote']) or set(legacy) & remote.keys()):
        raise ValueError('Duplicate, empty, or overlapping reader scope')
    cards = json.loads((source / 'gallery/books.json').read_text())
    approved = {path for card in cards for path in card['files'].values()}
    approved_covers = {card['cover'] for card in cards}
    for rel in [*legacy_covers, *remote_covers]:
        if (rel not in approved_covers or not rel.startswith('assets/covers/')
                or Path(rel).suffix not in ('.png', '.jpg')):
            raise ValueError('Cover is not in the approved gallery')
    for rel in legacy_covers:
        if digest(checked_file(site, rel)) != digest(checked_file(source / 'gallery', rel)):
            raise ValueError('Protected cover differs from source: ' + rel)
    if not set(remote).issubset(approved):
        raise ValueError('Remote reader is not in the approved gallery')
    for rel in legacy:
        if not rel.startswith('books/') or Path(rel).suffix not in ('.pdf', '.epub', '.zip'):
            raise ValueError('Invalid protected reader path')
        if digest(checked_file(site, rel)) != digest(checked_file(source, rel)):
            raise ValueError('Protected reader differs from source: ' + rel)
    raw = 'https://raw.githubusercontent.com/' + REPOSITORY + '/' + config['revision'] + '/'
    replacements = {}
    for rel, expected in remote.items():
        if not rel.startswith('books/') or Path(rel).suffix not in ('.pdf', '.epub') or not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('Invalid pinned reader')
        if digest(checked_file(source, rel)) != expected or digest(checked_file(site, rel)) != expected:
            raise ValueError('Pinned reader hash mismatch: ' + rel)
        replacements[base + quote(rel)] = raw + quote(rel)
    for rel, expected in remote_covers.items():
        if not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('Invalid pinned cover')
        if digest(checked_file(source / 'gallery', rel)) != expected or digest(checked_file(site, rel)) != expected:
            raise ValueError('Pinned cover hash mismatch: ' + rel)
        replacements[base + quote(rel)] = raw + quote('gallery/' + rel)
    omitted = set(remote) | set(remote_covers)
    pages = {}
    seen = set()
    for rel in PAGES:
        content = checked_file(site, rel).read_text()
        parser = Links()
        parser.feed(content)
        for url in parser.urls:
            if url in replacements:
                seen.add(url)
                for attribute in ('href', 'src'):
                    content = content.replace(attribute + '="' + html.escape(url, quote=True) + '"',
                                              attribute + '="' + html.escape(replacements[url], quote=True) + '"')
        parser = Links()
        parser.feed(content)
        for url in parser.urls:
            if url in replacements:
                raise ValueError('Reader link was not rewritten')
            if url.startswith(raw) and url not in replacements.values():
                raise ValueError('Unexpected pinned reader link')
            if url.startswith(base):
                local = unquote(urlsplit(url).path[len(base):])
                target = site / local
                if target.is_dir():
                    local = str(Path(local) / 'index.html')
                checked_file(site, local)
                if local in omitted:
                    raise ValueError('Local link still needs an omitted reader')
        pages[rel] = content
    if seen != set(replacements):
        raise ValueError('A pinned reader is missing its gallery link')
    # All validation above finishes before any output is changed. Only these
    # derived HTML files and explicitly allowlisted artifact copies are touched.
    for rel, content in pages.items():
        (site / rel).write_text(content, encoding='utf-8')
    removed_bytes = sum((site / rel).stat().st_size for rel in remote)
    removed_cover_bytes = sum((site / rel).stat().st_size for rel in remote_covers)
    for rel in omitted:
        (site / rel).unlink()
    # Remove only empty directories left by these omitted artifact copies.
    parents = {parent for rel in omitted for parent in (site / rel).parents
               if parent != site and parent.is_relative_to(site)}
    for parent in sorted(parents, key=lambda p: len(p.parts), reverse=True):
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    for rel in legacy:
        if digest(site / rel) != digest(source / rel):
            raise ValueError('Protected reader changed during preparation')
    for rel in legacy_covers:
        if digest(site / rel) != digest(source / 'gallery' / rel):
            raise ValueError('Protected cover changed during preparation')
    result = {'preserved_reader_urls': len(legacy), 'pinned_remote_readers': len(remote),
              'preserved_cover_urls': len(legacy_covers), 'pinned_remote_covers': len(remote_covers),
              'removed_cover_bytes': removed_cover_bytes,
              'removed_binary_bytes': removed_bytes, 'revision': config['revision']}
    print(json.dumps(result, sort_keys=True))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--base', default='/eternal-cycle-publishing/')
    args = parser.parse_args()
    prepare(args.source, args.site, base=args.base)
