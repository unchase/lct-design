"""Local operator configuration and bounded OpenAI-compatible transport.

The private settings file is never an artifact. No raw provider error is exposed.
"""
import asyncio,base64,hashlib,io,json,os,time,uuid
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
import httpx
from pydantic import BaseModel,ConfigDict,Field,SecretStr,model_validator
from .deadline import BudgetExpired

TRANSPORT=None  # Injected only by transport tests.

class ReasoningExhausted(Exception):pass

class ProviderConfig(BaseModel):
    model_config=ConfigDict(extra='forbid')
    provider:Literal['custom','openrouter']='custom'
    base_url:str=''
    model:str=Field(default='',max_length=200)
    api_key:SecretStr=SecretStr('')
    vision_enabled:bool=False
    vision_model:str=Field(default='',max_length=200)
    json_mode:bool=True
    disable_reasoning:bool=True  # Qwen3-class models otherwise spend the token budget thinking.
    competition_mode:bool=True
    model_license:str=''
    model_parameters_b:float=Field(default=0,ge=0,le=10000,allow_inf_nan=False)
    model_card:str=''
    vision_license:str=''
    vision_parameters_b:float=Field(default=0,ge=0,le=10000,allow_inf_nan=False)
    vision_card:str=''
    revision:str=''

    @model_validator(mode='after')
    def endpoint(self):
        self.base_url=self.base_url.strip().rstrip('/')
        if self.base_url:
            u=urlsplit(self.base_url)
            if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.query or u.fragment:
                raise ValueError('Нужен HTTP(S) Base URL без учётных данных, query и fragment')
            import ipaddress
            try:addr=ipaddress.ip_address(u.hostname)
            except ValueError:addr=None
            if addr and (addr.is_link_local or addr.is_unspecified or addr.is_multicast):
                raise ValueError('Этот адрес не подходит для inference API')
        if len(self.api_key.get_secret_value())>4096:raise ValueError('Слишком длинный ключ')
        return self

def is_openrouter(url):
    host=urlsplit(url or '').hostname or ''
    return host=='openrouter.ai' or host.endswith('.openrouter.ai')

def eligibility(cfg):
    issues=[]
    if not cfg.base_url or not cfg.model:issues.append('Укажите Base URL и ID текстовой модели')
    if is_openrouter(cfg.base_url) and not cfg.api_key.get_secret_value():issues.append('Укажите ключ OpenRouter')
    if cfg.vision_enabled and not cfg.vision_model:issues.append('Укажите ID визуальной модели')
    if cfg.competition_mode:
        def valid(license,size,card):return license in ('MIT','Apache-2.0') and 0<size<=35 and urlsplit(card).scheme in ('https','http')
        if not valid(cfg.model_license,cfg.model_parameters_b,cfg.model_card):issues.append('Текстовая модель: нужны MIT/Apache-2.0, не более 35B параметров и карточка модели')
        if cfg.vision_enabled and not valid(cfg.vision_license,cfg.vision_parameters_b,cfg.vision_card):issues.append('Визуальная модель: нужны MIT/Apache-2.0, не более 35B параметров и карточка модели')
    return issues

def private_data(cfg):
    data=cfg.model_dump(mode='json');data['api_key']=cfg.api_key.get_secret_value();return data

def load_provider(root=None):
    path=Path(root)/'provider.private.json' if root is not None else None
    if path and path.exists():return ProviderConfig.model_validate_json(path.read_text(encoding='utf-8'))
    base=os.getenv('LCT_API_BASE','')
    cfg=ProviderConfig(provider='openrouter' if is_openrouter(base.strip()) else 'custom',base_url=base,model=os.getenv('LCT_MODEL',''),api_key=os.getenv('LCT_API_KEY',''),
        model_license=os.getenv('LCT_MODEL_LICENSE',''),model_parameters_b=float(os.getenv('LCT_MODEL_PARAMETERS_B','0') or '0'),
        model_card=os.getenv('LCT_MODEL_CARD',''),competition_mode=os.getenv('LCT_COMPETITION_MODE','true').lower()!='false',
        vision_enabled=os.getenv('LCT_VISION_ENABLED','false').lower()=='true',vision_model=os.getenv('LCT_VISION_MODEL',''),
        vision_license=os.getenv('LCT_VISION_LICENSE',''),vision_parameters_b=float(os.getenv('LCT_VISION_PARAMETERS_B','0') or '0'),vision_card=os.getenv('LCT_VISION_CARD',''),
        disable_reasoning=os.getenv('LCT_DISABLE_REASONING','true').lower()!='false')
    cfg.revision='env-'+hashlib.sha256(json.dumps(private_data(cfg),sort_keys=True).encode()).hexdigest()[:20]
    return cfg

def public_data(cfg):
    data=cfg.model_dump(mode='json',exclude={'api_key'});data.update(has_key=bool(cfg.api_key.get_secret_value()),ready=not eligibility(cfg),issues=eligibility(cfg))
    return data

def save_provider(root,values):
    old=load_provider(root);values=dict(values);clear=values.pop('clear_key',False)
    values.pop('revision',None)
    cfg=ProviderConfig.model_validate(values)
    if not clear and not cfg.api_key.get_secret_value() and cfg.base_url==old.base_url:cfg.api_key=old.api_key
    if clear:cfg.api_key=SecretStr('')
    cfg.revision=uuid.uuid4().hex
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    temporary=root/('provider-'+uuid.uuid4().hex+'.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(private_data(cfg),f,ensure_ascii=False)
        os.replace(temporary,root/'provider.private.json')
    finally:temporary.unlink(missing_ok=True)
    return cfg

async def _request(cfg,path,body,timeout):
    headers={}
    if cfg.api_key.get_secret_value():headers['Authorization']='Bearer '+cfg.api_key.get_secret_value()
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(timeout=timeout,follow_redirects=False,trust_env=False,transport=TRANSPORT) as client:
                async with client.stream('GET' if body is None else 'POST',cfg.base_url+path,headers=headers,json=body) as response:
                    if not 200<=response.status_code<300:raise ValueError(f'Inference API: HTTP {response.status_code}. Проверьте адрес, ключ и доступ к модели.')
                    raw=bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw)>4*1024*1024:raise ValueError('Ответ inference API превышает 4 МБ')
                    try:return json.loads(raw)
                    except ValueError:raise ValueError('Inference API вернул не JSON') from None
    except (TimeoutError,httpx.TimeoutException):raise BudgetExpired('Истекло время ожидания inference API') from None
    except httpx.RequestError as exc:raise ValueError(f'Inference API недоступен ({type(exc).__name__}). Проверьте адрес и сетевое соединение.') from None

def request(cfg,path,body=None,timeout=75,deadline=None):
    if not cfg.base_url:raise ValueError('Не задан Base URL')
    requested=timeout;timeout=deadline.remaining(timeout) if deadline else timeout
    try:return asyncio.run(_request(cfg,path,body,timeout))
    except BudgetExpired:
        # Only a call cut short by the shared budget exhausts it; a slow single call is a model error.
        if deadline is not None and timeout<requested:raise
        raise ValueError(f'Inference API не ответил за {requested:.0f} с; повторите генерацию') from None

def completion(cfg,system,payload,max_tokens=6000,vision=None,deadline=None,vision_call=False,cap=75):
    content=json.dumps(payload,ensure_ascii=False)
    if len(content)>250000:raise ValueError('Контекст превышает лимит 250000 символов; сократите материалы')
    if vision:content=[{'type':'text','text':content},*vision]
    model=cfg.vision_model if vision_call else cfg.model
    body={'model':model,'messages':[{'role':'system','content':system},{'role':'user','content':content}],
        'temperature':.2,'max_tokens':max_tokens}
    if cfg.json_mode:body['response_format']={'type':'json_object'}
    if cfg.disable_reasoning:
        if is_openrouter(cfg.base_url):body['reasoning']={'enabled':False}
        else:body['chat_template_kwargs']={'enable_thinking':False}  # vLLM/SGLang dialect
    # OpenRouter routes one model to many hosts with very different speed; prefer the fastest.
    if is_openrouter(cfg.base_url):body['provider']={'sort':'throughput'}
    result=request(cfg,'/chat/completions',body,timeout=cap,deadline=deadline)
    try:
        choice=result['choices'][0];raw=choice['message']['content']
        if not (raw or '').strip() and (choice['message'].get('reasoning') or choice.get('finish_reason')=='length'):
            raise ReasoningExhausted()
        import re
        data=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',raw.strip()))
        if not isinstance(data,dict):raise ValueError()
        usage={k:v for k,v in result.get('usage',{}).items() if isinstance(v,(int,float)) and k in ('prompt_tokens','completion_tokens','total_tokens','cost')}
        return data,usage,model
    except ReasoningExhausted:raise ValueError('Модель израсходовала лимит токенов на рассуждения и не дала ответа; включите «Отключить рассуждения модели»') from None
    except (KeyError,IndexError,TypeError,ValueError,AttributeError):raise ValueError('Модель вернула ответ вне JSON-контракта; проверьте поддержку JSON и лимит токенов') from None

def install_routes(app,root):
    from fastapi import HTTPException,Request
    from pydantic import ValidationError
    @app.get('/api/provider')
    def get_provider():return public_data(load_provider(root))
    @app.put('/api/provider')
    async def put_provider(request:Request):
        try:
            raw=await request.body()
            if len(raw)>16000:raise ValueError()
            values=json.loads(raw)
            if not isinstance(values,dict):raise ValueError()
            return public_data(save_provider(root,values))
        except (ValidationError,ValueError,TypeError):
            raise HTTPException(422,'Некорректные настройки. Проверьте URL, параметры и обязательные поля.') from None
    @app.delete('/api/provider')
    def delete_provider():return public_data(save_provider(root,{'clear_key':True}))
    @app.get('/api/provider/models')
    def models():
        try:
            result=request(load_provider(root),'/models',timeout=15)
            return {'models':[{'id':str(m['id'])[:200]} for m in result.get('data',[])[:1000] if isinstance(m,dict) and isinstance(m.get('id'),str)]}
        except (ValueError,BudgetExpired):raise HTTPException(400,'Список моделей недоступен. ID можно указать вручную.') from None
    @app.get('/api/provider/balance')
    def balance():
        cfg=load_provider(root)
        if not is_openrouter(cfg.base_url):return {'available':False,'reason':'Баланс доступен только для OpenRouter'}
        if not cfg.api_key.get_secret_value():return {'available':False,'reason':'Сохраните ключ OpenRouter'}
        try:
            credits=request(cfg,'/credits',timeout=15).get('data',{});key=request(cfg,'/key',timeout=15).get('data',{})
            number=lambda v:round(float(v),2) if isinstance(v,(int,float)) and not isinstance(v,bool) else None
            total,used=number(credits.get('total_credits')),number(credits.get('total_usage'))
            return {'available':True,'balance':round(total-used,2) if total is not None and used is not None else None,'total_credits':total,
                'key_limit_remaining':number(key.get('limit_remaining')),'key_usage_daily':number(key.get('usage_daily'))}
        except (ValueError,BudgetExpired,AttributeError) as exc:return {'available':False,'reason':str(exc) if isinstance(exc,(ValueError,BudgetExpired)) else 'Неожиданный ответ OpenRouter'}
    @app.post('/api/provider/test')
    def test_connection():
        cfg=load_provider(root);issues=eligibility(cfg)
        if issues:return {'ok':False,'message':'; '.join(issues)}
        started=time.monotonic()
        from .deadline import Deadline
        deadline=Deadline(30)
        try:
            data,usage,model=completion(cfg,'Return JSON {"ok":true}.',{'test':'connection'},100,deadline=deadline,cap=20)
            if data.get('ok') is not True:raise ValueError('Модель не выполнила проверочный JSON-контракт')
            vision_status='disabled'
            if cfg.vision_enabled:
                from PIL import Image
                buf=io.BytesIO();Image.new('RGB',(16,16),'red').save(buf,format='PNG')
                images=[{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()}}]
                data,_,_=completion(cfg,'Identify the solid image color. Return JSON {"color":"red|green|blue"}.',{},100,images,deadline,True,20)
                if str(data.get('color','')).lower()!='red':raise ValueError('Визуальная модель не распознала тестовое изображение')
                vision_status='passed'
            return {'ok':True,'message':'Соединение и JSON проверены','model':model,'vision':vision_status,'seconds':round(time.monotonic()-started,2),'usage':usage}
        except (ValueError,BudgetExpired) as exc:return {'ok':False,'message':str(exc),'seconds':round(time.monotonic()-started,2)}
