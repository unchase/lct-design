from lct_design.models import Box,Slot,Pattern,TemplateProfile
from lct_design.layout import body_boxes

def test_visual_uses_main_region_not_photo_caption():
    p=Pattern(id='p',part='p',index=1,scope='m',slots=[
        Slot(id='t',role='title',box=Box(x=50,y=70,w=430,h=150)),
        Slot(id='b',box=Box(x=510,y=130,w=420,h=730)),
        Slot(id='photo',box=Box(x=220,y=630,w=100,h=60))])
    profile=TemplateProfile(hash='h',filename='f',width=1000,height=1000,colors=[],fonts=[],font_sizes=[],patterns=[p])
    b=body_boxes(p,profile,'sequential',True)[0]
    assert b.w>=420
    assert b.h>=400

def test_title_only_pattern_has_useful_content_region():
    p=Pattern(id='p',part='p',index=1,scope='m',slots=[Slot(id='t',role='title',box=Box(x=50,y=70,w=850,h=150))])
    profile=TemplateProfile(hash='h',filename='f',width=1000,height=1000,colors=[],fonts=[],font_sizes=[],patterns=[p])
    b=body_boxes(p,profile,'sequential')[0]
    assert b.y>=220 and b.w>=800 and b.h>=500
def test_sparse_template_font_scale_still_fits_content():
    from lct_design.layout import fit_text
    from lct_design.models import Box
    size,overflow=fit_text('Readable content '*20,Box(x=0,y=0,w=6000000,h=2400000),32,[32,44])
    assert not overflow
    assert 12<=size<32

def test_comparison_does_not_use_small_footer_as_second_column():
    from lct_design.models import Box,Slot,Pattern,TemplateProfile
    from lct_design.layout import body_boxes
    p=Pattern(id='p',part='slide',index=1,scope='theme',slots=[
        Slot(id='1',role='title',box=Box(x=50,y=20,w=900,h=100)),
        Slot(id='2',box=Box(x=50,y=180,w=500,h=250)),
        Slot(id='3',box=Box(x=700,y=620,w=100,h=100))])
    profile=TemplateProfile(hash='x',filename='x',width=1000,height=750,colors=[],fonts=[],font_sizes=[],patterns=[p])
    boxes=body_boxes(p,profile,'comparison')
    assert len(boxes)==2
    assert max(b.y for b in boxes)<400
    assert all(b.w>=200 for b in boxes)

def test_text_layout_prefers_canvas_without_sample_screenshot():
    from lct_design.models import Box,Slot,Pattern,TemplateProfile,PlannedSlide
    from lct_design.layout import select_pattern
    slots=[Slot(id='1',role='title',box=Box(x=50,y=20,w=900,h=100)),Slot(id='2',box=Box(x=50,y=180,w=900,h=500))]
    photo=Pattern(id='photo',part='a',index=1,scope='t',slots=slots,complexity=2)
    clean=Pattern(id='clean',part='b',index=2,scope='t',slots=slots,complexity=4)
    profile=TemplateProfile(hash='x',filename='x',width=1000,height=750,colors=[],fonts=[],font_sizes=[],patterns=[photo,clean])
    regions={'photo':[Box(x=50,y=180,w=900,h=500)],'clean':[]}
    for variant in ('sequential','comparison','focus'):
        assert select_pattern(profile,PlannedSlide(title='Title',source_ids=['x']),variant,0,regions).id=='clean'

def test_caption_layout_is_not_expanded_across_decorative_cards():
    from lct_design.models import Box,Slot,Pattern,TemplateProfile,PlannedSlide
    from lct_design.layout import select_pattern
    title=Slot(id='1',role='title',box=Box(x=50,y=20,w=900,h=100))
    cards=Pattern(id='cards',part='a',index=1,scope='t',complexity=2,slots=[title,Slot(id='2',box=Box(x=100,y=400,w=150,h=30))])
    clean=Pattern(id='clean',part='b',index=2,scope='t',complexity=4,slots=[title,Slot(id='2',box=Box(x=50,y=180,w=900,h=500))])
    profile=TemplateProfile(hash='x',filename='x',width=1000,height=750,colors=[],fonts=[],font_sizes=[],patterns=[cards,clean])
    for variant in ('sequential','comparison','focus'):
        assert select_pattern(profile,PlannedSlide(title='Title',source_ids=['x']),variant,0).id=='clean'

def test_real_card_body_does_not_expand_across_other_cards():
    from lct_design.models import Box,Slot,Pattern,TemplateProfile
    from lct_design.layout import body_boxes
    card=Box(x=40,y=200,w=320,h=420)
    pattern=Pattern(id='p',part='p',index=1,scope='t',slots=[Slot(id='1',role='title',box=Box(x=40,y=20,w=900,h=100)),Slot(id='2',box=card),Slot(id='3',box=Box(x=420,y=200,w=500,h=60))])
    profile=TemplateProfile(hash='x',filename='x',width=1000,height=750,colors=[],fonts=[],font_sizes=[],patterns=[pattern])
    for visual in (False,True):
        assert body_boxes(pattern,profile,'sequential',visual)[0]==card

def test_narrow_title_does_not_exclude_clear_body_layout():
    from lct_design.models import PlannedSlide
    from lct_design.layout import select_pattern
    clean=Pattern(id='clean',part='a',index=1,scope='t',slots=[Slot(id='t',role='title',box=Box(x=20,y=20,w=440,h=100)),Slot(id='b',box=Box(x=520,y=180,w=430,h=500))])
    photo=Pattern(id='photo',part='b',index=2,scope='t',slots=[Slot(id='t',role='title',box=Box(x=20,y=20,w=740,h=100)),Slot(id='b',box=Box(x=20,y=180,w=320,h=500))])
    profile=TemplateProfile(hash='x',filename='x',width=1000,height=750,colors=[],fonts=[],font_sizes=[],patterns=[clean,photo])
    assert select_pattern(profile,PlannedSlide(title='Title',source_ids=['x']),'sequential',0,{'clean':[],'photo':[Box(x=20,y=200,w=300,h=400)]}).id=='clean'

def test_text_slides_avoid_media_frames_that_would_stay_empty(template):
    import pytest
    from lct_design.layout import select_pattern
    from lct_design.models import Box,PlannedSlide
    from lct_design.planner import validate_layouts
    from lct_design.template import analyze_template
    p=analyze_template(template);framed=p.patterns[0].model_copy(update={'id':'framed','frames':[Box(x=0,y=0,w=p.width/2,h=p.height/2)]})
    p.patterns=[framed,p.patterns[0]]
    text=PlannedSlide(title='T',source_ids=['a'],bullets=['x'])
    assert select_pattern(p,text,'sequential',0).id!='framed'
    body=next(s.id for s in framed.slots if s.role=='body')
    with pytest.raises(ValueError,match='media frame'):
        validate_layouts({'sequential':{'pattern_id':'framed','body_slot_ids':[body]}},p,['sequential'])

def test_media_frame_detected_behind_insert_photo_prompt():
    from lxml import etree as ET
    from lct_design.models import Box,Slot
    from lct_design.template import media_frames
    ns='xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    xml=f'<p:sld {ns}><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="5" name="r"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="6000000" y="1000000"/><a:ext cx="5000000" cy="4000000"/></a:xfrm><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill></p:spPr></p:sp></p:spTree></p:cSld></p:sld>'
    prompt=Slot(id='6',role='body',box=Box(x=7000000,y=3000000,w=2000000,h=500000),text='Вставить\nфото')
    card=Slot(id='7',role='body',box=Box(x=6100000,y=1100000,w=4800000,h=3800000),text='Пункт карточки')
    tree=ET.fromstring(xml)
    assert len(media_frames(tree,[prompt],12192000,6858000))==1
    assert media_frames(tree,[card],12192000,6858000)==[]

def test_card_rows_receive_text_and_tiny_slots_refuse_visuals(template):
    import pytest
    from lct_design.layout import body_boxes,card_row
    from lct_design.models import Box,Slot
    from lct_design.planner import validate_layouts
    from lct_design.template import analyze_template
    p=analyze_template(template);base=p.patterns[0];W,H=p.width,p.height
    title=next(s for s in base.slots if s.role=='title')
    cards=[Slot(id=str(40+i),role='body',box=Box(x=W*(.05+.31*i),y=H*.3,w=W*.28,h=H*.5)) for i in range(3)]
    tiny=Slot(id='50',role='body',box=Box(x=W*.7,y=H*.1,w=W*.1,h=H*.03))
    grid=base.model_copy(update={'id':'grid','slots':[title,*cards,tiny]})
    p.patterns=[grid]
    assert len(card_row(grid,p))==3 and len(body_boxes(grid,p,'sequential'))==3
    assert len(body_boxes(grid,p,'focus'))==1
    with pytest.raises(ValueError,match='too small'):
        validate_layouts({'sequential':{'pattern_id':'grid','body_slot_ids':['50']}},p,['sequential'],visual=True)

def test_visual_accent_contrasts_with_slide_background():
    from lct_design.audit import contrast
    from lct_design.exporter import visual_accent
    colors=['0077FF','FFFFFF','FF3985','111111']
    assert visual_accent(colors,'FFFFFF')=='0077FF'
    assert contrast(visual_accent(colors,'0077FF'),'0077FF')>=3
