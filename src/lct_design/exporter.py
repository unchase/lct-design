import copy, posixpath, hashlib
from pathlib import Path
from lxml import etree as ET
from .package import NS,q,read_package,parse_xml,xml,relationships,rels_path,write_package,target_part
from .models import Box
from .layout import fit_text,select_pattern,body_boxes
from .visuals import element,sub,text_shape,table_shape,chart_parts,chart_workbook,frame,picture_shape

SLIDE_CT='application/vnd.openxmlformats-officedocument.presentationml.slide+xml'
CHART_CT='application/vnd.openxmlformats-officedocument.drawingml.chart+xml'

def add_override(types,name,content):
    node=ET.SubElement(types,'{'+NS['ct']+'}Override');node.set('PartName','/'+name);node.set('ContentType',content)

def prune(parts):
    reachable={'[Content_Types].xml','_rels/.rels'};queue=['']
    while queue:
        part=queue.pop();rp=rels_path(part) if part else '_rels/.rels'
        if rp not in parts: continue
        reachable.add(rp)
        for rel in parse_xml(parts[rp]):
            if rel.get('TargetMode')=='External': continue
            dest=target_part(part,rel.get('Target',''))
            if dest in parts and dest not in reachable: reachable.add(dest);queue.append(dest)
    return {k:v for k,v in parts.items() if k in reachable}

def generate_deck(template,profile,plan,variant,output,repairs=None):
    if variant not in ('sequential','comparison','focus'): raise ValueError('Unknown variant')
    parts=read_package(template);pres=parse_xml(parts['ppt/presentation.xml']);types=parse_xml(parts['[Content_Types].xml'])
    pr=parse_xml(parts['ppt/_rels/presentation.xml.rels']);ids=pres.find('p:sldIdLst',NS)
    ids.clear()
    for rel in list(pr):
        if rel.get('Type','').endswith(('/slide','/notesMaster','/commentAuthors')): pr.remove(rel)
    # Old custom shows and section indexes contain stale slide relationship IDs.
    for tag in ('custShowLst','extLst','notesMasterIdLst'):
        for node in pres.findall('p:'+tag,NS): pres.remove(node)
    manifest={'version':'1.0','template_hash':profile.hash,'width':profile.width,'height':profile.height,
        'variant':variant,'mode':plan.mode,'slides':[],'warnings':list(plan.warnings),'model':plan.model,'usage':plan.usage}
    from .template import geometry
    visual_regions={}
    for pattern in profile.patterns:
        regions=[]
        for picture in parse_xml(parts[pattern.part]).findall('.//p:pic',NS):
            box=geometry(picture,[picture])
            if box is None:continue
            full_background=(box.x<=profile.width*.03 and box.y<=profile.height*.03 and
                box.x+box.w>=profile.width*.97 and box.y+box.h>=profile.height*.97)
            if not full_background:regions.append(box)
        visual_regions[pattern.id]=regions
    chartno=10000
    for index,slide in enumerate(plan.slides):
        choice=slide.layouts.get(variant)
        if choice:
            from .planner import validate_layouts
            validate_layouts({variant:choice.model_dump()},profile,[variant],bool(slide.chart or slide.table or slide.diagram or slide.image))
            pattern=next(p for p in profile.patterns if p.id==choice.pattern_id)
        else:pattern=select_pattern(profile,slide,variant,index,visual_regions)
        tree=parse_xml(parts[pattern.part]);spTree=tree.find('p:cSld/p:spTree',NS)
        newpart=f'ppt/slides/slide{index+10000}.xml';source_rels=relationships(parts,pattern.part)
        sr=parse_xml(parts[rels_path(pattern.part)]) if rels_path(pattern.part) in parts else ET.Element('{'+NS['rel']+'}Relationships',nsmap={None:NS['rel']})
        for rel in list(sr):
            if rel.get('Type','').endswith(('/notesSlide','/comments','/oleObject','/hyperlink','/diagramDrawing')): sr.remove(rel)
        # Text and its visual container are separate. Keep the original shape, fill,
        # outline, effect, transforms and stacking order; clear only mutable text.
        # Footer/brand text and unclassified small decorative labels stay intact.
        mutable_ids={s.id for s in pattern.slots if s.role in ('title','body')}
        for node in list(tree.findall('.//p:sp',NS)):
            nv=node.find('p:nvSpPr/p:cNvPr',NS);body=node.find('p:txBody',NS)
            if nv is not None and nv.get('id') in mutable_ids and body is not None:
                for paragraph in list(body.findall('a:p',NS)):body.remove(paragraph)
                ET.SubElement(body,q('a:p'))
        for node in list(tree.findall('.//p:graphicFrame',NS))+list(tree.findall('.//p:oleObj',NS)):
            node.getparent().remove(node)
        # Size/frequency cannot distinguish a photograph from branded background
        # artwork. Preserve template pictures and their relationships by default.
        for tag in ('timing','transition'):
            for node in tree.findall('p:'+tag,NS): tree.remove(node)
        title=next(s for s in pattern.slots if s.role=='title');base=max((s for s in pattern.slots if s.role=='body'),key=lambda s:s.box.w*s.box.h,default=title)
        if choice:base=next(s for s in pattern.slots if s.id==choice.body_slot_ids[0])
        objects=[];idbase=max([int(n.get('id','0')) for n in tree.findall('.//p:cNvPr',NS)]+[100])+10
        def text(text,box,size,role,bold=False):
            nonlocal idbase
            size,overflow=fit_text(text,box,size,profile.font_sizes)
            if repairs and f'{index+1}:{role}' in repairs:
                size,overflow=fit_text(text,box,max(12,size*.82),list(range(12,int(size)+1)))
            spTree.append(text_shape(idbase,box,text,title.font if role=='title' else base.font,size,title.color if role=='title' else base.color,bold))
            objects.append({'id':str(idbase),'role':role,'box':box.model_dump(),'text':text,'font':title.font if role=='title' else base.font,
                'size':size,'color':title.color if role=='title' else base.color,'overflow':overflow});idbase+=1
        text(slide.title,title.box,title.size,'title',True)
        visual=bool(slide.chart or slide.table or slide.diagram or slide.image);boxes=body_boxes(pattern,profile,variant,visual)
        if choice:boxes=[next(s.box for s in pattern.slots if s.id==sid) for sid in choice.body_slot_ids]
        box=boxes[0];accent=next((c for c in profile.colors if c not in ('FFFFFF','000000','111111') and int(c,16)<0xEEEEEE),'3366AA')
        if visual and slide.bullets:
            text('\n'.join(slide.bullets),Box(x=box.x,y=box.y,w=box.w,h=box.h*.2),min(base.size,18),'caption')
            box=Box(x=box.x,y=box.y+box.h*.24,w=box.w,h=box.h*.76)
        if slide.table:
            size=min(base.size,18);spTree.append(table_shape(idbase,box,slide.table,base.font,base.color,accent,size,pattern.background))
            objects.append({'id':str(idbase),'role':'table','box':box.model_dump(),'text':'\n'.join(' | '.join(r) for r in slide.table),'rows':len(slide.table),'columns':len(slide.table[0]),'overflow':len(slide.table)>7})
        elif slide.chart:
            chartno+=1;cp=f'ppt/charts/chart{chartno}.xml';parts[cp]=chart_parts(slide.chart,base.font,accent);add_override(types,cp,CHART_CT)
            workbook=f'ppt/embeddings/chart{chartno}.xlsx';parts[workbook]=chart_workbook(slide.chart)
            add_override(types,workbook,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            parts[rels_path(cp)]=f'<Relationships xmlns="{NS["rel"]}"><Relationship Id="workbook" Type="{NS["r"]}/package" Target="../embeddings/chart{chartno}.xlsx"/></Relationships>'.encode()
            rid=f'lctChart{index}';rel=ET.SubElement(sr,'{'+NS['rel']+'}Relationship',Id=rid,Type=NS['r']+'/chart',Target='../charts/'+posixpath.basename(cp))
            f,data=frame(idbase,box,NS['c']);sub(data,'c:chart',**{q('r:id'):rid});spTree.append(f)
            objects.append({'id':str(idbase),'role':'chart','box':box.model_dump(),'text':slide.chart.title,'series':len(slide.chart.series),'unit':slide.chart.unit,'overflow':False})
        elif slide.image:
            from .images import decode_image
            data,ext,iw,ih=decode_image(slide.image);imagepart=f'ppt/media/lct{index}.{ext}';parts[imagepart]=data
            add_override(types,imagepart,'image/'+ext);rid=f'lctImage{index}'
            ET.SubElement(sr,'{'+NS['rel']+'}Relationship',Id=rid,Type=NS['r']+'/image',Target='../media/'+posixpath.basename(imagepart))
            scale=min(box.w/iw,box.h/ih);b=Box(x=box.x+(box.w-iw*scale)/2,y=box.y+(box.h-ih*scale)/2,w=iw*scale,h=ih*scale)
            spTree.append(picture_shape(idbase,b,rid,slide.title))
            objects.append({'id':str(idbase),'role':'image','box':b.model_dump(),'text':'','overflow':False})
        elif slide.diagram:
            from .smartart import supported,smartart_parts
            labels=slide.diagram;n=len(labels);gap=box.w*.03
            native=supported(slide.diagram_kind,n) and (slide.diagram_kind=='process' or (slide.diagram_parents==[None,0,0,0,0,2] and slide.diagram_assistant==1))
            if native:
                f,dp,dr,dt=smartart_parts(labels,slide.diagram_kind,box,idbase,f'lct{index}',base.font,accent)
                spTree.append(f);parts.update(dp)
                for rel in dr:ET.SubElement(sr,'{'+NS['rel']+'}Relationship',**rel)
                for part,ct in dt.items():add_override(types,part,ct)
                objects.append({'id':str(idbase),'role':'smartart','box':box.model_dump(),'text':'\n'.join(labels),'topology':slide.diagram_kind,'overflow':any(len(t)>100 for t in labels)})
            else:
                from .diagrams import vector_boxes,connector
                regions,edges=vector_boxes(labels,slide.diagram_kind,slide.diagram_parents,box)
                for j,(a,b) in enumerate(edges):spTree.append(connector(idbase+n+j,regions[a],regions[b],accent))
                for j,label in enumerate(labels):
                    b=regions[j]
                    text(label,b,min(base.size,20),f'diagram-{j}',True)
                manifest['warnings'].append(f'Схема на слайде {index+1}: {n} узлов созданы фигурами. Native SmartArt поддерживает процесс из 4 шагов и организацию из 6 узлов фиксированной структуры.')
        else:
            count=len(boxes);chunks=[slide.bullets[(len(slide.bullets)*j+count-1)//count:(len(slide.bullets)*(j+1)+count-1)//count] for j in range(count)]
            for j,(b,chunk) in enumerate(zip(boxes,chunks)):
                if choice:base=next(s for s in pattern.slots if s.id==choice.body_slot_ids[j])
                if chunk: text('\n'.join(chunk),b,min(base.size*1.2,32) if variant=='focus' else base.size,f'body-{j}')
        # Keep only relationships that are used, plus the slide layout.
        used={v for node in tree.iter() for k,v in node.attrib.items() if k.startswith('{'+NS['r']+'}')}
        for rel in list(sr):
            # SmartArt dataModelExt references the cache via the slide's relationship
            # scope; it is not a direct r:* attribute on this slide tree.
            if rel.get('Id') not in used and not rel.get('Type','').endswith(('/slideLayout','/diagramDrawing')): sr.remove(rel)
        from .speech import attach_notes
        note=attach_notes(parts,newpart,sr,slide.speaker_notes,index)
        add_override(types,note,'application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml')
        parts[newpart]=xml(tree);parts[rels_path(newpart)]=xml(sr);rid=f'lctSlide{index+1}'
        ET.SubElement(pr,'{'+NS['rel']+'}Relationship',Id=rid,Type=NS['r']+'/slide',Target='slides/'+posixpath.basename(newpart))
        ET.SubElement(ids,q('p:sldId'),{'id':str(256+index),q('r:id'):rid});add_override(types,newpart,SLIDE_CT)
        manifest['slides'].append({'number':index+1,'title':slide.title,'source_ids':slide.source_ids,'pattern_id':pattern.id,
            'layout_source':'llm' if choice else 'heuristic','body_slot_ids':choice.body_slot_ids if choice else [],
            'source_slide':pattern.index,'scope':pattern.scope,'background':pattern.background,'objects':objects,'speaker_notes':slide.speaker_notes})
    parts['ppt/presentation.xml']=xml(pres);parts['ppt/_rels/presentation.xml.rels']=xml(pr)
    # Remove stale template thumbnail, notes and metadata relationships from the reachable graph.
    rootrels=parse_xml(parts['_rels/.rels'])
    for rel in list(rootrels):
        if not rel.get('Type','').endswith('/officeDocument'): rootrels.remove(rel)
    parts['_rels/.rels']=xml(rootrels);parts=prune(parts)
    for node in list(types):
        if node.get('PartName') and node.get('PartName').lstrip('/') not in parts: types.remove(node)
    parts['[Content_Types].xml']=xml(types);Path(output).parent.mkdir(parents=True,exist_ok=True);write_package(parts,output)
    return manifest
