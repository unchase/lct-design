from lct_design.models import ContentPackage,Section
from lct_design.template import analyze_template
from lct_design.planner import plan_content
from lct_design.exporter import generate_deck
from lct_design.package import read_package,parse_xml,NS,validate_relationships

def test_native_process_and_hierarchy_data_agree_with_cache(template,tmp_path):
    content=ContentPackage(title='Native',sections=[
        Section(id='p',title='Process',diagram=['One','Two','Three','Four']),
        Section(id='h',title='Organization',diagram_kind='hierarchy',diagram=['Root','Assistant','Team A','Team B','Team C','Member A'],diagram_parents=[None,0,0,0,0,2],diagram_assistant=1)])
    p=analyze_template(template);plan=plan_content(content,p,2,'offline');out=tmp_path/'native.pptx'
    manifest=generate_deck(template,p,plan,'sequential',out);parts=read_package(out)
    assert not validate_relationships(parts)
    for slide in manifest['slides']:assert any(o['role']=='smartart' for o in slide['objects'])
    data=[v for k,v in parts.items() if k.startswith('ppt/diagrams/lct') and '/data' in k]
    assert len(data)==2
    alltext=' '.join(' '.join(parse_xml(v).xpath('//a:t/text()',namespaces=NS)) for k,v in parts.items() if k.startswith('ppt/diagrams/'))
    for label in ['One','Two','Three','Four','Root','Assistant','Team A','Team B','Team C','Member A']:assert alltext.count(label)>=2
    assert 'org-root' not in alltext and 'proc-1' not in alltext and 'sibTrans-' not in alltext

def test_drawing_cache_fits_requested_frame():
    from lct_design.smartart import smartart_parts,N
    from lct_design.models import Box
    box=Box(x=100,y=100,w=5000000,h=1800000)
    _,parts,_,_=smartart_parts(['A','B','C','D'],'process',box,9,'test','Arial','112233')
    tree=parse_xml(next(v for k,v in parts.items() if '/drawing' in k))
    for xfrm in tree.findall('.//a:xfrm',N)+tree.findall('.//dsp:txXfrm',N):
        off=xfrm.find('a:off',N);ext=xfrm.find('a:ext',N)
        if off is not None and ext is not None:
            assert int(off.get('x'))+int(ext.get('cx'))<=box.w+5
            assert int(off.get('y'))+int(ext.get('cy'))<=box.h+5
