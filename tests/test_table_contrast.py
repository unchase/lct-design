from lct_design.visuals import table_shape
from lct_design.models import Box
from lct_design.package import NS
from lct_design.audit import contrast

def test_light_template_text_remains_readable_in_table():
    table=table_shape(1,Box(x=0,y=0,w=6000000,h=3000000),[['Header'],['Body']],'Arial','FFFFFF','FFFF00',18)
    for cell in table.findall('.//a:tc',NS):
        text=cell.find('.//a:rPr/a:solidFill/a:srgbClr',NS).get('val')
        fill=cell.find('a:tcPr/a:solidFill/a:srgbClr',NS).get('val')
        assert contrast(text,fill)>=4.5
