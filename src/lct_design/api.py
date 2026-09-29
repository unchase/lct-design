import asyncio,json,os,re,subprocess,sys,uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,UploadFile,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .models import GenerateRequest
from .store import JobStore
from .template import analyze_template
from .pipeline import save_json

ROOT=Path(os.getenv('LCT_APP_ROOT',Path(__file__).resolve().parents[2]))

class RepairRequest(BaseModel):
    variant:str
    finding_ids:list[str]

def create_app(data_dir=None,start_worker=True):
    root=Path(data_dir or os.getenv('LCT_DATA_DIR',ROOT/'data')).resolve();store=JobStore(root)
    @asynccontextmanager
    async def lifespan(app):
        worker=None
        if start_worker:
            worker=subprocess.Popen([sys.executable,'-m','lct_design.cli','worker','--data',str(root)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        yield
        if worker:
            worker.terminate()
            try:worker.wait(timeout=10)
            except subprocess.TimeoutExpired:worker.kill();worker.wait()
    app=FastAPI(title='LCT Design',version='0.2.0',lifespan=lifespan)
    app.state.store=store
    from .provider import install_routes,load_provider,eligibility
    install_routes(app,root)
    @app.middleware('http')
    async def origin_guard(request:Request,call_next):
        access=os.getenv('LCT_ACCESS_TOKEN','')
        if access and request.url.path!='/api/health':
            import base64,secrets
            try:
                scheme,encoded=request.headers.get('authorization','').split(' ',1)
                username,password=base64.b64decode(encoded,validate=True).decode().split(':',1)
                authorized=scheme.lower()=='basic' and username=='forma' and secrets.compare_digest(password.encode(),access.encode())
            except (ValueError,UnicodeError):authorized=False
            if not authorized:return JSONResponse({'detail':'Войдите в рабочее пространство'},status_code=401,headers={'WWW-Authenticate':'Basic realm="Forma", charset="UTF-8"'})
        origin=request.headers.get('origin')
        allowed={str(request.base_url).rstrip('/'),'http://localhost:5173','http://127.0.0.1:5173'}
        public_url=os.getenv('LCT_PUBLIC_URL','').rstrip('/')
        if public_url:allowed.add(public_url)
        if request.method not in ('GET','HEAD','OPTIONS') and origin and origin not in allowed:
            return JSONResponse({'detail':'Cross-origin writes are not allowed'},status_code=403)
        response=await call_next(request)
        if request.url.path.startswith('/api/provider'):response.headers['Cache-Control']='no-store'
        return response
    def get_job(id):
        if not re.fullmatch('[a-f0-9]{32}',id): raise HTTPException(404,'Задача не найдена')
        try:return store.get(id)
        except KeyError:raise HTTPException(404,'Задача не найдена')
    @app.get('/api/health')
    def health():return {'status':'ok','version':'0.2.0','live_configured':not eligibility(load_provider(root)),'renderer':os.getenv('LCT_RENDERER','docker')}
    @app.get('/api/example')
    def example():return json.loads((ROOT/'examples/content.json').read_text(encoding='utf-8'))
    @app.get('/api/templates')
    def list_templates():
        return [json.loads(p.read_text(encoding='utf-8')) for p in (root/'templates').glob('*/meta.json')]
    @app.post('/api/templates')
    async def upload_template(file:UploadFile):
        if not (file.filename or '').lower().endswith('.pptx'):raise HTTPException(400,'Нужен файл .pptx')
        id=uuid.uuid4().hex;folder=root/'templates'/id;folder.mkdir(parents=True,exist_ok=True)
        path=folder/'source.pptx';size=0
        try:
            with path.open('wb') as f:
                while chunk:=await file.read(1024*1024):
                    size+=len(chunk)
                    if size>100*1024**2:raise HTTPException(413,'Максимальный размер — 100 МБ')
                    f.write(chunk)
            profile=await asyncio.to_thread(analyze_template,path);profile.filename=Path(file.filename).name
            save_json(folder/'profile.json',profile.model_dump())
            meta={'id':id,'filename':profile.filename,'slides':len(profile.patterns),'colors':profile.colors[:8],'fonts':profile.fonts,'patterns':len(profile.patterns),'hash':profile.hash}
            save_json(folder/'meta.json',meta);return meta
        except HTTPException:
            path.unlink(missing_ok=True);raise
        except (ValueError,OSError) as exc:
            path.unlink(missing_ok=True);raise HTTPException(400,str(exc)[:500])
        finally:await file.close()
    @app.get('/api/templates/{id}/profile')
    def profile(id:str):
        if not re.fullmatch('[a-f0-9]{32}',id):raise HTTPException(404)
        p=root/'templates'/id/'profile.json'
        if not p.exists():raise HTTPException(404)
        return json.loads(p.read_text(encoding='utf-8'))
    @app.post('/api/jobs',status_code=202)
    def create(request:GenerateRequest):
        if not re.fullmatch('[a-f0-9]{32}',request.template_id) or not (root/'templates'/request.template_id/'source.pptx').exists():raise HTTPException(404,'Шаблон не найден')
        if len(set(request.variants))!=len(request.variants) or not request.variants:raise HTTPException(422,'Выберите уникальные варианты')
        if request.mode=='live':
            cfg=load_provider(root)
            if eligibility(cfg):raise HTTPException(400,'; '.join(eligibility(cfg)))
        return store.create({'request':request.model_dump(),**({'provider_revision':cfg.revision} if request.mode=='live' else {})})
    @app.get('/api/jobs')
    def jobs():return store.list()
    @app.get('/api/jobs/{id}')
    def job(id:str):return get_job(id)
    @app.post('/api/jobs/{id}/cancel')
    def cancel(id:str):
        get_job(id);store.cancel(id);return {'cancelled':True}
    @app.post('/api/jobs/{id}/repair',status_code=202)
    def repair(id:str,request:RepairRequest):
        job=get_job(id)
        if job['status'] not in ('completed','partial'):raise HTTPException(409,'Дождитесь завершения задачи')
        variant=next((v for v in job['result']['variants'] if v['name']==request.variant),None)
        if not variant:raise HTTPException(404,'Вариант не найден')
        selected=[f for f in variant['findings'] if f['id'] in request.finding_ids and f.get('repair') in ('refit','relayout','recolor') and f.get('slide')]
        if not selected or len(selected)!=len(set(request.finding_ids)):raise HTTPException(422,'Выбраны недоступные исправления')
        repairs=[]
        for f in selected:
            slide=next(s for s in variant['slides'] if s['number']==f['slide'])
            if f['repair']=='relayout':repairs.append(f'{f["slide"]}:relayout:{slide["pattern_id"]}');continue
            obj=next((o for o in slide['objects'] if o['id']==f['object_id']),None)
            if obj is None:raise HTTPException(422,'Выбраны недоступные исправления')
            repairs.append(f'{f["slide"]}:{obj["role"]}' if f['repair']=='refit' else f'{f["slide"]}:recolor:{obj["role"]}')
        payload=dict(job['payload']);payload['request']=dict(payload['request']);payload['request']['variants']=[request.variant]
        payload.update({'parent_id':id,'repairs':sorted(set(payload.get('repairs',[]))|set(repairs)),'selected_findings':request.finding_ids})
        return store.create(payload)
    @app.get('/api/templates/{id}/slides/{number}.png')
    def template_slide(id:str,number:int):
        # Rendered source slide, for side-by-side comparison with a generated slide.
        if not re.fullmatch('[a-f0-9]{32}',id) or not 1<=number<=999:raise HTTPException(404)
        folder=root/'templates'/id/'render'
        path=next((f for f in (folder/f'slide-{number:02d}.png',folder/f'slide-{number}.png') if f.is_file()),None)
        if path is None:raise HTTPException(404,'Изображение исходного слайда ещё не подготовлено')
        return FileResponse(path)
    @app.get('/api/jobs/{id}/artifacts/{variant}/{filename}')
    def artifact(id:str,variant:str,filename:str):
        get_job(id)
        if variant not in ('sequential','comparison','focus') or not re.fullmatch(r'(presentation\.(pptx|html)|speech\.md|source\.pdf|slide-\d+\.png|manifest\.json|audit\.json)',filename):raise HTTPException(404)
        path=root/'jobs'/id/variant/filename
        if not path.is_file():raise HTTPException(404)
        return FileResponse(path,filename=None if filename.endswith('.png') else filename)
    dist=ROOT/'frontend/dist'
    if dist.exists(): app.mount('/',StaticFiles(directory=dist,html=True),name='frontend')
    else:
        @app.get('/')
        def index():return {'message':'Frontend not built. Run npm ci && npm run build in frontend.','api':'/docs'}
    return app
