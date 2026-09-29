from lct_design.audit import audit_deck
from lct_design.models import RenderResult

def manifest():
    return {'width':1000,'height':600,'slides':[{'number':1,'background':'FFFFFF','objects':[{'id':'1','role':'body-0','box':{'x':900,'y':10,'w':200,'h':80},'text':'Text','overflow':True,'size':20,'color':'111111'}]}]}

def test_missing_renderer_never_passes():
    findings=audit_deck(manifest(),RenderResult(status='unavailable',error='missing'))
    assert any(f.rule=='render.available' and f.status=='not_run' for f in findings)
    assert any(f.rule=='layout.bounds' for f in findings)
    assert any(f.rule=='text.fit' and f.repair=='refit' for f in findings)

def test_overlap_excludes_containment():
    m=manifest();m['slides'][0]['objects']=[{'id':'1','role':'body','box':{'x':10,'y':10,'w':100,'h':100},'text':'A'}, {'id':'2','role':'body','box':{'x':50,'y':50,'w':100,'h':100},'text':'B'}]
    assert any(f.rule=='layout.overlap' for f in audit_deck(m,RenderResult(status='unavailable')))
def test_render_text_loss_is_visible(tmp_path):
    from lct_design.audit import audit_rendered_text
    manifest={'width':1000,'height':500,'slides':[{'number':1,'objects':[{'id':'1','role':'body','text':'Revenue 125 million','box':{'x':20,'y':20,'w':400,'h':200}}]}]}
    findings=audit_rendered_text(manifest,['Revenue'])
    assert any(f.rule=='render.text_missing' and f.severity=='error' for f in findings)
    assert not audit_rendered_text(manifest,['Revenue 125 million'])
def test_non_text_overflow_has_no_noop_repair():
    from lct_design.audit import audit_deck
    from lct_design.models import RenderResult
    manifest={'width':1000,'height':500,'slides':[{'number':1,'objects':[{'id':'t','role':'table','text':'x','box':{'x':20,'y':20,'w':400,'h':200},'overflow':True}]}]}
    fit=next(f for f in audit_deck(manifest,RenderResult(status='unavailable')) if f.rule=='text.fit')
    assert fit.repair is None

def test_fill_ratio_and_template_artwork_overlap_are_reported():
    from lct_design.audit import audit_deck
    from lct_design.models import RenderResult
    w,h=12192000,6858000
    title={'id':'1','role':'title','box':{'x':500000,'y':300000,'w':8000000,'h':800000},'text':'Вывод','size':32}
    sparse={'number':2,'objects':[title,{'id':'2','role':'body-0','box':{'x':500000,'y':1500000,'w':3000000,'h':1000000},'text':'Одна строка','size':12}]}
    covered={'number':3,'artwork':[{'x':6000000,'y':1500000,'w':5000000,'h':4000000}],
             'objects':[title,{'id':'3','role':'chart','box':{'x':5500000,'y':1500000,'w':6000000,'h':4500000},'text':'','overflow':False}]}
    rules={(f.rule,f.slide) for f in audit_deck({'width':w,'height':h,'slides':[sparse,covered]},RenderResult(status='unavailable'))}
    assert ('density.fill',2) in rules and ('layout.artwork',3) in rules and ('layout.artwork',2) not in rules

def test_model_layout_over_template_artwork_is_rejected(template):
    import pytest
    from lct_design.models import Box
    from lct_design.planner import validate_layouts
    from lct_design.template import analyze_template
    p=analyze_template(template);slot=next(s for s in p.patterns[0].slots if s.role=='body')
    p.patterns[0].artwork=[slot.box.model_copy()]
    with pytest.raises(ValueError,match='artwork'):
        validate_layouts({'sequential':{'pattern_id':p.patterns[0].id,'body_slot_ids':[slot.id]}},p,['sequential'])
