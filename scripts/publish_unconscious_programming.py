#!/usr/bin/env python3
"""Publish Unconscious Programming RU/EN as validated 90 x 160 mm mobile readers."""
import hashlib, io, json, subprocess, tempfile, zipfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from weasyprint import CSS, HTML

ROOT=Path(__file__).resolve().parents[1]
SLUG='unconscious-programming'
DIR=Path('books/technology/other')/SLUG
COV=Path('gallery/assets/covers')
BOOK={'id':SLUG,'category':'technology','series':'other',
      'title_en':'Unconscious Programming','title_ru':'Бессознательное программирование',
      'note_en':'Café de la Luna · Research Series · Book I',
      'note_ru':'Café de la Luna · Исследовательская серия · Книга I',
      'file_stems':{'en':'Unconscious Programming','ru':'Бессознательное программирование'},
      'editions':[{'version':1,'status':'published','approved_for_publication':True,
                   'year':2026,'note_en':'Bilingual research edition',
                   'note_ru':'Двуязычное исследовательское издание',
                   'approved_languages':['en','ru']}]}
DESC={'en':'An inquiry into what experienced programmers acquire beyond syntax: tacit knowledge, intuition, collaboration with AI, and the ability to sense when a question is wrong.',
      'ru':'Исследование того, что приобретают опытные программисты за пределами синтаксиса: неявного знания, интуиции, сотрудничества с ИИ и умения почувствовать неверный вопрос.'}
CSS_PRINT="""
@page{size:90mm 160mm;margin:12mm 10.5mm 13mm 10.5mm;
 @bottom-center{content:counter(page);font-family:'DejaVu Sans';font-size:8pt;color:#777}}
@page:first{@bottom-center{content:none}}
html,body{font-family:'DejaVu Serif',serif!important;font-size:10.3pt!important;line-height:1.43!important;color:#222!important}
body{margin:0!important}
p{margin:0 0 .65em!important;text-align:left!important;orphans:3;widows:3;overflow-wrap:break-word}
h1,h2,h3,h4,h5{font-family:'DejaVu Sans',sans-serif!important;break-after:avoid!important;line-height:1.28;margin:1.15em 0 .5em}
h1{font-size:17pt!important}h2{font-size:13pt!important}h3{font-size:11.8pt!important}h4{font-size:10.6pt!important}
.title{text-align:center;break-after:page;padding-top:20mm}.title p{text-align:center!important}
.title h1{font-size:16pt!important}
blockquote{border-left:2px solid #888;margin:3mm 0;padding-left:3mm}
pre{font-family:'DejaVu Sans Mono';font-size:7pt;white-space:pre-wrap;overflow-wrap:anywhere}
code{font-family:'DejaVu Sans Mono'}hr{border:0;border-top:1px solid #aaa;margin:5mm 0}
"""

def font(n,bold=False):
 p='/usr/share/fonts/truetype/dejavu/DejaVuSerif'+('-Bold' if bold else '')+'.ttf'
 return ImageFont.truetype(p,n)

def cover(lang):
 im=Image.new('RGB',(660,990),'#15202e'); d=ImageDraw.Draw(im)
 for y in range(990):
  f=y/990;d.line((0,y,660,y),fill=(int(21+21*f),int(30+15*f),int(46+20*f)))
 d.ellipse((452,96,562,206),fill='#e7d4a0');d.ellipse((474,83,576,186),fill='#192337')
 for x,y in [(68,98),(169,168),(327,86),(568,312),(82,368),(388,278),(570,512)]:
  d.ellipse((x-2,y-2,x+2,y+2),fill='#e9d8ad')
 d.line((54,392,606,392),fill='#9e8c68',width=2)
 d.text((57,45),'CAFÉ DE LA LUNA',font=font(19,True),fill='#dfcfa7')
 d.text((57,74),'RESEARCH SERIES · I',font=font(15),fill='#c1baa9')
 lines=['Unconscious','Programming'] if lang=='en' else ['Бессознательное','программирование']
 for i,t in enumerate(lines):
  d.text((55,430+i*84),t,font=font(39 if len(t)>17 else 49,True),fill='#f4eada')
 subtitle='Twenty Years Later' if lang=='en' else 'Двадцать лет спустя'
 who='Evgeniy Tyurkin · Grok · Sol' if lang=='en' else 'Евгений Тюркин · Грок · Sol'
 d.text((57,631),subtitle,font=font(27),fill='#e5d2a9')
 d.line((54,707,606,707),fill='#9e8c68',width=2)
 d.text((57,760),who,font=font(17),fill='#f1e6d7')
 d.text((57,885),'ETERNAL CYCLE PUBLISHING',font=font(18,True),fill='#e5d2a9')
 d.text((57,917),'2026 · Krasnoyarsk · 1979',font=font(17),fill='#e5d2a9')
 o=io.BytesIO();im.save(o,format='PNG',optimize=True);return o.getvalue()

def cover_epub(path,image):
 with zipfile.ZipFile(path) as z:
  files={name:z.read(name) for name in z.namelist()}
 assert files['mimetype']==b'application/epub+zip'
 opf=files['EPUB/package.opf'].decode('utf8')
 if '<item id="cover"' not in opf:
  opf=opf.replace('</manifest>','<item id="cover" href="images/cover.png" media-type="image/png" properties="cover-image"/></manifest>')
 files['EPUB/package.opf']=opf.encode('utf8')
 files['EPUB/images/cover.png']=image
 temp=path.with_suffix('.new.epub')
 with zipfile.ZipFile(temp,'w') as z:
  for name,data in files.items():
   z.writestr(name,data,compress_type=zipfile.ZIP_STORED if name=='mimetype' else zipfile.ZIP_DEFLATED,compresslevel=6)
 temp.replace(path)
 with zipfile.ZipFile(path) as z:
  assert z.testzip() is None and z.namelist()[0]=='mimetype'
 return files['EPUB/text/book.xhtml']

def mobile_pdf(xhtml,cover_png,path,lang):
 with tempfile.TemporaryDirectory() as d:
  root=Path(d);text=root/'EPUB/text';style=root/'EPUB/styles'
  text.mkdir(parents=True);style.mkdir()
  (text/'book.xhtml').write_bytes(xhtml);(style/'book.css').write_text('')
  content=HTML(filename=str(text/'book.xhtml'), encoding='utf-8').write_pdf(stylesheets=[CSS(string=CSS_PRINT)])
  (root/'cover.png').write_bytes(cover_png)
  front=HTML(string='<html><body><img src="cover.png"/></body></html>',base_url=str(root)).write_pdf(
   stylesheets=[CSS(string='@page{size:90mm 160mm;margin:0}html,body{padding:0;margin:0}img{width:90mm;height:160mm}')])
  writer=PdfWriter();writer.append(PdfReader(io.BytesIO(front)));writer.append(PdfReader(io.BytesIO(content)))
  with path.open('wb') as f:writer.write(f)
 p=PdfReader(str(path),strict=True)
 if len(p.pages)<40:raise ValueError('Insufficient pages for complete manuscript')
 if lang=='ru' and 'Бессознательное' not in ''.join((page.extract_text() or '') for page in p.pages[:5]):
  raise ValueError('Cyrillic PDF text is not decoded correctly; check UTF-8 encoding')
 for n,page in enumerate(p.pages,1):
  w=float(page.mediabox.width)*25.4/72;h=float(page.mediabox.height)*25.4/72
  if abs(w-90)>.05 or abs(h-160)>.05:raise ValueError(f'Non-mobile PDF page {n}: {w}x{h}')
 return len(p.pages)

def main():
 cat=json.loads((ROOT/'catalog.json').read_text(encoding='utf8'))
 gal=json.loads((ROOT/'gallery/books.json').read_text(encoding='utf8'))
 mob=json.loads((ROOT/'mobile-readers.json').read_text(encoding='utf8'))
 existing=[b for b in cat['books'] if b['id']==SLUG]
 if existing and existing != [BOOK]:raise ValueError('Existing publication metadata differs; refuse overwrite')
 if existing:
  cat['books']=[b for b in cat['books'] if b['id']!=SLUG]
  gal=[b for b in gal if b['id']!=SLUG]
  mob['editions']=[e for e in mob['editions'] if not e['relative_path'].startswith(DIR.as_posix()+'/')]
 for lang in ('en','ru'):
  stem=BOOK['file_stems'][lang]
  epub=ROOT/DIR/(stem+'.epub')
  if not epub.is_file():raise ValueError(f'Missing original staged EPUB: {epub}')
  pic=cover(lang);pic_name=f'unconscious-programming-{lang}.png'
  (ROOT/COV/pic_name).write_bytes(pic)
  xhtml=cover_epub(epub,pic)
  pdf=epub.with_suffix('.pdf');pages=mobile_pdf(xhtml,pic,pdf,lang);data=pdf.read_bytes()
  print(lang,pages,'90x160 mm pages',len(data),'bytes')
  mob['editions'].append({'relative_path':(DIR/(stem+'.pdf')).as_posix(),
    'language':lang,'pages':pages,'pdf_sha256':hashlib.sha256(data).hexdigest(),
    'bytes':len(data),'page_size_mm':[90,160]})
  paths={ext:(DIR/(stem+'.'+ext)).as_posix() for ext in ('pdf','epub','zip')}
  gal.append({'id':SLUG,'language':lang,'title':BOOK['title_'+lang],
    'note':BOOK['note_'+lang],'category':'technology',
    'cover':'assets/covers/'+pic_name,
    'cover_source':{'epub':paths['epub'],'member':'EPUB/images/cover.png','sha256':hashlib.sha256(pic).hexdigest()},
    'files':paths,'description':DESC[lang],
    'description_source':{'epub':paths['epub'],'chapters':['EPUB/text/book.xhtml']}})
 cat['books'].append(BOOK)
 for name,val in [('catalog.json',cat),('gallery/books.json',gal),('mobile-readers.json',mob)]:
  (ROOT/name).write_text(json.dumps(val,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 for args in [('scripts/build_catalog.py',),('scripts/verify_reader_files.py',),
              ('scripts/verify_mobile_readers.py',),
              ('scripts/build_gallery.py','--output',str(ROOT/'_site'))]:
  subprocess.run(['python',*args],cwd=ROOT,check=True)
 print('Verified bilingual EPUB/PDF/ZIP readers and mobile gallery.')

if __name__=='__main__':main()
