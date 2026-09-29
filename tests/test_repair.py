from fastapi.testclient import TestClient
from lct_design.api import create_app
from lct_design.pipeline import run_job

def test_repair_only_selected_and_keeps_parent(tmp_path,template,monkeypatch):
    monkeypatch.setenv('LCT_RENDERER','none')
    app=create_app(tmp_path/'data',start_worker=False)
    with TestClient(app) as c:
        tid=c.post('/api/templates',files={'file':('t.pptx',template.read_bytes())}).json()['id']
        job=c.post('/api/jobs',json={'template_id':tid,'content':{'title':'Long','sections':[{'id':'x','title':'One','bullets':['Long words '*300]},{'id':'y','title':'Two','bullets':['More words '*300]}]},'variants':['sequential']}).json()
        result=run_job(app.state.store,job);original=(app.state.store.root/'jobs'/job['id']/'sequential/presentation.pptx').read_bytes()
        finding=next(f for f in result['variants'][0]['findings'] if f.get('repair'))
        response=c.post(f'/api/jobs/{job["id"]}/repair',json={'variant':'sequential','finding_ids':[finding['id']]})
        assert response.status_code==202,response.text
        child=response.json();assert child['payload']['parent_id']==job['id']
        repaired=run_job(app.state.store,child)
        second=next(f for f in repaired['variants'][0]['findings'] if f.get('repair') and f['slide']==2)
        grandchild=c.post(f'/api/jobs/{child["id"]}/repair',json={'variant':'sequential','finding_ids':[second['id']]}).json()
        assert set(child['payload']['repairs'])<=set(grandchild['payload']['repairs'])
        assert len(grandchild['payload']['repairs'])==2
        assert (app.state.store.root/'jobs'/job['id']/'sequential/presentation.pptx').read_bytes()==original
        assert c.post(f'/api/jobs/{job["id"]}/repair',json={'variant':'sequential','finding_ids':['unknown']}).status_code==422

def test_relayout_repair_moves_slide_to_another_composition(tmp_path,template,monkeypatch):
    monkeypatch.setenv('LCT_RENDERER','none')
    app=create_app(tmp_path/'data',start_worker=False)
    with TestClient(app) as c:
        tid=c.post('/api/templates',files={'file':('t.pptx',template.read_bytes())}).json()['id']
        job=c.post('/api/jobs',json={'template_id':tid,'content':{'title':'T','sections':[{'id':'x','title':'One','bullets':['Short']},{'id':'y','title':'Two','bullets':['Short too']}]},'variants':['sequential']}).json()
        result=run_job(app.state.store,job)
        sparse=[f for f in result['variants'][0]['findings'] if f['rule']=='density.fill' and f.get('repair')=='relayout']
        assert sparse,'sparse slides must be selectable for repair'
        f=sparse[0];before=next(s for s in result['variants'][0]['slides'] if s['number']==f['slide'])['pattern_id']
        child=c.post(f'/api/jobs/{job["id"]}/repair',json={'variant':'sequential','finding_ids':[f['id']]}).json()
        assert child['payload']['repairs']==[f'{f["slide"]}:relayout:{before}']
        repaired=run_job(app.state.store,child)
        after=next(s for s in repaired['variants'][0]['slides'] if s['number']==f['slide'])['pattern_id']
        profile=c.get(f'/api/templates/{tid}/profile').json()
        if len([p for p in profile['patterns'] if p['family'] not in ('guide','code')])>1:assert after!=before
