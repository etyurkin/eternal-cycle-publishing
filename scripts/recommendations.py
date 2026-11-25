"""Editorial links are separate from the audited catalogue of hosted books."""
import html
import json
import re
from urllib.parse import urlsplit

PATHS = {'en': 'recommended/', 'ru': 'ru/recommended/'}
CATEGORIES = {
    'fiction': {'en': 'Fiction', 'ru': 'Художественная литература'},
    'technical': {'en': 'Technical reading', 'ru': 'Техническая литература'},
}
COVER_HOSTS = {'images.penguinrandomhouse.com', 'raw.githubusercontent.com', 'media.springernature.com'}
LINK_HOSTS = {'www.penguinrandomhouseretail.com', 'books.apple.com', 'github.com',
              'www.norvig.com', 'link.springer.com'}

def validate_url(value, hosts):
    url = urlsplit(value)
    if (url.scheme != 'https' or url.netloc not in hosts or not url.path.startswith('/')
            or any(ch.isspace() for ch in value)):
        raise ValueError('Unexpected recommendation URL: ' + value)

def localized(entry):
    return all(isinstance(entry.get(lang), str) and entry[lang].strip() for lang in PATHS)

def load(path):
    books = json.loads(path.read_text(encoding='utf-8'))
    ids = set()
    for book in books:
        if (not re.fullmatch('[a-z0-9-]+', book['id']) or book['id'] in ids
                or book['category'] not in CATEGORIES):
            raise ValueError('Invalid recommendation ID or category')
        ids.add(book['id'])
        for field in ('title', 'author', 'description'):
            if not localized(book[field]):
                raise ValueError('Missing recommendation translation: ' + book['id'])
        validate_url(book['cover'], COVER_HOSTS)
        if not book['links']:
            raise ValueError('Missing recommendation source: ' + book['id'])
        for link in book['links']:
            if not localized(link):
                raise ValueError('Missing translated recommendation link')
            validate_url(link['url'], LINK_HOSTS)
    if {book['category'] for book in books} != CATEGORIES.keys():
        raise ValueError('Missing recommendations category')
    return books

def render(lang, books):
    esc = html.escape
    sections = []
    for category, names in CATEGORIES.items():
        cards = []
        for book in (b for b in books if b['category'] == category):
            title = esc(book['title'][lang])
            cover_label = 'Обложка: ' if lang == 'ru' else 'Cover: '
            links = ''.join(f'<a href="{esc(link["url"])}" rel="noreferrer">{esc(link[lang])}</a>'
                            for link in book['links'])
            cards.append(
                f'<article class="book" id="{book["id"]}"><figure class="frame recommendation-cover">'
                f'<img src="{esc(book["cover"])}" alt="{cover_label}{title}" width="200" height="300" '
                f'loading="lazy" decoding="async" referrerpolicy="no-referrer"></figure><div>'
                f'<p class="index">{esc(book["author"][lang])}</p><h3>{title}</h3>'
                f'<p class="description">{esc(book["description"][lang])}</p>'
                f'<div class="downloads">{links}</div></div></article>'
            )
        sections.append(f'<section class="recommendation-shelf" aria-labelledby="{category}">'
                        f'<div class="hall-bar"><h2 id="{category}">{names[lang]}</h2></div>'
                        f'{"".join(cards)}</section>')
    return ''.join(sections)
