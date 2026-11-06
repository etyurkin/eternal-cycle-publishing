#!/usr/bin/env python3
"""Build only the audited public gallery and exact approved reader files. No dependencies."""
from pathlib import Path
import argparse,json,shutil,html,hashlib,zipfile
from urllib.parse import quote
from catalog_common import load_catalog
ROOT=Path(__file__).resolve().parents[1]
def esc(v):return html.escape(str(v),quote=True)
def safe(root,rel):
 p=Path(rel)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe path: '+rel)
 result=root/p
 if result.is_symlink() or not result.is_file() or not result.resolve().is_relative_to(root.resolve()):raise ValueError('Missing or unsafe file: '+rel)
 return result

def verify_provenance(source,book):
 cover=book['cover_source'];description=book['description_source'];epub=book['files']['epub']
 if description['epub']!=epub:raise ValueError('Gallery provenance differs from reader EPUB')
 if not description['chapters']:raise ValueError('Missing description provenance')
 kind=cover.get('kind','epub')
 if kind=='epub':
  if cover['epub']!=epub:raise ValueError('Gallery provenance differs from reader EPUB')
 elif kind=='pdf-title-page':
  if cover['pdf']!=book['files']['pdf']:raise ValueError('Cover provenance differs from reader PDF')
  if type(cover['page']) is not int or cover['page']!=1:raise ValueError('PDF cover must use title page 1')
  if hashlib.sha256(safe(source,cover['pdf']).read_bytes()).hexdigest()!=cover['pdf_sha256']:raise ValueError('Cover PDF source hash mismatch')
  if hashlib.sha256(safe(ROOT/'gallery',book['cover']).read_bytes()).hexdigest()!=cover['sha256']:raise ValueError('Cover asset hash mismatch')
  _,rows=load_catalog(source)
  row=next((r for r in rows if (r['book']['id'],r['language'])==(book['id'],book['language'])),None)
  if row is None or row['book'].get('gallery_cover_'+book['language'])!={'path':book['cover'],**cover}:raise ValueError('PDF title-page cover lacks matching catalogue approval')
 else:raise ValueError('Unknown cover source kind')
 with zipfile.ZipFile(safe(source,epub)) as archive:
  if kind=='epub' and (cover['member'] not in archive.namelist() or hashlib.sha256(archive.read(cover['member'])).hexdigest()!=cover['sha256']):raise ValueError('Cover source hash mismatch')
  if any(chapter not in archive.namelist() for chapter in description['chapters']):raise ValueError('Missing description source chapter')

def render(lang,books,source,base):
 ru=lang=='ru';label='Русский зал' if ru else 'English hall';title='Книги, к которым<br>хочется вернуться.' if ru else 'Books worth<br>coming back to.'
 intro='Сказки, проза и заметки о технологиях. Выберите обложку и найдите свою историю. Все PDF подготовлены для чтения с телефона.' if ru else 'Fairy tales, prose, and notes on technology. Find a story behind a cover. Every PDF is laid out for reading on your phone.'
 cards=[]
 for i,b in enumerate([b for b in books if b['language']==lang],1):
  links=[]
  for ext,path in b['files'].items():
   size=safe(source,path).stat().st_size/1024/1024
   name=('Читать PDF' if ru else 'Read PDF') if ext=='pdf' else ext.upper()
   links.append(f'<a href="{esc(base+quote(path))}"'+(' download' if ext!='pdf' else '')+f' aria-label="{esc(name+": "+b["title"])}">{name}<small>{size:.1f} MB</small></a>')
  format_note='EPUB — для приложения-читалки' if ru else 'EPUB for your reading app'
  if 'zip' in b['files']:format_note+=' · ZIP — комплект файлов' if ru else ' · ZIP for the file bundle'
  cards.append(f'''<article class="book" id="{esc(b['id'])}"><figure class="frame"><a href="{esc(base+quote(b['files']['pdf']))}" aria-label="{esc(('Читать: ' if ru else 'Read: ')+b['title'])}"><img src="{esc(base+b['cover'])}" alt="{esc(('Обложка: ' if ru else 'Cover: ')+b['title'])}" width="660" height="990" loading="lazy" decoding="async"></a></figure><div><p class="index">{i:02d} / {esc(b['note'])}</p><h3>{esc(b['title'])}</h3><p class="description">{esc(b['description'])}</p><div class="downloads">{''.join(links)}</div><p class="format-note">{format_note}</p></div></article>''')
 return f'''<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{esc(intro)}"><meta name="theme-color" content="#f7f0e5"><title>{label} · Eternal Cycle Publishing</title><link rel="stylesheet" href="{base}assets/gallery.css"><link rel="canonical" href="{base + ('ru/' if ru else '')}"><link rel="alternate" hreflang="en" href="{base}"><link rel="alternate" hreflang="ru" href="{base}ru/"><link rel="alternate" hreflang="x-default" href="{base}"></head><body><a class="skip" href="#collection">{'К книгам' if ru else 'Skip to books'}</a><header><div class="shell masthead"><a class="brand" href="{base}"><span>Eternal Cycle Publishing</span><small>{'Книжная галерея' if ru else 'Book gallery'}</small></a><nav aria-label="{'Язык книг' if ru else 'Book language'}"><a href="{base}" lang="en" {'' if ru else 'aria-current="page"'}>English</a><a href="{base}ru/" lang="ru" {'aria-current="page"' if ru else ''}>Русский</a></nav></div></header><main class="shell"><section class="intro"><div class="eyebrow">{'Открытая книжная галерея' if ru else 'An open book gallery'} · 2026</div><h1>{title}</h1><p>{intro}</p></section><section id="collection" aria-labelledby="hall-title"><div class="hall-bar"><h2 id="hall-title">{label}</h2><span class="count">{len(cards)} {'изданий' if ru else 'editions'} · PDF / EPUB / ZIP</span></div>{''.join(cards)}</section></main><footer><div class="shell"><span>© 2026 {'Евгений Тюркин · Вечный цикл' if ru else 'Evgeniy Tyurkin · Eternal Cycle Publishing'}</span><a href="https://github.com/etyurkin/eternal-cycle-publishing">{'Исходный каталог на GitHub' if ru else 'Source catalogue on GitHub'}</a></div><div class="shell rights">{'Бесплатное скачивание не означает разрешения на коммерческое переиздание.' if ru else 'Free downloads do not grant commercial republication rights.'}</div></footer></body></html>'''

def build(source,output,base):
 source=source.resolve()
 if any(p.is_symlink() for p in (output,*output.parents)):raise ValueError('Symlink output directory')
 output=output.resolve()
 if not base.startswith('/') or not base.endswith('/') or '..' in base or any(x in base for x in ('"',"'",'<','>','?','#','\\')):raise ValueError('Base must be a safe absolute URL path ending in /')
 if output==source or source.is_relative_to(output) or output.is_relative_to(source/'books'):raise ValueError('Unsafe output directory')
 books=json.loads((ROOT/'gallery/books.json').read_text());catalog,selected=load_catalog(source);approved={b['id']:b for b in catalog['books']};latest={(r['book']['id'],r['language']):r for r in selected}
 if not books:raise ValueError('Empty gallery scope')
 pairs=set();copies={'assets/gallery.css':ROOT/'gallery/assets/gallery.css'}
 for b in books:
  pair=(b['id'],b['language'])
  if pair in pairs:raise ValueError('Duplicate gallery edition')
  pairs.add(pair)
  if b['id'] not in approved or b['language'] not in ('ru','en'):raise ValueError('Unapproved gallery edition')
  original=approved[b['id']]
  if pair not in latest:raise ValueError('Unapproved gallery edition')
  if b['title']!=original['title_'+b['language']]:raise ValueError('Gallery title differs from catalogue')
  if not b['description'].strip() or set(b['files'])!=({'pdf','epub','zip'} if latest[pair]['archive'] is not None else {'pdf','epub'}):raise ValueError('Incomplete gallery card')
  folder=Path('books')/original['category']
  if original['category']!='children':folder/=original['series']
  folder/=original['id']
  for ext,rel in b['files'].items():
   if Path(rel)!=folder/(original['file_stems'][b['language']]+'.'+ext):raise ValueError('Gallery reader path differs from catalogue')
   copies[rel]=safe(source,rel)
  if not b['cover'].startswith('assets/covers/') or Path(b['cover']).suffix not in ('.jpg','.png'):raise ValueError('Unexpected cover path')
  verify_provenance(source,b)
  copies[b['cover']]=safe(ROOT/'gallery',b['cover'])
 expected_pairs=set(latest)
 if pairs!=expected_pairs:raise ValueError('Gallery must represent every approved language edition')
 expected=set(copies)|{'index.html','en/index.html','ru/index.html','.nojekyll'}
 if output.exists():
  if any(p.is_symlink() for p in output.rglob('*')):raise ValueError('Symlink inside output')
  extras={str(p.relative_to(output)) for p in output.rglob('*') if p.is_file()}-expected
  if extras:raise ValueError('Output contains non-allowlisted files; use a fresh directory: '+str(sorted(extras)))
 for rel,src in copies.items():
  dest=output/rel;dest.parent.mkdir(parents=True,exist_ok=True)
  if dest.is_symlink():raise ValueError('Symlink output')
  shutil.copyfile(src,dest)
 # Retain /en/ as an English alias for previously shared links.
 for lang,rel in [('en','index.html'),('en','en/index.html'),('ru','ru/index.html')]:
  target=output/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(render(lang,books,source,base),encoding='utf-8')
 (output/'.nojekyll').touch()
 print(f'Built {len(books)} editions / {len({b["id"] for b in books})} volumes; {len(expected)} allowlisted files → {output}')
 return expected
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=ROOT);parser.add_argument('--output',type=Path,default=ROOT/'_site');parser.add_argument('--base',default='/eternal-cycle-publishing/');a=parser.parse_args();build(a.source,a.output,a.base)
