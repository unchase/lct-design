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
