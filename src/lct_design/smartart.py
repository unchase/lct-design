"""Native SmartArt retexting with synchronized DrawingML data and drawing cache.

Supported topologies: process (4 steps), organization (root, assistant, 3 teams,
member of first team). Other counts are explicitly rendered as native shapes.
The fixed topology is a format primitive, never a brand/template selection rule.
"""
from pathlib import Path
from lxml import etree as ET
from .package import NS,q,read_package,parse_xml,xml,relationships
from .visuals import frame,sub

DGM='http://schemas.openxmlformats.org/drawingml/2006/diagram'
DSP='http://schemas.microsoft.com/office/drawing/2008/diagram'
N={**NS,'dgm':DGM,'dsp':DSP}

def supported(kind,count):return count==(6 if kind=='hierarchy' else 4)

def replace_paragraph(paragraph,text,font):
    for child in list(paragraph):
        if child.tag!=q('a:pPr'):paragraph.remove(child)
    run=sub(paragraph,'a:r');prop=sub(run,'a:rPr',lang='ru-RU',sz=2400)
    sub(prop,'a:latin',typeface=font);sub(prop,'a:ea',typeface=font);sub(run,'a:t').text=text

def smartart_parts(labels,kind,box,id,prefix,font,accent):
    if not supported(kind,len(labels)):raise ValueError('Unsupported native SmartArt topology')
    source=read_package(Path(__file__).parent/'assets/smartart-families.pptx');n=1 if kind=='hierarchy' else 2
    original=f'ppt/slides/slide{n}.xml';rels=relationships(source,original)
    types=parse_xml(source['[Content_Types].xml']);content_types={t.get('PartName','').lstrip('/'):t.get('ContentType') for t in types}
    data=parse_xml(source[f'ppt/diagrams/data{n}.xml']);drawing=parse_xml(source[f'ppt/diagrams/drawing{n}.xml'])
    nodes=data.findall('dgm:ptLst/dgm:pt',N);cxns=data.findall('dgm:cxnLst/dgm:cxn',N);index=0
    for pt in nodes:
        body=pt.find('dgm:t',N)
        if body is None or not body.xpath('.//a:t',namespaces=N):continue
        typ=pt.get('type','node');label=''
        if typ in ('node','asst'):
            label=labels[index];index+=1
        paras=body.findall('a:p',N)
        for j,p in enumerate(paras):replace_paragraph(p,label if j==0 else '',font)
        for cxn in cxns:
            if cxn.get('type')!='presOf' or cxn.get('srcId')!=pt.get('modelId'):continue
            cached=drawing.xpath('//dsp:sp[@modelId=$id]/dsp:txBody',namespaces=N,id=cxn.get('destId'))
            for tx in cached:
                ordinal=int(cxn.get('destOrd','0'));ps=tx.findall('a:p',N)
                if ordinal<len(ps):replace_paragraph(ps[ordinal],label,font)
    if index!=len(labels):raise ValueError('SmartArt donor content cardinality changed')
    ext=parse_xml(source[original]).find('.//p:graphicFrame/p:xfrm/a:ext',N)
    sw,sh=int(ext.get('cx')),int(ext.get('cy'));scale=min(box.w/sw,box.h/sh)
    dx,dy=(box.w-sw*scale)/2,(box.h-sh*scale)/2
    # LibreOffice consumes the explicit cache coordinates, without scaling them to
    # graphicFrame extents. Resize the cache itself, not just its enclosing frame.
    for t in drawing.findall('.//a:xfrm',N)+drawing.findall('.//dsp:txXfrm',N):
        off=t.find('a:off',N);extent=t.find('a:ext',N)
        if off is not None:
            off.set('x',str(round(int(off.get('x'))*scale+dx)));off.set('y',str(round(int(off.get('y'))*scale+dy)))
        if extent is not None:
            for key in ('cx','cy'):extent.set(key,str(round(int(extent.get(key))*scale)))
    for node in drawing.iter():
        local=node.tag.rsplit('}',1)[-1]
        keys=('x','y') if local=='pt' else ('sz',) if local in ('rPr','defRPr','endParaRPr') else ('lIns','rIns','tIns','bIns') if local=='bodyPr' else ('w',) if local=='ln' else ()
        for key in keys:
            value=node.get(key)
            if value and value.lstrip('-').isdigit():node.set(key,str(round(int(value)*scale)))
    # Bind the native style to the imported theme's accent, including renderer cache.
    for tree in (data,drawing):
        for color in tree.xpath('//a:schemeClr[starts-with(@val,"accent")]',namespaces=N):
            color.tag=q('a:srgbClr');color.set('val',accent)
    newparts={};overrides={};newrels=[];ridmap={}
    for rid,(kindrel,dest) in rels.items():
        if not kindrel.startswith('diagram'):continue
        newrid=prefix+'_'+rid;ridmap[rid]=newrid
        name=f'ppt/diagrams/{prefix}/'+Path(dest).name
        newparts[name]=source[dest];overrides[name]=content_types[dest]
        typeuri=next(r.get('Type') for r in parse_xml(source[f'ppt/slides/_rels/slide{n}.xml.rels']) if r.get('Id')==rid)
        newrels.append({'Id':newrid,'Type':typeuri,'Target':'../diagrams/'+prefix+'/'+Path(dest).name})
    for ext in data.findall('.//dsp:dataModelExt',N):ext.set('relId',ridmap[ext.get('relId')])
    newparts[f'ppt/diagrams/{prefix}/data{n}.xml']=xml(data)
    newparts[f'ppt/diagrams/{prefix}/drawing{n}.xml']=xml(drawing)
    f,g=frame(id,box,DGM);donor=parse_xml(source[original]).find('.//dgm:relIds',N)
    d=ET.SubElement(g,'{'+DGM+'}relIds',nsmap={'dgm':DGM})
    for k,v in donor.attrib.items():d.set(k,ridmap[v])
    return f,newparts,newrels,overrides
