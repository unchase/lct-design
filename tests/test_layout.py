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
