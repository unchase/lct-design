"""Source-grounded planning with validated template layout selections."""
import re
from pathlib import Path
from .models import ContentPackage,DeckPlan,PlannedSlide,Section,LayoutChoice
PROMPTS=Path(__file__).parent/'prompts'

def model_config():
    from .provider import load_provider,eligibility
    cfg=load_provider();issues=eligibility(cfg)
    if issues:raise ValueError('; '.join(issues))
    return cfg

def infer_json(system,payload,max_tokens=6000,vision=None,config=None,deadline=None):
    from .provider import completion
    return completion(config or model_config(),system,payload,max_tokens,vision,deadline,vision_call=bool(vision))

def catalogue(profile):
    semantics=profile.analysis.get('model_semantics',{}).get('patterns',{})
    return [{'id':p.id,'family':p.family,'background':p.background,'description':semantics.get(p.id,''),
        'slots':[{'id':s.id,'role':s.role,'text_sample':s.text[:100],'font':s.font,'size':s.size,
          'box':[round(s.box.x/profile.width,3),round(s.box.y/profile.height,3),round(s.box.w/profile.width,3),round(s.box.h/profile.height,3)]} for s in p.slots[:30]]}
        for p in profile.patterns if p.family not in ('guide','code')][:100]

def validate_layouts(raw,profile,variants,visual=False):
    from pydantic import ValidationError
    if not isinstance(raw,dict) or set(raw)!=set(variants):raise ValueError('Model layout must cover every requested variant')
    result={}
    for variant,value in raw.items():
        try:choice=LayoutChoice.model_validate(value)
        except ValidationError:raise ValueError('Invalid model layout contract') from None
        p=next((p for p in profile.patterns if p.id==choice.pattern_id),None)
        if p is None:raise ValueError('Unknown model pattern ID')
        slots={s.id:s for s in p.slots if s.role=='body'}
        if len(set(choice.body_slot_ids))!=len(choice.body_slot_ids) or any(i not in slots for i in choice.body_slot_ids):raise ValueError('Invalid body slot IDs')
        if visual and len(choice.body_slot_ids)!=1:raise ValueError('Visual layout needs exactly one body slot')
        boxes=[slots[i].box for i in choice.body_slot_ids]+[s.box for s in p.slots if s.role=='title']
        from itertools import combinations
        if any(b.x<0 or b.y<0 or b.x+b.w>profile.width+1 or b.y+b.h>profile.height+1 for b in boxes):raise ValueError('Model layout extends outside slide')
        for a,b in combinations(boxes,2):
            overlap=max(0,min(a.x+a.w,b.x+b.w)-max(a.x,b.x))*max(0,min(a.y+a.h,b.y+b.h)-max(a.y,b.y))
            if overlap>min(a.w*a.h,b.w*b.h)*.03:raise ValueError('Model layout contains overlapping slots')
        result[variant]=choice
    return result

def plan_content(content:ContentPackage,profile,slide_count:int,mode:str,config=None,deadline=None,variants=None)->DeckPlan:
    variants=variants or ['sequential','comparison','focus']
    sections=list(content.sections)
    if not sections:
        lines=[s.strip(' #-*\t') for s in re.split(r'\n\s*\n|\n',content.brief) if s.strip()]
        if not lines:raise ValueError('Add source content or a brief')
        sections=[Section(id=f'brief-{i+1}',title=line[:100],bullets=[line]) for i,line in enumerate(lines)]
    warnings=[];usage={};model=None
    if mode=='live':
        payload={'title':content.title,'purpose':content.purpose,'language':content.language,'slide_count':slide_count,
                 'sources':[{**s.model_dump(exclude={'image'}),'has_image':bool(s.image)} for s in sections],'patterns':catalogue(profile),'variants':variants}
        prompt=(PROMPTS/'plan.md').read_text(encoding='utf-8')+'\n'+(PROMPTS/'design-principles.md').read_text(encoding='utf-8')
        data,usage,model=infer_json(prompt,payload,config=config,deadline=deadline) if config or deadline else infer_json(prompt,payload)
        mapping={s.id:s for s in sections};out=[];covered=[]
        if not isinstance(data.get('slides'),list):raise ValueError('Model plan must contain slides')
        for item in data['slides']:
            if not isinstance(item,dict):raise ValueError('Invalid model slide')
            ids=item.get('source_ids',[])
            if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in mapping for i in ids):raise ValueError('Model plan contains unknown source IDs')
            if len(ids)>1 and any(mapping[i].chart or mapping[i].table or mapping[i].diagram or mapping[i].image for i in ids):raise ValueError('Visual source must stay on its own slide')
            src=[mapping[i] for i in ids];covered.extend(ids)
            title=item.get('title',src[0].title)
            if title not in [s.title for s in src]:title=src[0].title
            s=src[0];layouts=validate_layouts(item.get('layouts'),profile,variants,bool(s.chart or s.table or s.diagram or s.image))
            out.append(PlannedSlide(title=title,source_ids=ids,bullets=[b for section in src for b in section.bullets],
                table=s.table,chart=s.chart,diagram=s.diagram,diagram_kind=s.diagram_kind,diagram_parents=s.diagram_parents,diagram_assistant=s.diagram_assistant,image=s.image,layouts=layouts))
        if set(covered)!=set(mapping) or len(covered)!=len(set(covered)) or not 1<=len(out)<=50:raise ValueError('Model plan must include each source exactly once (1–50 slides)')
    else:
        out=[PlannedSlide(title=s.title,source_ids=[s.id],bullets=s.bullets,table=s.table,chart=s.chart,
            diagram=s.diagram,diagram_kind=s.diagram_kind,diagram_parents=s.diagram_parents,diagram_assistant=s.diagram_assistant,image=s.image) for s in sections]
        warnings.append('Диагностический режим: структура собрана из исходных разделов без LLM; смысловой аудит не выполнен.')
    if len(out)!=slide_count:warnings.append(f'Запрошено {slide_count} слайдов; сохранены {len(out)} исходных разделов без выдумывания и потери данных.')
    from .speech import speaker_text
    for slide in out:slide.speaker_notes=speaker_text(slide)
    return DeckPlan(title=content.title,slides=out,mode=mode,model=model,usage=usage,warnings=warnings)
