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
