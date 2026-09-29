from lct_design.template import analyze_template
from conftest import make_template

def test_extract_theme_and_slots(template):
    p=analyze_template(template)
    assert p.width==12192000
    assert '1261A0' in p.colors
    assert 'Arial' in p.fonts
    assert p.patterns[0].slots[0].role=='title'
    assert len(p.patterns[0].slots)==2

def test_unseen_theme_not_filename(tmp_path):
    a=analyze_template(make_template(tmp_path/'a.pptx','AA2200','Georgia'))
    b=analyze_template(make_template(tmp_path/'b.pptx','008866','Verdana'))
    assert a.colors!=b.colors and a.fonts!=b.fonts

def test_large_numeric_callout_below_header_is_not_the_title(template):
    from lct_design.package import read_package,write_package,parse_xml,xml,NS
    parts=read_package(template);tree=parse_xml(parts['ppt/slides/slide1.xml'])
    shape=tree.findall('.//p:sp',NS)[1]
    shape.find('.//a:off',NS).set('y','1000000')
    shape.find('.//a:rPr',NS).set('sz','8000')
    shape.find('.//a:t',NS).text='42% result'
    parts['ppt/slides/slide1.xml']=xml(tree);write_package(parts,template)
    assert analyze_template(template).patterns[0].slots[0].id=='2'
