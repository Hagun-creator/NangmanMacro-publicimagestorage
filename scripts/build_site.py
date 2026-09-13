from pathlib import Path
import json,struct,re,shutil,zlib,binascii,hashlib
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'; SITE=ROOT/'docs'; OUT=ROOT/'dist'
if OUT.exists(): shutil.rmtree(OUT)
shutil.copytree(SITE,OUT)
(OUT/'generated'/'original').mkdir(parents=True)
(OUT/'generated'/'verified').mkdir(parents=True)
meta=json.loads((DATA/'templates_meta.json').read_text(encoding='utf-8'))
verified=json.loads((DATA/'verified.json').read_text(encoding='utf-8'))
for p in (DATA/'verified').glob('*.png'):
    shutil.copy2(p,OUT/'generated'/'verified'/p.name)

def safe(s): return re.sub(r'[^0-9A-Za-z가-힣._-]+','_',s)
def png_bytes(w,h,bits):
    rows=[]
    for y in range(h):
        row=bytearray([0])
        for x in range(w):
            i=y*w+x; on=(bits[i>>3]>>(i&7))&1; v=255 if on else 22
            row.extend((v,v,v,255))
        rows.append(bytes(row))
    raw=b''.join(rows)
    def chunk(t,b): return struct.pack('>I',len(b))+t+b+struct.pack('>I',binascii.crc32(t+b)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b'')

d=(DATA/'templates.bin').read_bytes();pos=4
ver=struct.unpack('>I',d[pos:pos+4])[0];pos+=4;cnt=struct.unpack('>I',d[pos:pos+4])[0];pos+=4
def u16():
    global pos
    v=struct.unpack('>H',d[pos:pos+2])[0];pos+=2;return v
def i32():
    global pos
    v=struct.unpack('>i',d[pos:pos+4])[0];pos+=4;return v
def sr():
    global pos
    n=u16();v=d[pos:pos+n].decode('utf-8');pos+=n;return v
byid={x['id']:x for x in meta['templates']}
records=[]
for i in range(cnt):
    cat=sr();name=sr();w=u16();h=u16();th=u16();gray=d[pos];pos+=1;inv=bool(d[pos]);pos+=1;n=i32();bits=d[pos:pos+n];pos+=n
    m=byid[i]; c=byid[m['canonical_id']]
    rel=f"generated/original/{safe(cat)}/{c['id']:04d}__{safe(c['name'])}.png"
    if i==m['canonical_id']:
        p=OUT/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(png_bytes(w,h,bits))
    key=f'{cat}/{name}'; vr=verified.get(key)
    records.append({**m,'key':key,'original_png':rel,'verified':({'label':vr['label'],'note':vr['note'],'png':'generated/'+vr['file']} if vr else None)})
cats=[]
for name in sorted({x['category'] for x in records}):
    arr=[x for x in records if x['category']==name]
    uniq={x['canonical_id'] for x in arr};done={x['canonical_id'] for x in arr if x['verified']}
    cats.append({'name':name,'raw_count':len(arr),'unique_count':len(uniq),'duplicate_count':len(arr)-len(uniq),'verified_count':len(done),'usage':arr[0].get('category_usage','')})
manifest={'template_count':len(records),'categories':cats,'records':records}
(OUT/'generated'/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
