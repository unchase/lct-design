import copy,io
from lxml import etree as ET
from PIL import Image
from lct_design.package import read_package,write_package,parse_xml,xml,NS,q,rels_path,relationships,validate_relationships
from lct_design.models import Box,ContentPackage,Section
from lct_design.visuals import picture_shape
from lct_design.template import analyze_template
from lct_design.planner import plan_content
from lct_design.exporter import generate_deck


def test_preserve_background_picture_card_fill_logo_and_footer(template,tmp_path):
    parts=read_package(template);part='ppt/slides/slide1.xml';tree=parse_xml(parts[part]);shapes=tree.find('p:cSld/p:spTree',NS)
    body=shapes.findall('p:sp',NS)[1]
    props=body.find('p:spPr',NS);props.remove(props.find('a:noFill',NS))
    fill=ET.SubElement(props,q('a:solidFill'));ET.SubElement(fill,q('a:srgbClr'),val='E8F1DF')
    before=xml(props)
    footer=copy.deepcopy(body);footer.find('p:nvSpPr/p:cNvPr',NS).set('id','12')
    ET.SubElement(footer.find('p:nvSpPr/p:nvPr',NS),q('p:ph'),type='ftr',idx='9')
    footer.find('.//a:t',NS).text='Company footer';shapes.append(footer)
    background=picture_shape(10,Box(x=0,y=0,w=12192000,h=6858000),'background','Unique background image')
    logo=picture_shape(11,Box(x=10000000,y=50000,w=1000000,h=500000),'background','Company logo')
    shapes.insert(2,background);shapes.append(logo)
    buf=io.BytesIO();Image.new('RGB',(160,90),'#aaccee').save(buf,format='PNG')
    parts['ppt/media/background.png']=buf.getvalue()
    parts[rels_path(part)]=f'<Relationships xmlns="{NS["rel"]}"><Relationship Id="background" Type="{NS["r"]}/image" Target="../media/background.png"/></Relationships>'.encode()
    types=parse_xml(parts['[Content_Types].xml']);ET.SubElement(types,'{'+NS['ct']+'}Default',Extension='png',ContentType='image/png')
    parts['[Content_Types].xml']=xml(types);parts[part]=xml(tree);write_package(parts,template)
    profile=analyze_template(template)
    plan=plan_content(ContentPackage(title='New',sections=[Section(id='new',title='New title',bullets=['New content'])]),profile,1,'offline')
    for variant in ('sequential','comparison','focus'):
        out=tmp_path/(variant+'.pptx');generate_deck(template,profile,plan,variant,out)
        actual=read_package(out)
        assert not validate_relationships(actual)
        slide_part=next(p for kind,p in relationships(actual,'ppt/presentation.xml').values() if kind=='slide')
        result=parse_xml(actual[slide_part])
        assert len(result.findall('.//p:pic',NS))==2, 'Background and logo must survive even when unique'
        card=result.xpath('//p:sp[p:nvSpPr/p:cNvPr[@id="3"]]',namespaces=NS)
        assert len(card)==1, 'Replacing text must not delete the card itself'
        assert xml(card[0].find('p:spPr',NS))==before
        assert actual['ppt/media/background.png']==buf.getvalue()
        text=' '.join(result.xpath('//a:t/text()',namespaces=NS))
        assert 'New content' in text and 'Company footer' in text
        assert 'Вставьте текст' not in text
