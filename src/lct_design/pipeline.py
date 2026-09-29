import json,time,hashlib,shutil
from pathlib import Path
from .models import GenerateRequest,TemplateProfile,DeckPlan,Finding
from .template import analyze_template,ANALYSIS_ALGORITHM
from .planner import plan_content,PROMPTS
from .exporter import generate_deck
from .render import render_deck,html_export
from .audit import audit_deck
from .vision import analyze_visual
from .package import read_package,validate_relationships,write_package
from .deadline import Deadline,BudgetExpired
from .provider import load_provider,eligibility
from .live_design import prepare_template,batch_audit,apply_audit,repair_layouts

def save_json(path,data):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

def run_job(store,job):
    id=job['id'];payload=job['payload'];request=GenerateRequest.model_validate(payload.get('request',payload))
    root=store.root;template=root/'templates'/request.template_id/'source.pptx';folder=root/'jobs'/id
    folder.mkdir(parents=True,exist_ok=True);start=time.monotonic();deadline=None;cfg=None
    if request.mode=='live':
        cfg=load_provider(root)
        if eligibility(cfg):raise ValueError('; '.join(eligibility(cfg)))
        if payload.get('provider_revision') and payload['provider_revision']!=cfg.revision:
            raise ValueError('Настройки провайдера изменились после постановки в очередь. Создайте новое задание.')
    def stage(label):
        if store.get(id)['cancelled']:raise InterruptedError('Задача отменена')
        if deadline:deadline.remaining()
        store.update(id,stage=label)
    stage('Анализ шаблона');profile_path=template.parent/'profile.json'
    profile=TemplateProfile.model_validate_json(profile_path.read_text(encoding='utf-8')) if profile_path.exists() else analyze_template(template)
    if profile.analysis.get('algorithm')!=ANALYSIS_ALGORITHM:
        filename=profile.filename;profile=analyze_template(template);profile.filename=filename
    if profile.analysis.get('visual')!='complete':
        stage('Визуальный анализ шаблона')
        sanitized=template.parent/'render-input.pptx';write_package(read_package(template),sanitized)
        tr=render_deck(sanitized,template.parent/'render')
        profile=analyze_visual(profile,tr,template.parent/'render')
    preparation_warnings=[]
    if cfg and cfg.vision_enabled:
        stage('Понимание композиций шаблона')
        try:prepare_template(profile,template.parent,cfg)
        except (ValueError,BudgetExpired) as exc:preparation_warnings.append('Визуальное описание шаблона недоступно: '+str(exc))
    save_json(profile_path,profile.model_dump())
    generation_start=time.monotonic();preparation_seconds=generation_start-start;deadline=Deadline(300)
    result={'variants':[],'mode':request.mode,'model':cfg.model if cfg else None,'usage':{},'warnings':preparation_warnings,
        'parent_id':payload.get('parent_id'),'template_name':profile.filename,'template_id':request.template_id,
        'analysis':profile.analysis,'seconds':0,'versions':{'app':'0.2.0','profile':profile.version,
        'prompts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in PROMPTS.glob('*.md')}},
        'content_hash':hashlib.sha256(request.content.model_dump_json().encode()).hexdigest(),
        'inference':{'calls':[],'audit':{'status':'not_run','coverage':[]},'repair':{'status':'not_needed'},
            'provider':cfg.provider if cfg else None,'competition_mode':cfg.competition_mode if cfg else None}}
    def usage(stage_name,model,values):
        result['inference']['calls'].append({'stage':stage_name,'model':model,'usage':values,'status':'complete'})
        for key,value in values.items():
            if isinstance(value,(int,float)):result['usage'][key]=result['usage'].get(key,0)+value
    def persist_variant(item,out):
        save_json(out/'audit.json',item['findings'])
    def build_variant(variant,out,plan):
        vstart=time.monotonic();out.mkdir(parents=True,exist_ok=True)
        stage('Вёрстка: '+variant)
        manifest=generate_deck(template,profile,plan,variant,out/'presentation.pptx',payload.get('repairs'))
        stage('Рендеринг: '+variant);render=render_deck(out/'presentation.pptx',out,deadline=deadline)
        # Preserve a usable PPTX even when the renderer exhausts its allotted time.
        if store.get(id)['cancelled']:raise InterruptedError('Задача отменена')
        findings=audit_deck(manifest,render,profile,out)
        missing=validate_relationships(read_package(out/'presentation.pptx'))
        findings.append(Finding(id='package-integrity',rule='package.relationships',severity='error' if missing else 'info',status='failed' if missing else 'passed',message='Повреждённые связи PPTX' if missing else 'Все связи PPTX разрешаются',evidence={'missing':missing}))
        html_export(manifest,render,out)
        (out/'speech.md').write_text(speech,encoding='utf-8')
        save_json(out/'manifest.json',manifest);save_json(out/'render.json',render.model_dump())
        item={'name':variant,'width':profile.width,'height':profile.height,'slides':manifest['slides'],'findings':[f.model_dump() for f in findings],
            'render':render.model_dump(),'warnings':manifest['warnings'],'seconds':round(time.monotonic()-vstart,2),
            'files':['presentation.pptx','presentation.html','speech.md','manifest.json','audit.json']+(['source.pdf'] if render.status=='complete' and render.pdf else [])}
        persist_variant(item,out);return item
    expired=False
    try:
        stage('LLM: структура и три композиции' if cfg else 'Структура и содержание')
        if payload.get('parent_id'):
            plan=DeckPlan.model_validate_json((root/'jobs'/payload['parent_id']/'plan.json').read_text(encoding='utf-8'))
        else:
            plan=plan_content(request.content,profile,request.slide_count,request.mode,cfg,deadline,request.variants)
            if cfg:usage('plan',plan.model,plan.usage)
        from .speech import speaker_text,speech_document
        for slide in plan.slides:
            if not slide.speaker_notes:slide.speaker_notes=speaker_text(slide)
        speech=speech_document(plan);result['warnings'].extend(plan.warnings);result['model']=plan.model
        save_json(folder/'plan.json',plan.model_dump());save_json(folder/'profile.json',profile.model_dump())
        for variant in request.variants:
            item=build_variant(variant,folder/variant,plan)
            result['variants'].append(item);result['seconds']=round(time.monotonic()-start,2);store.update(id,result=result)
        if cfg and cfg.vision_enabled:
            stage('VLM: проверка всех вариантов')
            try:
                audit=batch_audit(result,folder,plan,cfg,deadline);usage('audit',audit['model'],audit['usage'])
                result['inference']['audit']=audit;apply_audit(result,audit)
            except (ValueError,BudgetExpired) as exc:
                result['inference']['audit']={'status':'failed','coverage':[],'error':str(exc)}
                result['inference']['calls'].append({'stage':'audit','status':'failed','usage':None})
                result['warnings'].append('VLM-аудит не завершён: '+str(exc))
        elif cfg:result['warnings'].append('Визуальная модель отключена: композиция и семантика по изображениям не проверены.')
        issues=[]
        for v in result['variants']:
            for f in v['findings']:
                if f.get('slide') and (f['severity']=='error' or (f['rule']=='content.semantic' and f['status']=='warning')):
                    issues.append({'variant':v['name'],'slide':f['slide'],'message':f['message']})
        if cfg and issues and not payload.get('parent_id'):
            if deadline.remaining()>60:
                stage('LLM: один проход исправлений')
                try:
                    candidate,changes,tokens,model=repair_layouts(plan,profile,issues,cfg,deadline);usage('repair',model,tokens)
                    result['inference']['repair']={'status':'unchanged','changed_slides':[]}
                    if changes:
                        changed=[]
                        for variant in sorted({v for v,n in changes}):
                            out=folder/'repair-candidate'/variant;item=build_variant(variant,out,candidate)
                            previous=next(v for v in result['variants'] if v['name']==variant)
                            old_errors=sum(f['severity']=='error' for f in previous['findings']);new_errors=sum(f['severity']=='error' for f in item['findings'])
                            if item['render']['status']=='complete' and new_errors<=old_errors:
                                archive=folder/'before-repair'/variant;archive.parent.mkdir(exist_ok=True)
                                shutil.move(str(folder/variant),str(archive));shutil.move(str(out),str(folder/variant))
                                result['variants'][result['variants'].index(previous)]=item;changed.append(variant)
                                for i,s in enumerate(plan.slides):s.layouts[variant]=candidate.slides[i].layouts[variant]
                                # Persist each accepted variant before another render can fail.
                                result['inference']['repair']={'status':'applied','changed_slides':[{'variant':v,'slide':n} for v,n in sorted(changes) if v in changed]}
                                result['inference']['audit']['status']='partial'
                                result['inference']['audit']['coverage']=[c for c in result['inference']['audit'].get('coverage',[]) if c['variant']!=variant]
                                if len(changed)==1:result['warnings'].append('После исправления выполнена техническая проверка. Повторный VLM-аудит не запускался из-за ограничения числа проходов.')
                                save_json(folder/'plan.json',plan.model_dump());store.update(id,result=result)
                except (ValueError,BudgetExpired) as exc:
                    if result['inference']['repair']['status']=='applied':
                        result['inference']['repair']['error']=str(exc)
                        result['warnings'].append('Автоисправление завершено частично; уже принятые варианты сохранены: '+str(exc))
                    else:
                        result['inference']['repair']={'status':'failed','error':str(exc)}
                        result['warnings'].append('Автоисправление не применено: '+str(exc))
            else:result['inference']['repair']={'status':'skipped_budget'}
        for v in result['variants']:persist_variant(v,folder/v['name'])
        deadline.remaining()
    except BudgetExpired:
        expired=True;result['warnings'].append('Общий бюджет 300 секунд исчерпан. Готовые варианты сохранены; остальные этапы не выполнены.')
    generation_seconds=time.monotonic()-generation_start
    renders_complete=len(result['variants'])==len(request.variants) and all(v['render']['status']=='complete' for v in result['variants'])
    partial=expired or not renders_complete or any(f['severity']=='error' for v in result['variants'] for f in v['findings']) or bool(cfg and result['inference']['audit']['status']!='complete')
    result['timing']={'preparation_seconds':round(preparation_seconds,2),'generation_seconds':round(generation_seconds,2),
        'budget_seconds':300,'budget_status':'exceeded' if expired or generation_seconds>300 else ('met' if renders_complete and len(result['variants'])==3 else 'not_verified')}
    result['seconds']=round(time.monotonic()-start,2);save_json(folder/'run.json',result)
    store.update(id,status='partial' if partial else 'completed',stage='Готово с ограничениями' if partial else 'Готово',result=result)
    return result
