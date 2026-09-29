import argparse,json,os,shutil,uuid
from pathlib import Path

def main():
    p=argparse.ArgumentParser(prog='lct-design');sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('analyze');a.add_argument('template',type=Path);a.add_argument('--output',type=Path)
    g=sub.add_parser('generate');g.add_argument('--template',required=True,type=Path);g.add_argument('--content',required=True,type=Path);g.add_argument('--output',type=Path,default=Path('output'));g.add_argument('--mode',choices=['offline','live'],default='offline');g.add_argument('--variants',nargs='+',default=['sequential','comparison','focus']);g.add_argument('--slides',type=int,default=12)
    s=sub.add_parser('serve');s.add_argument('--host',default='127.0.0.1');s.add_argument('--port',type=int,default=8000);s.add_argument('--data',type=Path,default=Path('data'))
    w=sub.add_parser('worker');w.add_argument('--data',required=True,type=Path);w.add_argument('--once',action='store_true')
    args=p.parse_args()
    from .template import analyze_template
    from .pipeline import save_json
    if args.command=='analyze':
        profile=analyze_template(args.template).model_dump()
        if args.output:save_json(args.output,profile)
        else:print(json.dumps(profile,ensure_ascii=False,indent=2))
    elif args.command=='generate':
        from .models import ContentPackage,GenerateRequest
        from .store import JobStore
        from .pipeline import run_job
        store=JobStore(args.output);tid=uuid.uuid4().hex;folder=store.root/'templates'/tid;folder.mkdir(parents=True)
        shutil.copyfile(args.template,folder/'source.pptx');profile=analyze_template(args.template);save_json(folder/'profile.json',profile.model_dump())
        content=ContentPackage.model_validate_json(args.content.read_text(encoding='utf-8'))
        req=GenerateRequest(template_id=tid,content=content,mode=args.mode,variants=args.variants,slide_count=args.slides)
        job=store.create({'request':req.model_dump()});store.update(job['id'],status='running')
        try:
            result=run_job(store,job);print(json.dumps({'job':job['id'],'output':str((store.root/'jobs'/job['id']).resolve()),'seconds':result['seconds']},ensure_ascii=False))
        except Exception as exc:store.update(job['id'],status='failed',error=str(exc));raise
    elif args.command=='serve':
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(args.data),host=args.host,port=args.port)
    elif args.command=='worker':
        from .worker import work
        work(args.data,args.once)

if __name__=='__main__':main()
