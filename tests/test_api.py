from fastapi.testclient import TestClient
from lct_design.api import create_app

def test_upload_job_and_unknown_artifact(tmp_path,template):
    with TestClient(create_app(tmp_path/'data',start_worker=False)) as c:
        r=c.post('/api/templates',files={'file':('test.pptx',template.read_bytes(),'application/octet-stream')})
        assert r.status_code==200,r.text
        tid=r.json()['id']
        r=c.post('/api/jobs',json={'template_id':tid,'content':{'title':'Test','sections':[{'id':'s1','title':'One','bullets':['Fact 125']}]} ,'variants':['sequential']})
        assert r.status_code==202,r.text
        j=r.json();assert c.get('/api/jobs/'+j['id']).json()['status']=='queued'
        assert c.get('/api/jobs/'+j['id']+'/artifacts/unknown/secret.txt').status_code==404
        assert c.post('/api/jobs/'+j['id']+'/cancel').status_code==200

def test_reject_remote_origin(tmp_path):
    with TestClient(create_app(tmp_path,start_worker=False)) as c:
        assert c.post('/api/jobs',headers={'Origin':'https://evil.example'},json={}).status_code==403

def test_public_deployment_requires_access_token(tmp_path,monkeypatch):
    monkeypatch.setenv('LCT_ACCESS_TOKEN','local-test-password')
    with TestClient(create_app(tmp_path,start_worker=False)) as c:
        assert c.get('/api/health').status_code==200
        assert c.get('/api/provider').status_code==401
        assert c.get('/api/jobs',auth=('forma','wrong')).status_code==401
        assert c.get('/api/provider',auth=('forma','local-test-password')).status_code==200

def test_configured_https_origin_works_behind_proxy(tmp_path,monkeypatch):
    monkeypatch.setenv('LCT_PUBLIC_URL','https://forma.inflake.fun')
    with TestClient(create_app(tmp_path,start_worker=False)) as c:
        assert c.put('/api/provider',json={},headers={'Origin':'https://forma.inflake.fun'}).status_code==200
        assert c.put('/api/provider',json={},headers={'Origin':'https://other.example'}).status_code==403

def test_template_source_slide_render_is_served_for_comparison(tmp_path):
    from fastapi.testclient import TestClient
    from lct_design.api import create_app
    tid='a'*32;folder=tmp_path/'templates'/tid/'render';folder.mkdir(parents=True)
    (folder/'slide-03.png').write_bytes(b'\x89PNG fake')
    with TestClient(create_app(tmp_path,start_worker=False)) as c:
        assert c.get(f'/api/templates/{tid}/slides/3.png').content==b'\x89PNG fake'
        assert c.get(f'/api/templates/{tid}/slides/4.png').status_code==404
        assert c.get('/api/templates/..%2F..%2Fx/slides/1.png').status_code==404

def test_finished_job_can_be_deleted_with_its_files_but_running_cannot(tmp_path):
    from fastapi.testclient import TestClient
    from lct_design.api import create_app
    app=create_app(tmp_path,start_worker=False)
    with TestClient(app) as c:
        store=app.state.store
        done=store.create({'request':{}});store.update(done['id'],status='completed')
        folder=tmp_path/'jobs'/done['id'];folder.mkdir(parents=True);(folder/'x.txt').write_text('x')
        busy=store.create({'request':{}})
        assert c.delete(f'/api/jobs/{busy["id"]}').status_code==409
        assert c.delete(f'/api/jobs/{done["id"]}').json()=={'deleted':True}
        assert not folder.exists() and c.get(f'/api/jobs/{done["id"]}').status_code==404

def test_preset_briefs_are_listed_and_loadable(tmp_path):
    from fastapi.testclient import TestClient
    from lct_design.api import create_app
    with TestClient(create_app(tmp_path,start_worker=False)) as c:
        items={i['id']:i for i in c.get('/api/examples').json()}
        assert {'demo','medium','large','xlarge'}<=set(items) and items['xlarge']['chars']>items['medium']['chars']
        assert c.get('/api/examples/large').json()['purpose']=='product'
        assert c.get('/api/examples/../x').status_code==404
