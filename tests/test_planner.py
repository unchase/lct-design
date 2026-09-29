import base64,io
import pytest
from PIL import Image
from lct_design.models import ContentPackage,Section
from lct_design.planner import plan_content
from lct_design.template import analyze_template

def test_live_plan_cannot_merge_away_image(template,monkeypatch):
    buf=io.BytesIO();Image.new('RGB',(4,4),'red').save(buf,format='PNG')
    content=ContentPackage(title='x',sections=[Section(id='a',title='A',bullets=['A']),Section(id='b',title='B',image='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode())])
    monkeypatch.setattr('lct_design.planner.infer_json',lambda *args:({'slides':[{'source_ids':['a','b'],'title':'A'}]}, {},'test'))
    with pytest.raises(ValueError,match='Visual source'):plan_content(content,analyze_template(template),1,'live')

def test_live_plan_selects_patterns_and_export_uses_slots(template,tmp_path,monkeypatch):
    from lct_design.exporter import generate_deck
    p=analyze_template(template);p.patterns.append(p.patterns[0].model_copy(update={'id':'alternative'}))
    layouts={v:{'pattern_id':'alternative','body_slot_ids':['3']} for v in ('sequential','comparison','focus')}
    def response(*args,**kwargs):
        assert 'patterns' in args[1] and 'variants' in args[1]
        return {'slides':[{'source_ids':['a'],'title':'Title','layouts':layouts}]},{'total_tokens':123},'test'
    monkeypatch.setattr('lct_design.planner.infer_json',response)
    plan=plan_content(ContentPackage(title='x',sections=[Section(id='a',title='Title',bullets=['Exact fact 125'])]),p,1,'live')
    for v in layouts:
        manifest=generate_deck(template,p,plan,v,tmp_path/(v+'.pptx'))
        assert manifest['slides'][0]['pattern_id']=='alternative'
        assert manifest['slides'][0]['layout_source']=='llm'
        slot=p.patterns[0].slots[1].box;box=manifest['slides'][0]['objects'][1]['box']
        if v=='sequential':assert box==slot.model_dump()
        # Variant axes re-divide the chosen region but never leave it.
        else:assert slot.x<=box['x'] and slot.y<=box['y'] and box['x']+box['w']<=slot.x+slot.w+1 and box['y']+box['h']<=slot.y+slot.h+1

@pytest.mark.parametrize('choice',[{'pattern_id':'invented','body_slot_ids':['3']},{'pattern_id':'p1','body_slot_ids':['2']},{'pattern_id':'p1','body_slot_ids':['3','3']}])
def test_live_rejected_layout_falls_back_per_variant_without_failing_deck(template,monkeypatch,choice):
    monkeypatch.setattr('lct_design.planner.infer_json',lambda *a,**kw:({'slides':[{'source_ids':['a'],'layouts':{'sequential':{'pattern_id':'p1','body_slot_ids':['3']},'comparison':choice,'focus':choice}}]}, {},'test'))
    plan=plan_content(ContentPackage(title='x',sections=[Section(id='a',title='A',bullets=['fact'])]),analyze_template(template),1,'live')
    assert set(plan.slides[0].layouts)=={'sequential'}
    assert sum('детерминированный выбор' in w for w in plan.warnings)==2

def test_diversify_caps_one_pattern_and_keeps_focus_single_region():
    from lct_design.models import PlannedSlide,LayoutChoice
    from lct_design.planner import diversify
    slides=[PlannedSlide(title=str(i),source_ids=[str(i)],layouts={'sequential':LayoutChoice(pattern_id='p24',body_slot_ids=['1']),
        'focus':LayoutChoice(pattern_id='p9',body_slot_ids=['1','2'])}) for i in range(12)]
    warnings=[];diversify(slides,['sequential','focus'],warnings)
    assert sum('sequential' in s.layouts for s in slides)==5 and not any('focus' in s.layouts for s in slides) and len(warnings)==2

def test_small_icon_in_text_card_is_allowed_but_photo_is_not(template):
    import pytest
    from lct_design.models import Box
    from lct_design.planner import validate_layouts
    from lct_design.template import analyze_template
    p=analyze_template(template);slot=next(s for s in p.patterns[0].slots if s.role=='body');b=slot.box
    choice={'sequential':{'pattern_id':p.patterns[0].id,'body_slot_ids':[slot.id]}}
    p.patterns[0].artwork=[Box(x=b.x+b.w*.8,y=b.y+b.h*.8,w=b.w*.1,h=b.h*.1)]
    validate_layouts(choice,p,['sequential'])
    p.patterns[0].artwork=[Box(x=b.x,y=b.y,w=b.w*.8,h=b.h*.8)]
    with pytest.raises(ValueError,match='artwork'):validate_layouts(choice,p,['sequential'])
