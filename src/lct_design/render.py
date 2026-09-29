import html, json, os, shutil, subprocess, time,uuid
from pathlib import Path
from .models import RenderResult

def render_deck(pptx:Path,output:Path,deadline=None)->RenderResult:
    started=time.monotonic();output=Path(output);output.mkdir(parents=True,exist_ok=True)
    engine=os.getenv('LCT_RENDERER','docker')
    if engine=='none': return RenderResult(status='unavailable',error='Renderer disabled',engine=engine)
    source=output/'source.pptx'
    if Path(pptx).resolve()!=source.resolve(): shutil.copyfile(pptx,source)
    container=None
    def budget(cap):return deadline.remaining(cap) if deadline else cap
    try:
        if engine=='docker':
            if not shutil.which('docker'): return RenderResult(status='unavailable',engine=engine,error='Docker not found')
            image=os.getenv('LCT_RENDER_IMAGE','lct-design-renderer:local')
            container='lct-render-'+uuid.uuid4().hex
            cmd=['docker','run','--name',container,'--rm','--network','none','--memory','2g','--cpus','2','--pids-limit','256',
                '--cap-drop','ALL','--security-opt','no-new-privileges','--read-only','--tmpfs','/tmp:rw,size=512m',
                '-v',str(output.resolve())+':/work',image,'sh','-c',
                'libreoffice -env:UserInstallation=file:///tmp/lo --headless --convert-to pdf --outdir /work /work/source.pptx >/tmp/lo.log 2>&1 && test -s /work/source.pdf && pdftoppm -scale-to 1440 -png /work/source.pdf /work/slide && pdftotext -bbox-layout /work/source.pdf /work/geometry.html && fc-list : family > /work/fonts.txt']
        elif engine=='local':
            binary=os.getenv('LCT_SOFFICE') or shutil.which('soffice')
            if not binary: return RenderResult(status='unavailable',engine=engine,error='Set LCT_SOFFICE or install LibreOffice in the application container')
            cmd=[binary,'-env:UserInstallation='+ (output/'lo-profile').resolve().as_uri(),'--headless','--convert-to','pdf','--outdir',str(output),str(source)]
        else: return RenderResult(status='unavailable',engine=engine,error='Unknown renderer')
        run=subprocess.run(cmd,capture_output=True,text=True,timeout=budget(120),encoding='utf-8',errors='replace')
        if run.returncode or not (output/'source.pdf').is_file():
            return RenderResult(status='failed',engine=engine,error=(run.stderr or run.stdout or 'PDF not created')[-800:],seconds=time.monotonic()-started)
        if engine=='local':
            subprocess.run(['pdftoppm','-scale-to','1440','-png',str(output/'source.pdf'),str(output/'slide')],check=True,capture_output=True,timeout=budget(90))
            subprocess.run(['pdftotext','-bbox-layout',str(output/'source.pdf'),str(output/'geometry.html')],check=True,capture_output=True,timeout=budget(30))
            if shutil.which('fc-list'):
                (output/'fonts.txt').write_bytes(subprocess.check_output(['fc-list',':','family'],timeout=budget(10)))
        images=sorted(output.glob('slide-*.png'),key=lambda p:int(p.stem.rsplit('-',1)[-1]))
        if not images: return RenderResult(status='failed',engine=engine,error='No page images produced')
        return RenderResult(status='complete',pdf='source.pdf',images=[p.name for p in images],engine=engine,seconds=time.monotonic()-started)
    except (OSError,subprocess.SubprocessError) as exc:
        return RenderResult(status='failed',engine=engine,error=str(exc)[:500],seconds=time.monotonic()-started)
    finally:
        if container:
            try:subprocess.run(['docker','rm','-f',container],capture_output=True,timeout=10)
            except (OSError,subprocess.SubprocessError):pass

def html_export(manifest,render:RenderResult,out:Path):
    items=[]
    for i,s in enumerate(manifest['slides']):
        caption=html.escape(s['title'])
        if i<len(render.images):
            import base64
            encoded=base64.b64encode((out/render.images[i]).read_bytes()).decode()
            content=f'<img src="data:image/png;base64,{encoded}" alt="{caption}">'
        else:
            content='<div class="unrendered">Рендеринг недоступен. Ниже — текст, не изображение слайда.</div>'
            content+=''.join('<p>'+html.escape(o.get('text',''))+'</p>' for o in s['objects'])
        items.append(f'<section><h2>{i+1}. {caption}</h2>{content}</section>')
    document='<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Презентация</title><style>body{margin:0;background:#eceef1;font:16px system-ui;color:#202938}main{max-width:1100px;margin:auto;padding:24px}section{margin:0 0 40px}img{width:100%;height:auto;background:white}h2{font-size:17px}p{white-space:pre-wrap}.unrendered{padding:24px;background:#fff4d0}</style><main>'+''.join(items)+'</main></html>'
    (out/'presentation.html').write_text(document,encoding='utf-8')
