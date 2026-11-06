import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_gallery import build
from prepare_pages_artifact import prepare, Links, PAGES, REPOSITORY

BASE = '/eternal-cycle-publishing/'


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class PagesArtifactTests(unittest.TestCase):
    def fixture(self, root):
        source, site = root / 'source', root / 'site'
        old, new = 'books/test/Old.pdf', 'books/test/New книга.epub'
        for folder in (source, site):
            (folder / 'books/test').mkdir(parents=True)
            (folder / old).write_bytes(b'%PDF-old')
            (folder / new).write_bytes(b'PK-new')
        (source / 'gallery').mkdir()
        (source / 'gallery/books.json').write_text(json.dumps([{'files': {'pdf': old, 'epub': new}, 'cover': 'assets/covers/unused.png'}]))
        (site / '.nojekyll').touch()
        for rel in PAGES:
            path = site / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('<a href="' + BASE + quote(old) + '">Old</a><a href="' + BASE + quote(new) + '">New</a>')
        config = {'version': 1, 'repository': REPOSITORY, 'revision': 'a' * 40,
                  'preserve_pages': [old],
                  'remote': [{'path': new, 'sha256': hashlib.sha256(b'PK-new').hexdigest()}]}
        return source, site, config, old, new

    def test_complete_current_artifact_preserves_every_existing_reader(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d) / 'site'
            build(ROOT, site, BASE)
            before = hashes(site)
            source_before = {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
                             for rel in before if rel.startswith('books/')}
            config = json.loads((ROOT / 'gallery/pages-downloads.json').read_text())
            result = prepare(ROOT, site)
            after = hashes(site)
            remote = {r['path'] for r in config['remote']}
            covers = {r['path'] for r in config['remote_covers']}
            self.assertEqual(result['preserved_cover_urls'], 26)
            self.assertEqual(result['pinned_remote_covers'], 6)
            self.assertEqual(result['removed_cover_bytes'], 10866467)
            self.assertEqual(result['preserved_reader_urls'], 78)
            self.assertEqual(result['pinned_remote_readers'], 12)
            self.assertEqual(result['removed_binary_bytes'], 28253887)
            self.assertEqual(set(before) - set(after), remote | covers)
            self.assertEqual(len(after), 109)
            for rel in set(after) - set(PAGES):
                self.assertEqual(after[rel], before[rel])
            for rel in config['preserve_pages']:
                self.assertEqual(after[rel], before[rel])
            for rel, digest in source_before.items():
                self.assertEqual(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), digest)
            raw = 'https://raw.githubusercontent.com/' + REPOSITORY + '/' + config['revision'] + '/'
            seen = set()
            for rel in PAGES:
                text = (site / rel).read_text()
                self.assertIn('<span>Eternal Cycle Publishing</span>', text)
                self.assertEqual(text.count('<article '), 17 if rel.startswith('ru/') else 15)
                parser = Links()
                parser.feed(text)
                for url in parser.urls:
                    if url.startswith(raw):
                        path = unquote(url.removeprefix(raw))
                        self.assertIn(path, remote | {'gallery/' + c for c in covers})
                        seen.add(path)
                    elif url.startswith(BASE):
                        path = site / unquote(url.removeprefix(BASE))
                        self.assertTrue(path.exists(), url)
            self.assertEqual(seen, remote | {'gallery/' + c for c in covers})
            self.assertEqual((site / 'index.html').read_bytes(), (site / 'en/index.html').read_bytes())

    def test_invalid_manifest_or_changed_bytes_never_changes_artifact(self):
        for case in ('revision', 'repository', 'hash', 'overlap', 'unknown', 'missing', 'changed', 'legacy', 'no_link'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as d:
                source, site, config, old, new = self.fixture(Path(d))
                if case == 'revision': config['revision'] = 'main'
                if case == 'repository': config['repository'] = 'other/repo'
                if case == 'hash': config['remote'][0]['sha256'] = '0' * 64
                if case == 'overlap': config['preserve_pages'].append(new)
                if case == 'unknown': config['remote'][0]['path'] = 'books/unknown.epub'
                if case == 'missing': (site / new).unlink()
                if case == 'changed': (source / new).write_bytes(b'changed')
                if case == 'legacy': (site / old).write_bytes(b'changed')
                if case == 'no_link':
                    for rel in PAGES: (site / rel).write_text('<html>No reader links</html>')
                before = hashes(site)
                with self.assertRaises(ValueError): prepare(source, site, config)
                self.assertEqual(hashes(site), before)

    def test_cover_validation_fails_before_any_output_changes(self):
        for case in ('hash', 'source', 'legacy', 'overlap', 'unknown', 'missing_link'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as d:
                source, site, config, old, new = self.fixture(Path(d))
                old_cover, new_cover = 'assets/covers/Old.png', 'assets/covers/New.png'
                for root in (source / 'gallery', site):
                    (root / 'assets/covers').mkdir(parents=True)
                    (root / old_cover).write_bytes(b'old cover')
                    (root / new_cover).write_bytes(b'new cover')
                cards = [{'files': {'pdf': old, 'epub': new}, 'cover': c} for c in (old_cover, new_cover)]
                (source / 'gallery/books.json').write_text(json.dumps(cards))
                config['preserve_covers'] = [old_cover]
                config['remote_covers'] = [{'path': new_cover, 'sha256': hashlib.sha256(b'new cover').hexdigest()}]
                for rel in PAGES:
                    path = site / rel
                    path.write_text(path.read_text() + '<img src="' + BASE + new_cover + '">')
                if case == 'hash': config['remote_covers'][0]['sha256'] = '0' * 64
                if case == 'source': (source / 'gallery' / new_cover).write_bytes(b'changed')
                if case == 'legacy': (site / old_cover).write_bytes(b'changed')
                if case == 'overlap': config['preserve_covers'].append(new_cover)
                if case == 'unknown': config['remote_covers'][0]['path'] = 'assets/covers/unknown.png'
                if case == 'missing_link':
                    for rel in PAGES:
                        path = site / rel
                        path.write_text(path.read_text().replace('<img src="' + BASE + new_cover + '">', ''))
                before, source_before = hashes(site), hashes(source)
                with self.assertRaises(ValueError): prepare(source, site, config)
                self.assertEqual(hashes(site), before)
                self.assertEqual(hashes(source), source_before)

    def test_repeat_fails_cleanly_without_touching_source_or_output(self):
        with tempfile.TemporaryDirectory() as d:
            source, site, config, old, new = self.fixture(Path(d))
            source_before = hashes(source)
            prepare(source, site, config)
            before = hashes(site)
            with self.assertRaises(ValueError): prepare(source, site, config)
            self.assertEqual(hashes(site), before)
            self.assertEqual(hashes(source), source_before)

    def test_unsafe_output_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, site, config, old, new = self.fixture(root)
            for target in (source, source / 'books', source / 'gallery', root):
                with self.assertRaises(ValueError): prepare(source, target, config)
            (site / new).unlink()
            (site / new).symlink_to(source / new)
            with self.assertRaises(ValueError): prepare(source, site, config)


if __name__ == '__main__':
    unittest.main()
