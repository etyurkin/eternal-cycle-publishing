import unittest,json,sys,tempfile,os,copy,zipfile
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from build_gallery import build,safe,verify_provenance
SOURCE=Path(os.environ.get('GALLERY_SOURCE',str(ROOT if (ROOT/'catalog.json').exists() else ROOT.parent/'catalog_mobile/source_repo')))
class Links(HTMLParser):
 def __init__(self):super().__init__();self.urls=[];self.cards=0;self.images=0
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='article':self.cards+=1
  if tag=='img':self.images+=1;assert a.get('alt')
  for k in ('href','src'):
   if k in a:self.urls.append(a[k])
class GalleryTests(unittest.TestCase):
 def test_current_approved_scope(self):
  data=json.loads((ROOT/'gallery/books.json').read_text())
  self.assertEqual(len(data),24);self.assertEqual(len({b['id'] for b in data}),13)
  for bid in ('philosophy-of-intent-machines','the-last-don-quixote'):
   cards=[b for b in data if b['id']==bid]
   self.assertEqual({b['language'] for b in cards},{'en','ru'})
   for b in cards:
    with zipfile.ZipFile(SOURCE/b['files']['epub']) as archive:
     self.assertEqual((ROOT/'gallery'/b['cover']).read_bytes(),archive.read(b['cover_source']['member']))
 def test_allowlisted_build_and_links(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'site';expected=build(SOURCE,out,'/eternal-cycle-publishing/')
   data=json.loads((ROOT/'gallery/books.json').read_text())
   self.assertEqual(expected,{str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()});self.assertEqual(len(expected),len(data)*4+4)
   for language,rel in (('ru','index.html'),('en','en/index.html')):
    count=sum(b['language']==language for b in data)
    p=Links();p.feed((out/rel).read_text());self.assertEqual(p.cards,count);self.assertEqual(p.images,count)
    for url in p.urls:
     if url.startswith('/eternal-cycle-publishing/'):
      self.assertTrue((out/unquote(url.removeprefix('/eternal-cycle-publishing/'))).exists(),url)
   for name in ('README.md','catalog.json','books.json','research','.git','.github'):self.assertFalse((out/name).exists())
 def test_unapproved_output_refused(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d);(out/'secret.txt').write_text('no')
   with self.assertRaises(ValueError):build(SOURCE,out,'/')
   self.assertEqual((out/'secret.txt').read_text(),'no')
 def test_path_traversal_refused(self):
  with self.assertRaises(ValueError):safe(SOURCE,'../secret')
 def test_bad_base_refused(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):build(SOURCE,Path(d),'https://bad/')
 def test_provenance(self):
  for b in json.loads((ROOT/'gallery/books.json').read_text()):
   self.assertTrue(b['description_source']['chapters']);self.assertEqual(b['cover_source']['epub'],b['files']['epub'])
   verify_provenance(SOURCE,b)
 def test_changed_cover_source_rejected(self):
  b=copy.deepcopy(json.loads((ROOT/'gallery/books.json').read_text())[0]);b['cover_source']['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'Cover source hash mismatch'):verify_provenance(SOURCE,b)
 def test_missing_description_source_rejected(self):
  b=copy.deepcopy(json.loads((ROOT/'gallery/books.json').read_text())[0]);b['description_source']['chapters']=['missing.xhtml']
  with self.assertRaisesRegex(ValueError,'Missing description source chapter'):verify_provenance(SOURCE,b)
 def test_other_epub_provenance_rejected(self):
  b=copy.deepcopy(json.loads((ROOT/'gallery/books.json').read_text())[0]);b['description_source']['epub']='unapproved.epub'
  with self.assertRaisesRegex(ValueError,'provenance differs'):verify_provenance(SOURCE,b)
if __name__=='__main__':unittest.main()
