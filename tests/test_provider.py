import json
import pytest
from fastapi.testclient import TestClient
from lct_design.api import create_app

def test_provider_key_is_private_and_endpoint_change_drops_it(tmp_path):
    with TestClient(create_app(tmp_path,start_worker=False)) as c:
        values={'provider':'openrouter','base_url':'https://openrouter.ai/api/v1','model':'vendor/model','api_key':'private-example-key','competition_mode':False}
        r=c.put('/api/provider',json=values)
        assert r.status_code==200,r.text
        assert r.json()['has_key'] and 'private-example-key' not in r.text
        assert 'api_key' not in c.get('/api/provider').json()
        revision=r.json()['revision']
        values['api_key']='';values['model']='vendor/new'
        assert c.put('/api/provider',json=values).json()['has_key']
        values.update(provider='custom',base_url='https://another.example/v1')
        changed=c.put('/api/provider',json=values).json()
        assert not changed['has_key'] and changed['revision']!=revision
        assert c.delete('/api/provider').status_code==200
        assert not c.get('/api/provider').json()['has_key']

def test_provider_invalid_input_never_echoes_key(tmp_path):
    with TestClient(create_app(tmp_path,start_worker=False)) as c:
        r=c.put('/api/provider',json={'api_key':'SECRET-MUST-NOT-ECHO','base_url':'https://u:password@example.org/v1'})
        assert r.status_code==422 and 'SECRET-MUST-NOT-ECHO' not in r.text and 'password' not in r.text

def test_competition_metadata_and_vision_are_independently_validated(tmp_path):
    from lct_design.provider import ProviderConfig,eligibility
    cfg=ProviderConfig(base_url='https://example.org/v1',model='text',vision_enabled=True,vision_model='vision',model_license='MIT',model_parameters_b=20,model_card='https://example.org/card')
    assert any('визуаль' in e.lower() for e in eligibility(cfg))

def test_provider_errors_do_not_expose_response_secrets(tmp_path,monkeypatch):
    import httpx
    from lct_design import provider
    monkeypatch.setattr(provider,'TRANSPORT',httpx.MockTransport(lambda r:httpx.Response(401,json={'error':'provider secret echoed'})))
    with TestClient(create_app(tmp_path,start_worker=False)) as c:
        c.put('/api/provider',json={'base_url':'https://example.org/v1','model':'test','competition_mode':False,'api_key':'secret'})
        r=c.post('/api/provider/test')
        assert r.status_code==200 and not r.json()['ok']
        assert 'provider secret echoed' not in r.text and '401' in r.text

def test_openrouter_requires_key_but_local_server_does_not():
    from lct_design.provider import ProviderConfig,eligibility
    meta=dict(model='qwen/qwen3.8-27b',model_license='Apache-2.0',model_parameters_b=27.8,model_card='https://huggingface.co/Qwen/Qwen3.8-27B')
    assert any('ключ' in e.lower() for e in eligibility(ProviderConfig(base_url='https://openrouter.ai/api/v1',**meta)))
    assert not eligibility(ProviderConfig(base_url='https://openrouter.ai/api/v1',api_key='sk-test',**meta))
    assert not eligibility(ProviderConfig(base_url='http://localhost:8080/v1',**meta))

def test_environment_openrouter_preset_is_labelled_and_waits_for_key(monkeypatch,tmp_path):
    from lct_design.provider import load_provider,eligibility
    monkeypatch.setenv('LCT_API_BASE','https://openrouter.ai/api/v1');monkeypatch.setenv('LCT_MODEL','qwen/qwen3.8-27b');monkeypatch.delenv('LCT_API_KEY',raising=False)
    cfg=load_provider(tmp_path)
    assert cfg.provider=='openrouter' and any('ключ' in e.lower() for e in eligibility(cfg))

def test_reasoning_is_disabled_per_provider_dialect_and_exhaustion_is_explained(monkeypatch):
    import httpx,json as j,pytest
    from lct_design import provider
    from lct_design.provider import ProviderConfig,completion
    sent=[]
    def reply(r):
        sent.append(j.loads(r.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'}}]})
    monkeypatch.setattr(provider,'TRANSPORT',httpx.MockTransport(reply))
    completion(ProviderConfig(base_url='https://openrouter.ai/api/v1',model='m',api_key='k'),'s',{})
    completion(ProviderConfig(base_url='http://localhost:8000/v1',model='m'),'s',{})
    completion(ProviderConfig(base_url='http://localhost:8000/v1',model='m',disable_reasoning=False),'s',{})
    assert sent[0]['reasoning']=={'enabled':False} and 'chat_template_kwargs' not in sent[0]
    assert sent[1]['chat_template_kwargs']=={'enable_thinking':False} and 'reasoning' not in sent[1]
    assert 'reasoning' not in sent[2] and 'chat_template_kwargs' not in sent[2]
    monkeypatch.setattr(provider,'TRANSPORT',httpx.MockTransport(lambda r:httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'','reasoning':'long thoughts'}}]})))
    with pytest.raises(ValueError,match='рассужден'):
        completion(ProviderConfig(base_url='http://localhost:8000/v1',model='m',disable_reasoning=False),'s',{})

def test_openrouter_balance_combines_account_and_key_limits(tmp_path,monkeypatch):
    import httpx
    from lct_design import provider
    def reply(r):
        if r.url.path.endswith('/credits'):return httpx.Response(200,json={'data':{'total_credits':200,'total_usage':171.33}})
        return httpx.Response(200,json={'data':{'limit':50,'limit_remaining':12.5,'usage':37.5,'usage_daily':0.09}})
    monkeypatch.setattr(provider,'TRANSPORT',httpx.MockTransport(reply))
    with TestClient(create_app(tmp_path,start_worker=False)) as c:
        c.put('/api/provider',json={'base_url':'https://example.org/v1','model':'m','competition_mode':False})
        assert c.get('/api/provider/balance').json()=={'available':False,'reason':'Баланс доступен только для OpenRouter'}
        c.put('/api/provider',json={'provider':'openrouter','base_url':'https://openrouter.ai/api/v1','model':'m','competition_mode':False,'api_key':'sk-secret'})
        b=c.get('/api/provider/balance').json()
        assert b=={'available':True,'balance':28.67,'total_credits':200.0,'key_limit_remaining':12.5,'key_usage_daily':0.09}
        assert 'sk-secret' not in c.get('/api/provider/balance').text
