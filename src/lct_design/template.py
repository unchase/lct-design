"""Extract effective template typography, geometry and reusable patterns."""
import hashlib, math, re
from collections import Counter
from pathlib import Path
from .package import NS,q,parse_xml,read_package,relationships
from .models import Box,Slot,Pattern,TemplateProfile

EMU=914400
# Sample prompts inside media frames ("Вставить фото", "Insert picture") are not content.
PROMPT=re.compile(r'вставь?(?:те|ить)?\s*(?:сюда\s*)?(?:фото|изображени|картинк|скриншот|график)|insert\s*(?:your\s*)?(?:photo|picture|image)|^\s*(?:фото|photo|image|screenshot|скриншот)\s*$')
ANALYSIS_ALGORITHM='OOXML effective styles + geometry families + inherited artwork + media frames v6'

def linked(parts,part,kind):
    return next((dest for k,dest in relationships(parts,part).values() if k==kind and dest in parts),None)

def themes(parts,slide):
    layout=linked(parts,slide,'slideLayout')
    master=linked(parts,layout,'slideMaster') if layout else None
    theme=linked(parts,master,'theme') if master else None
    theme=theme or linked(parts,'ppt/presentation.xml','theme')
    theme=theme or next((n for n in parts if n.startswith('ppt/theme/') and n.endswith('.xml')),None)
    return layout,master,theme

def theme_tokens(parts,theme):
    colors={};fonts={'major':'Arial','minor':'Arial'}
    if theme:
        tree=parse_xml(parts[theme]);scheme=tree.find('.//a:clrScheme',NS)
        if scheme is not None:
            for child in scheme:
                c=next(iter(child),None)
                if c is not None: colors[child.tag.rsplit('}',1)[-1]]=c.get('val') if c.tag==q('a:srgbClr') else c.get('lastClr','111111')
        for role,tag in [('major','majorFont'),('minor','minorFont')]:
            f=tree.find('.//a:'+tag+'/a:latin',NS)
            if f is not None and f.get('typeface'): fonts[role]=f.get('typeface')
    colors.update({'tx1':colors.get('dk1','111111'),'tx2':colors.get('dk2','111111'),
                   'bg1':colors.get('lt1','FFFFFF'),'bg2':colors.get('lt2','FFFFFF')})
    return colors,fonts

def resolve_color(node,colors,default='111111'):
    if node is None: return default
    c=node.find('.//a:srgbClr',NS)
    if c is None: c=node.find('.//a:schemeClr',NS)
    if c is None: c=node.find('.//a:sysClr',NS)
    if c is None: return default
    value=colors.get(c.get('val'),c.get('lastClr',c.get('val',default)))
    if not value or len(value)!=6: return default
    try: rgb=[int(value[i:i+2],16)/255 for i in (0,2,4)]
    except ValueError: return default
    for t in c:
        name=t.tag.rsplit('}',1)[-1];v=int(t.get('val','0'))/100000
        if name=='lumMod': rgb=[n*v for n in rgb]
        elif name=='lumOff': rgb=[n+v for n in rgb]
        elif name=='tint': rgb=[n+(1-n)*v for n in rgb]
        elif name=='shade': rgb=[n*v for n in rgb]
    return ''.join(f'{round(max(0,min(1,n))*255):02X}' for n in rgb)

def placeholder(shape):
    ph=shape.find('.//p:ph',NS)
    return (ph.get('type','body'),ph.get('idx','0')) if ph is not None else None

def ancestor_shapes(parts,shape,layout,master):
    chain=[shape];ph=placeholder(shape)
    for part in (layout,master):
        if part and ph:
            candidates=parse_xml(parts[part]).findall('.//p:sp',NS)
            found=next((s for s in candidates if placeholder(s) and placeholder(s)[1]==ph[1]),None)
            if found is None: found=next((s for s in candidates if placeholder(s) and placeholder(s)[0]==ph[0]),None)
            if found is not None: chain.append(found)
    return chain

def geometry(shape,chain):
    t=None
    for item in chain:
        t=item.find('p:spPr/a:xfrm',NS)
        if t is not None: break
    if t is None: return None
    off=t.find('a:off',NS);ext=t.find('a:ext',NS)
    if off is None or ext is None: return None
    x,y=float(off.get('x',0)),float(off.get('y',0));w,h=float(ext.get('cx',0)),float(ext.get('cy',0))
    for parent in shape.iterancestors(q('p:grpSp')):
        gt=parent.find('p:grpSpPr/a:xfrm',NS)
        if gt is None: continue
        o,e,co,ce=[gt.find('a:'+tag,NS) for tag in ('off','ext','chOff','chExt')]
        if any(v is None for v in (o,e,co,ce)): continue
        sx=float(e.get('cx'))/max(1,float(ce.get('cx')));sy=float(e.get('cy'))/max(1,float(ce.get('cy')))
        x=float(o.get('x'))+(x-float(co.get('x')))*sx;y=float(o.get('y'))+(y-float(co.get('y')))*sy;w*=sx;h*=sy
    return Box(x=x,y=y,w=w,h=h) if w>0 and h>0 else None

def media_frames(tree,slots,width,height):
    """Empty filled panels and picture placeholders reserved for screenshots, photos or charts."""
    frames=[]
    for shape in tree.findall('.//p:cSld/p:spTree//p:sp',NS):
        if ''.join(shape.xpath('.//a:t/text()',namespaces=NS)).strip():continue
        ph=placeholder(shape);sp=shape.find('p:spPr',NS)
        if ph and ph[0] not in ('pic','media','clipArt','chart','tbl','obj'):continue
        filled=bool(ph) or (sp is not None and sp.find('a:noFill',NS) is None and (sp.find('a:solidFill',NS) is not None or
            sp.find('a:gradFill',NS) is not None or shape.find('p:style/a:fillRef',NS) is not None))
        box=geometry(shape,[shape])
        if not filled or box is None or not .06<=box.w*box.h/(width*height)<=.8:continue
        # A panel under a text block is that block's card, not a free media area.
        def inter(a,b):return max(0,min(a.x+a.w,b.x+b.w)-max(a.x,b.x))*max(0,min(a.y+a.h,b.y+b.h)-max(a.y,b.y))
        if any(inter(box,s.box)>s.box.w*s.box.h*.3 for s in slots if s.role in ('title','body') and s.text.strip() and not PROMPT.search(s.text.lower())):continue
        frames.append(box)
    return frames

def analyze_template(path:Path)->TemplateProfile:
    parts=read_package(path);pres=parse_xml(parts['ppt/presentation.xml']);size=pres.find('p:sldSz',NS)
    width,height=int(size.get('cx')),int(size.get('cy'));rels=relationships(parts,'ppt/presentation.xml')
    patterns=[];allcolors=Counter();allfonts=Counter();allsizes=Counter();warnings=[]
    for i,sid in enumerate(pres.find('p:sldIdLst',NS)):
        entry=rels.get(sid.get(q('r:id')))
        if not entry or entry[1] not in parts: continue
        part=entry[1];tree=parse_xml(parts[part]);layout,master,theme=themes(parts,part)
        colors,fonts=theme_tokens(parts,theme);allcolors.update(colors.values());slots=[]
        # Master's clrMap can map accent/text aliases to alternative scheme slots.
        if master:
            cmap=parse_xml(parts[master]).find('p:clrMap',NS)
            if cmap is not None:
                colors.update({k:colors.get(v,'111111') for k,v in cmap.attrib.items()})
        for shape in tree.findall('.//p:sp',NS):
            tx=shape.find('p:txBody',NS)
            if tx is None: continue
            text='\n'.join(''.join(p.xpath('.//a:t/text()',namespaces=NS)) for p in tx.findall('a:p',NS)).strip()
            if not text and placeholder(shape) is None: continue
            chain=ancestor_shapes(parts,shape,layout,master);box=geometry(shape,chain)
            if box is None or box.w<width*.025 or box.h<height*.015: continue
            props=[]
            for s in chain:
                props.extend(s.findall('.//a:rPr',NS)+s.findall('.//a:defRPr',NS)+s.findall('.//a:endParaRPr',NS))
            typ=placeholder(shape)
            if master:
                style='titleStyle' if typ and typ[0] in ('title','ctrTitle') else 'bodyStyle'
                props.extend(parse_xml(parts[master]).findall('.//p:'+style+'/a:lvl1pPr/a:defRPr',NS))
            sz=next((float(p.get('sz'))/100 for p in props if p.get('sz')),20.0)
            font=next((p.find('a:latin',NS).get('typeface') for p in props if p.find('a:latin',NS) is not None),fonts['minor'])
            if font.startswith('+'): font=fonts['major' if font.startswith('+mj') else 'minor']
            color=next((resolve_color(p,colors) for p in props if p.find('a:solidFill',NS) is not None),colors.get('tx1','111111'))
            nv=shape.find('p:nvSpPr/p:cNvPr',NS)
            role='footer' if typ and typ[0] in ('ftr','dt','sldNum') else 'body'
            if text.isdigit() and box.y>height*.8: role='footer'
            slots.append(Slot(id=nv.get('id'),role=role,box=box,font=font,size=sz,color=color,text=text))
            allfonts[font]+=1;allsizes[sz]+=1;allcolors[color]+=1
        body=[s for s in slots if s.role!='footer']
        if not body: continue
        title_candidates=[s for s in body if s.box.y<height*.22 and not s.text.strip().isdigit()]
        # A large metric below the header is still body content. Prefer the top
        # heading band before comparing typography; font size alone is ambiguous.
        if title_candidates:
            top=min(s.box.y for s in title_candidates)
            title_candidates=[s for s in title_candidates if s.box.y<=top+height*.04]
        title=max(title_candidates or body,key=lambda s:s.size+(1-s.box.y/height)*30-min(len(s.text),500)/100)
        title.role='title'
        slots.sort(key=lambda s:(s.role!='title',s.box.y,s.box.x))
        n=len(body)-1;family='cover' if n<=0 else 'split' if n in (2,3) else 'content' if n<=6 else 'dense'
        if any(re.search(r'\b(body\s*\{|function\s*\(|import\s+|padding\s*:|def\s+\w+)',s.text) for s in body): family='code'
        elif title.box.y>height*.22: family='cover'
        if any(x in title.text.lower() for x in ('шрифт','палитр','иконки','логотипы','инструкция','palette','typography','font','logo','guideline','instruction','how to use')): family='guide'
        background='FFFFFF'
        for scope in (part,layout,master):
            if scope:
                bg=parse_xml(parts[scope]).find('.//p:bg',NS)
                if bg is not None: background=resolve_color(bg,colors,'FFFFFF');break
        artwork=[];scopes=[tree]
        if layout:
            ltree=parse_xml(parts[layout]);scopes.append(ltree)
            # Master artwork shows through unless the layout hides master shapes.
            if master and ltree.get('showMasterSp','1') not in ('0','false'):scopes.append(parse_xml(parts[master]))
        for picture in (pic for scope in scopes for pic in scope.findall('.//p:cSld/p:spTree//p:pic',NS)):
            pb=geometry(picture,[picture])
            # Full-bleed pictures are backgrounds; smaller ones are content artwork to avoid.
            if pb and not (pb.x<=width*.03 and pb.y<=height*.03 and pb.x+pb.w>=width*.97 and pb.y+pb.h>=height*.97):artwork.append(pb)
        frames=media_frames(tree,slots,width,height)
        feature=[n/10,sum(s.box.w*s.box.h for s in body)/width/height,title.box.y/height,title.size/100]
        patterns.append(Pattern(id=f'p{i+1}',part=part,index=i+1,scope=master or theme or part,
            slots=slots,family=family,background=background,complexity=len(tree.findall('.//p:sp',NS))+len(tree.findall('.//p:pic',NS))*2,
            visual_features=feature,artwork=artwork,frames=frames))
    if not patterns: raise ValueError('No editable text slots found in the presentation')
    return TemplateProfile(hash=hashlib.sha256(Path(path).read_bytes()).hexdigest(),filename=Path(path).name,
        width=width,height=height,colors=[c for c,_ in allcolors.most_common(32)],fonts=list(allfonts),
        font_sizes=sorted(allsizes),patterns=patterns,warnings=warnings,
        asset_count=sum(n.startswith('ppt/media/') for n in parts),
        analysis={'structural':'complete','visual':'not_run','semantic':'not_run','algorithm':ANALYSIS_ALGORITHM})
