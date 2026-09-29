import hashlib,re
from itertools import combinations
from pathlib import Path
from .models import Finding,Box

def audit_rendered_text(manifest,pages):
    """Compare the exported PDF's searchable text with authored object content."""
    from collections import Counter
    def tokens(s):return Counter(re.findall(r'\w+',s.casefold().replace('\u00ad',''),re.UNICODE))
    result=[]
    for slide,page in zip(manifest['slides'],pages):
        available=tokens(page)
        for obj in slide['objects']:
            if obj['role'] in ('image','chart'):continue
            expected=tokens(obj.get('text',''));missing=expected-available
            if sum(missing.values())>max(1,sum(expected.values())*.1):
                result.append(Finding(id=f'render-text-{slide["number"]}-{obj["id"]}',rule='render.text_missing',severity='error',kind='heuristic',
                    slide=slide['number'],object_id=obj['id'],box=Box(**obj['box']),message='Часть текста не найдена в отрендеренном PDF',
                    evidence={'missing_tokens':list(missing)[:25],'reason':'PDF extraction can also split ligatures or words'}))
    return result

def contrast(a,b):
    def lum(hex):
        n=[int(hex[i:i+2],16)/255 for i in (0,2,4)]
        n=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in n]
        return sum(v*w for v,w in zip(n,(.2126,.7152,.0722)))
    a,b=sorted((lum(a),lum(b)));return (b+.05)/(a+.05)

def audit_deck(manifest,render,profile=None,render_dir=None):
    findings=[];w,h=manifest['width'],manifest['height']
    def add(rule,message,slide=None,obj=None,severity='warning',kind='deterministic',status='failed',repair=None,evidence=None):
        key=f'{rule}:{slide}:{obj.get("id") if obj else ""}:{message}'
        findings.append(Finding(id=hashlib.sha256(key.encode()).hexdigest()[:16],rule=rule,message=message,slide=slide,
            object_id=obj.get('id') if obj else None,box=Box(**obj['box']) if obj else None,severity=severity,
            kind=kind,status=status,repair=repair,evidence=evidence or {}))
    if render.status!='complete': add('render.available','Рендеринг не выполнен: '+(render.error or 'недоступен'),kind='deterministic',status='not_run')
    elif len(render.images)!=len(manifest['slides']): add('render.slide_count','Число страниц рендера отличается от плана',severity='error')
    else: add('render.available','Экспортированный PPTX отрендерен',severity='info',status='passed',evidence={'engine':render.engine,'pages':len(render.images)})
    add('content.semantic','Контекстуальная проверка требует подключённой VLM',kind='contextual',status='not_run',severity='info')
    seen=set()
    for slide in manifest['slides']:
        n=slide['number'];objects=slide['objects'];text=' '.join(o.get('text','') for o in objects)
        if text in seen: add('content.duplicate','Повторяющийся контент слайда',n)
        seen.add(text)
        if len(objects)<2: add('content.empty','На слайде только заголовок',n,severity='error')
        for o in objects:
            b=o['box']
            if b['x']<0 or b['y']<0 or b['x']+b['w']>w+1 or b['y']+b['h']>h+1:
                add('layout.bounds','Объект выходит за границы слайда',n,o,'error',repair=None)
            if o.get('overflow'): add('text.fit','Текст может не поместиться в рамку',n,o,'error','heuristic',repair='refit' if o.get('role') not in ('table','smartart','chart','image') else None,evidence={'estimate':'character-width and font-size approximation'})
            if re.search(r'lorem ipsum|\bXXX\b|\bTODO\b|вставьте текст',o.get('text',''),re.I): add('content.placeholder','Обнаружен текст-заглушка',n,o,'error')
            if o.get('rows',0)>7 or o.get('columns',0)>5: add('density.table','Таблица больше 7 строк или 5 колонок',n,o)
            if o.get('role','').startswith('body'):
                lines=o.get('text','').split('\n')
                if len(lines)>6: add('density.bullets','Больше 6 текстовых пунктов',n,o)
                if any(len(line.split())>15 for line in lines): add('density.words','Пункт длиннее 15 слов',n,o)
            if o.get('color'):
                ratio=contrast(o['color'],slide.get('background','FFFFFF'))
                if ratio<4.5: add('style.contrast','Контраст к заливке ниже 4.5:1; фон под объектом требует визуальной проверки',n,o,kind='heuristic',evidence={'ratio':round(ratio,2)})
            if profile and o.get('font') and o['font'] not in profile.fonts: add('style.font','Шрифт отсутствует в извлечённой типографике',n,o)
        for a,b in combinations(objects,2):
            aa,bb=a['box'],b['box'];iw=min(aa['x']+aa['w'],bb['x']+bb['w'])-max(aa['x'],bb['x']);ih=min(aa['y']+aa['h'],bb['y']+bb['h'])-max(aa['y'],bb['y'])
            if iw>0 and ih>0 and iw*ih>min(aa['w']*aa['h'],bb['w']*bb['h'])*.03:
                add('layout.overlap','Пересекаются два содержательных блока',n,a,'error',evidence={'other_object':b['id']})
    if render_dir and profile:
        file=Path(render_dir)/'fonts.txt'
        if file.exists():
            available=file.read_text(encoding='utf-8',errors='replace').lower()
            used={o.get('font') for s in manifest['slides'] for o in s['objects'] if o.get('font')}
            missing=[f for f in used if f.lower() not in available]
            if missing: add('render.fonts','Renderer использовал замену отсутствующих шрифтов: '+', '.join(sorted(missing)),evidence={'missing':sorted(missing)})
    if render_dir and render.status=='complete' and render.pdf:
        from pypdf import PdfReader
        try:
            pages=PdfReader(Path(render_dir)/render.pdf).pages
            findings.extend(audit_rendered_text(manifest,[p.extract_text() for p in pages]))
            geometry=Path(render_dir)/'geometry.html'
            if geometry.exists():
                from lxml import etree as ET
                tree=ET.fromstring(geometry.read_bytes(),ET.XMLParser(resolve_entities=False,no_network=True,load_dtd=False))
                for i,page in enumerate(tree.xpath('//*[local-name()="page"]'),1):
                    pw,ph=float(page.get('width')),float(page.get('height'))
                    for word in page.xpath('.//*[local-name()="word"]'):
                        x,y,right,bottom=[float(word.get(k)) for k in ('xMin','yMin','xMax','yMax')]
                        if x<-.5 or y<-.5 or right>pw+.5 or bottom>ph+.5:
                            obj={'id':'pdf-word','box':{'x':x/pw*w,'y':y/ph*h,'w':(right-x)/pw*w,'h':(bottom-y)/ph*h}}
                            add('render.bounds','Отрендеренный текст выходит за страницу',i,obj,'error',evidence={'text':word.text})
            add('render.text_extraction','Текст PDF сопоставлен с содержанием объектов',severity='info',status='passed')
        except Exception as exc:add('render.text_extraction','Не удалось проверить текст PDF',status='not_run',evidence={'error':str(exc)[:200]})
    return findings
