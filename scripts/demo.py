"""Reproducible 3-template × 3-variant matrix; inputs remain user-owned."""
import argparse,hashlib,json,shutil,time,uuid,sys
from pathlib import Path
from lct_design.template import analyze_template
from lct_design.models import GenerateRequest,ContentPackage
from lct_design.pipeline import run_job,save_json
from lct_design.store import JobStore

def diversity(variants):
    def signature(s):return [(o['role'],{k:round(v) for k,v in o['box'].items()}) for o in s['objects']]
    from itertools import combinations
    return {a['name']+' / '+b['name']:round(sum(signature(x)!=signature(y) for x,y in zip(a['slides'],b['slides']))/max(1,len(a['slides'])),3) for a,b in combinations(variants,2)}

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser();p.add_argument('--dataset',required=True,type=Path);p.add_argument('--content',default=Path('examples/content.json'),type=Path);p.add_argument('--output',default=Path('output/matrix'),type=Path);p.add_argument('--mode',default='offline',choices=['offline','live']);a=p.parse_args()
    content=ContentPackage.model_validate_json(a.content.read_text(encoding='utf-8'));store=JobStore(a.output)
    summary={'mode':a.mode,'synthetic_content':content.synthetic,'content_sha256':hashlib.sha256(a.content.read_bytes()).hexdigest(),'runs':[]}
    for template in sorted(a.dataset.glob('*.pptx')):
        start=time.monotonic();tid=uuid.uuid4().hex;folder=store.root/'templates'/tid;folder.mkdir(parents=True)
        shutil.copyfile(template,folder/'source.pptx');profile=analyze_template(template);save_json(folder/'profile.json',profile.model_dump())
        request=GenerateRequest(template_id=tid,content=content,mode=a.mode,slide_count=len(content.sections) or 12)
        job=store.create({'request':request.model_dump()});store.update(job['id'],status='running')
        try:
            result=run_job(store,job)
            run={'template':template.name,'hash':profile.hash,'job':job['id'],'seconds_cold':round(time.monotonic()-start,2),'timing':result['timing'],'diversity':diversity(result['variants']),
                 'variants':[{'name':v['name'],'seconds':v['seconds'],'render':v['render']['status'],'slides':len(v['slides']),
                              'errors':sum(f['severity']=='error' for f in v['findings']),'not_run':sum(f['status']=='not_run' for f in v['findings'])} for v in result['variants']]}
        except Exception as exc:
            store.update(job['id'],status='failed',error=str(exc));run={'template':template.name,'job':job['id'],'error':str(exc)}
        summary['runs'].append(run);save_json(a.output/'matrix.json',summary);print(json.dumps(run,ensure_ascii=False),flush=True)
    if any('error' in r or any(v['render']!='complete' for v in r['variants']) for r in summary['runs']):raise SystemExit(1)

if __name__=='__main__':main()
