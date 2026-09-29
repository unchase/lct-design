from zipfile import ZipFile
from lct_design.models import ContentPackage, Section, Chart
from lct_design.template import analyze_template
from lct_design.planner import plan_content
from lct_design.exporter import generate_deck
from lct_design.package import read_package,validate_relationships,parse_xml,NS

def content():
    return ContentPackage(title='Проверка', sections=[
        Section(id='facts',title='Факты',bullets=['Стоимость 125 рублей','Рост 12%']),
        Section(id='table',title='Таблица',table=[['Период','План'],['2026','125']]),
        Section(id='chart',title='График',chart=Chart(categories=['А','Б'],series={'План':[12,25]},unit='шт.'))])

def test_native_export_preserves_sources(template,tmp_path):
    original=template.read_bytes();p=analyze_template(template);c=content()
    plan=plan_content(c,p,3,'offline');out=tmp_path/'result.pptx'
    manifest=generate_deck(template,p,plan,'sequential',out)
    parts=read_package(out)
    assert not validate_relationships(parts)
    text=' '.join(' '.join(parse_xml(d).xpath('//a:t/text()',namespaces=NS)) for n,d in parts.items() if n.startswith('ppt/slides/slide') and n.endswith('.xml'))
    assert '125 рублей' in text and '12%' in text
    assert any(n.startswith('ppt/charts/chart') for n in parts)
    assert any(b'<a:tbl>' in d for d in parts.values())
    tables=[parse_xml(d) for n,d in parts.items() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
    assert any(t.xpath('//a:graphicData[@uri="http://schemas.openxmlformats.org/drawingml/2006/table"]/a:tbl',namespaces=NS) for t in tables)
    assert any(n.endswith('.xlsx') for n in parts)
    assert template.read_bytes()==original
    assert len(manifest['slides'])==3

def test_long_content_never_disappears(template,tmp_path):
    p=analyze_template(template);long='Очень длинный текст '*120
    plan=plan_content(ContentPackage(title='Long',sections=[Section(id='a',title='Title',bullets=[long])]),p,1,'offline')
    m=generate_deck(template,p,plan,'focus',tmp_path/'long.pptx')
    assert m['slides'][0]['source_ids']==['a']
    assert any(o['text']==long for o in m['slides'][0]['objects'])
    # Either it fits at a readable template size or the overflow is reported, never silently shrunk.
    assert all(o['overflow'] or o.get('size',12)>=12 for o in m['slides'][0]['objects'])

def test_embedded_image_is_native_and_not_a_remote_fetch(template,tmp_path):
    import base64,io
    from PIL import Image
    buf=io.BytesIO();Image.new('RGB',(80,40),'red').save(buf,format='PNG')
    uri='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()
    p=analyze_template(template)
    plan=plan_content(ContentPackage(title='Image',sections=[Section(id='photo',title='Photo',image=uri)]),p,1,'offline')
    m=generate_deck(template,p,plan,'sequential',tmp_path/'image.pptx')
    parts=read_package(tmp_path/'image.pptx')
    assert any(o['role']=='image' for o in m['slides'][0]['objects'])
    assert any(buf.getvalue()==data for data in parts.values())
    assert not validate_relationships(parts)

def test_incompatible_visuals_rejected():
    import pytest
    with pytest.raises(ValueError): Section(id='x',title='x',diagram=['a'],table=[['b']])
    with pytest.raises(ValueError): Section(id='x',title='x',image='http://localhost/secret')
    with pytest.raises(ValueError): Section(id='x',title='x',table=[[]])
