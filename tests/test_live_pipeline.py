import json
from pathlib import Path
from PIL import Image
from lct_design.api import create_app
from lct_design.pipeline import run_job,save_json
from lct_design.models import RenderResult
from lct_design.template import analyze_template
from lct_design.provider import save_provider
from fastapi.testclient import TestClient

def setup_job(tmp_path,template,monkeypatch):
    app=create_app(tmp_path/'data',start_worker=False);store=app.state.store
    cfg=save_provider(store.root,{'base_url':'https://example.org/v1','model':'text','vision_model':'vision','vision_enabled':True,'competition_mode':False})
    with TestClient(app) as c:
        tid=c.post('/api/templates',files={'file':('test.pptx',template.read_bytes())}).json()['id']
        job=c.post('/api/jobs',json={'template_id':tid,'mode':'live','slide_count':1,'content':{'title':'Demo','sections':[{'id':'a','title':'Title','bullets':['Fact 125']}]}}).json()
    profile=analyze_template(template);profile.analysis['visual']='complete'
    save_json(store.root/'templates'/tid/'profile.json',profile.model_dump())
    def render(pptx,out,deadline=None):
        out=Path(out);Image.new('RGB',(80,45),'white').save(out/'slide-1.png')
        return RenderResult(status='complete',images=['slide-1.png'])
    monkeypatch.setattr('lct_design.pipeline.render_deck',render)
    return store,job

def test_live_has_one_joint_plan_and_one_batch_audit(tmp_path,template,monkeypatch):
    store,job=setup_job(tmp_path,template,monkeypatch);calls=[]
    def complete(cfg,system,payload,*args,**kwargs):
        calls.append(payload)
        if 'patterns' in payload:
            return {'slides':[{'source_ids':['a'],'layouts':{v:{'pattern_id':'p1','body_slot_ids':['3']} for v in payload['variants']}}]},{'total_tokens':10},cfg.model
        return {'covered':payload['coverage'],'findings':[]},{'total_tokens':20},cfg.vision_model
    monkeypatch.setattr('lct_design.provider.completion',complete)
    result=run_job(store,job)
    assert len(calls)==2
    assert result['inference']['audit']['status']=='complete'
    assert result['usage']['total_tokens']==30
    assert all(v['slides'][0]['layout_source']=='llm' for v in result['variants'])

def test_changed_provider_does_not_reroute_queued_job(tmp_path,template,monkeypatch):
    import pytest
    store,job=setup_job(tmp_path,template,monkeypatch)
    save_provider(store.root,{'base_url':'https://different.org/v1','model':'other','competition_mode':False})
    with pytest.raises(ValueError,match='изменились'):run_job(store,job)

def test_audit_without_explicit_coverage_is_not_success(tmp_path,template,monkeypatch):
    store,job=setup_job(tmp_path,template,monkeypatch)
    def complete(cfg,system,payload,*args,**kwargs):
        if 'patterns' in payload:return {'slides':[{'source_ids':['a'],'layouts':{v:{'pattern_id':'p1','body_slot_ids':['3']} for v in payload['variants']}}]}, {},cfg.model
        return {'findings':[]},{},cfg.vision_model
    monkeypatch.setattr('lct_design.provider.completion',complete)
    result=run_job(store,job)
    assert result['inference']['audit']['status']=='failed'
    assert store.get(job['id'])['status']=='partial'

def test_only_one_layout_repair_and_new_render_is_not_vlm_verified(tmp_path,template,monkeypatch):
    store,job=setup_job(tmp_path,template,monkeypatch);calls=[]
    pth=store.root/'templates'/job['payload']['request']['template_id']/'profile.json'
    p=json.loads(pth.read_text(encoding='utf-8'));p['patterns'].append({**p['patterns'][0],'id':'alternate'});save_json(pth,p)
    def complete(cfg,system,payload,*args,**kwargs):
        calls.append(payload)
        if 'issues' in payload:return {'repairs':[{'variant':'sequential','slide':1,'layout':{'pattern_id':'alternate','body_slot_ids':['3']}}]},{'total_tokens':5},cfg.model
        if 'patterns' in payload:return {'slides':[{'source_ids':['a'],'layouts':{v:{'pattern_id':'p1','body_slot_ids':['3']} for v in payload['variants']}}]},{'total_tokens':10},cfg.model
        return {'covered':payload['coverage'],'findings':[{'variant':'sequential','slide':1,'message':'Use the other composition'}]},{'total_tokens':20},cfg.vision_model
    monkeypatch.setattr('lct_design.provider.completion',complete)
    result=run_job(store,job)
    assert len(calls)==3 and result['usage']['total_tokens']==35
    assert result['variants'][0]['slides'][0]['pattern_id']=='alternate'
    assert result['inference']['repair']['status']=='applied'
    assert result['inference']['audit']['status']=='partial'
    assert (store.root/'jobs'/job['id']/'before-repair/sequential/presentation.pptx').exists()

def test_deadline_preserves_already_generated_variant(tmp_path,template,monkeypatch):
    from lct_design.deadline import BudgetExpired
    store,job=setup_job(tmp_path,template,monkeypatch)
    class Budget:
        def __init__(self,*a):self.calls=0
        def remaining(self,*a):
            self.calls+=1
            if self.calls>3:raise BudgetExpired()
            return 100
    monkeypatch.setattr('lct_design.pipeline.Deadline',Budget)
    monkeypatch.setattr('lct_design.provider.completion',lambda cfg,system,payload,*a,**kw:({'slides':[{'source_ids':['a'],'layouts':{v:{'pattern_id':'p1','body_slot_ids':['3']} for v in payload['variants']}}]}, {},cfg.model))
    result=run_job(store,job)
    assert len(result['variants'])==1 and result['timing']['budget_status']=='exceeded'
    assert store.get(job['id'])['status']=='partial'
    assert (store.root/'jobs'/job['id']/'sequential/presentation.pptx').exists()

def test_second_repair_failure_keeps_first_plan_and_invalidates_audit(tmp_path,template,monkeypatch):
    from lct_design.deadline import BudgetExpired
    from lct_design.pipeline import generate_deck
    store,job=setup_job(tmp_path,template,monkeypatch)
    pth=store.root/'templates'/job['payload']['request']['template_id']/'profile.json'
    p=json.loads(pth.read_text(encoding='utf-8'));p['patterns'].append({**p['patterns'][0],'id':'alternate'});save_json(pth,p)
    def complete(cfg,system,payload,*args,**kwargs):
        if 'issues' in payload:return {'repairs':[{'variant':v,'slide':1,'layout':{'pattern_id':'alternate','body_slot_ids':['3']}} for v in ['comparison','focus']]},{},cfg.model
        if 'patterns' in payload:return {'slides':[{'source_ids':['a'],'layouts':{v:{'pattern_id':'p1','body_slot_ids':['3']} for v in payload['variants']}}]}, {},cfg.model
        return {'covered':payload['coverage'],'findings':[{'variant':v,'slide':1,'message':'Change composition'} for v in ['comparison','focus']]},{},cfg.vision_model
    def generate(template,profile,plan,variant,path,*args):
        if 'repair-candidate' in str(path) and variant=='focus':raise BudgetExpired('Injected second repair timeout')
        return generate_deck(template,profile,plan,variant,path,*args)
    monkeypatch.setattr('lct_design.provider.completion',complete)
    monkeypatch.setattr('lct_design.pipeline.generate_deck',generate)
    result=run_job(store,job);folder=store.root/'jobs'/job['id']
    assert result['inference']['audit']['status']=='partial'
    assert all(c['variant']!='comparison' for c in result['inference']['audit']['coverage'])
    assert result['inference']['repair']['status']=='applied'
    assert result['inference']['repair']['changed_slides']==[{'variant':'comparison','slide':1}]
    assert 'error' in result['inference']['repair']
    assert json.loads((folder/'plan.json').read_text(encoding='utf-8'))['slides'][0]['layouts']['comparison']['pattern_id']=='alternate'
    assert store.get(job['id'])['status']=='partial'
