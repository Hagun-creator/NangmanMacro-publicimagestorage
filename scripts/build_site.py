from pathlib import Path
import json,struct,re,shutil,zlib,binascii,hashlib,os,urllib.request,urllib.parse
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'; SITE=ROOT/'docs'; OUT=ROOT/'dist'
if OUT.exists(): shutil.rmtree(OUT)
shutil.copytree(SITE,OUT)

# Inject the project introduction into the built home page without duplicating it
intro_path=OUT/'intro.html'
index_path=OUT/'index.html'
if intro_path.exists() and index_path.exists():
    intro=intro_path.read_text(encoding='utf-8').strip()
    html=index_path.read_text(encoding='utf-8')
    marker='<main>'
    if intro and intro not in html and marker in html:
        html=html.replace(marker,marker+'\n'+intro+'\n',1)
        index_path.write_text(html,encoding='utf-8')

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

# Pull every Issue carrying the 검증완료 label. This is build-time only; no token is exposed to Pages.
def github_json(url):
    token=os.getenv('GITHUB_TOKEN','')
    headers={'Accept':'application/vnd.github+json','User-Agent':'nangman-image-browser'}
    if token: headers['Authorization']='Bearer '+token
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))

def body_field(body,label):
    pat=r'###\s*'+re.escape(label)+r'\s*\n+(.+?)(?=\n+###\s|\Z)'
    m=re.search(pat,body or '',re.S)
    if not m: return ''
    v=m.group(1).strip()
    if v in ('_No response_','No response'): return ''
    return re.sub(r'\s+',' ',v).strip()

def attachment_url(body):
    body=body or ''
    pats=[
        r'<img[^>]+src=["\'](https://github\.com/user-attachments/assets/[^"\']+)',
        r'!\[[^\]]*\]\((https://github\.com/user-attachments/assets/[^)\s]+)',
        r'<img[^>]+src=["\'](https://private-user-images\.githubusercontent\.com/[^"\']+)',
        r'!\[[^\]]*\]\((https://private-user-images\.githubusercontent\.com/[^)\s]+)'
    ]
    for p in pats:
        m=re.search(p,body,re.I)
        if m: return m.group(1).replace('&amp;','&')
    return ''

def download_issue_image(url,out_base):
    token=os.getenv('GITHUB_TOKEN','')
    headers={'User-Agent':'nangman-image-browser','Accept':'image/*'}
    if token and 'private-user-images.githubusercontent.com' in url:
        headers['Authorization']='Bearer '+token
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=45) as r:
        data=r.read(); ctype=(r.headers.get('Content-Type') or '').lower()
    if data.startswith(b'\x89PNG'): ext='.png'
    elif data[:3]==b'\xff\xd8\xff': ext='.jpg'
    elif data[:4] in (b'RIFF',): ext='.webp'
    elif 'jpeg' in ctype: ext='.jpg'
    elif 'webp' in ctype: ext='.webp'
    else: ext='.png'
    path=out_base.with_suffix(ext); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
    return path

def load_verified_issues(valid_keys):
    repo=os.getenv('GITHUB_REPOSITORY','Hagun-creator/NangmanMacro-publicimagestorage')
    label=urllib.parse.quote('검증완료')
    found={}
    for page in range(1,11):
        url=f'https://api.github.com/repos/{repo}/issues?state=all&labels={label}&per_page=100&page={page}'
        try: issues=github_json(url)
        except Exception as e:
            print('verified issue sync skipped:',e); break
        if not issues: break
        for issue in issues:
            if 'pull_request' in issue: continue
            title=(issue.get('title') or '').strip()
            m=re.match(r'^\[이미지 제출\]\s*(.+?)\s*$',title)
            if not m: continue
            key=m.group(1).strip()
            if key not in valid_keys:
                print('verified issue key not found:',issue.get('number'),key); continue
            url_img=attachment_url(issue.get('body',''))
            if not url_img:
                print('verified issue has no image:',issue.get('number'),key); continue
            old=found.get(key)
            if old and (old.get('updated_at') or '') >= (issue.get('updated_at') or ''): continue
            found[key]=issue
        if len(issues)<100: break
    result={}
    for key,issue in found.items():
        try:
            base=OUT/'generated'/'verified'/'issues'/f"{issue['number']}__{safe(key)}"
            p=download_issue_image(attachment_url(issue.get('body','')),base)
            label_ko=body_field(issue.get('body',''),'화면에 보이는 한국어 이름') or key.split('/',1)[-1]
            result[key]={
                'label':label_ko,
                'note':f"GitHub Issue #{issue['number']}에서 검증완료",
                'png':p.relative_to(OUT).as_posix(),
                'issue_number':issue['number'],
                'issue_url':issue.get('html_url','')
            }
            print('verified issue synced:',key,'<- #'+str(issue['number']))
        except Exception as e:
            print('verified issue image download failed:',issue.get('number'),key,e)
    return result

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
valid_keys={f"{x['category']}/{x['name']}" for x in meta['templates']}
issue_verified=load_verified_issues(valid_keys)
records=[]
for i in range(cnt):
    cat=sr();name=sr();w=u16();h=u16();th=u16();gray=d[pos];pos+=1;inv=bool(d[pos]);pos+=1;n=i32();bits=d[pos:pos+n];pos+=n
    m=byid[i]; c=byid[m['canonical_id']]
    rel=f"generated/original/{safe(cat)}/{c['id']:04d}__{safe(c['name'])}.png"
    if i==m['canonical_id']:
        p=OUT/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(png_bytes(w,h,bits))
    key=f'{cat}/{name}'
    vr_issue=issue_verified.get(key)
    vr_static=verified.get(key)
    if vr_issue:
        vr={'label':vr_issue['label'],'note':vr_issue['note'],'png':vr_issue['png'],'issue_number':vr_issue['issue_number'],'issue_url':vr_issue['issue_url']}
    elif vr_static:
        vr={'label':vr_static['label'],'note':vr_static['note'],'png':'generated/'+vr_static['file']}
    else:
        vr=None
    records.append({**m,'key':key,'original_png':rel,'verified':vr})
cats=[]
for name in sorted({x['category'] for x in records}):
    arr=[x for x in records if x['category']==name]
    uniq={x['canonical_id'] for x in arr};done={x['canonical_id'] for x in arr if x['verified']}
    cats.append({'name':name,'raw_count':len(arr),'unique_count':len(uniq),'duplicate_count':len(arr)-len(uniq),'verified_count':len(done),'usage':arr[0].get('category_usage','')})
manifest={'template_count':len(records),'categories':cats,'records':records,'issue_verified_count':len(issue_verified)}
(OUT/'generated'/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
