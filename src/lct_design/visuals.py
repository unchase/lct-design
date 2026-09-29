"""Native DrawingML tables, vector diagrams and editable chart caches."""
from lxml import etree as ET
from .package import q,NS,xml

def element(tag,**attrs): return ET.Element(q(tag),{k:str(v) for k,v in attrs.items()})
def sub(parent,tag,**attrs):
    node=element(tag,**attrs);parent.append(node);return node

def transform(parent,box,tag='a:xfrm'):
    t=sub(parent,tag);sub(t,'a:off',x=int(box.x),y=int(box.y));sub(t,'a:ext',cx=int(box.w),cy=int(box.h));return t

def tx_body(text,font,size,color,tag='p:txBody',bold=False):
    tx=element(tag);sub(tx,'a:bodyPr',wrap='square',anchor='t',lIns=50000,rIns=50000,tIns=30000,bIns=30000);sub(tx,'a:lstStyle')
    for line in text.split('\n'):
        p=sub(tx,'a:p');pp=sub(p,'a:pPr');sub(pp,'a:buNone')
        run=sub(p,'a:r');rp=sub(run,'a:rPr',lang='ru-RU',sz=max(100,int(size*100)),b='1' if bold else '0')
        fill=sub(rp,'a:solidFill');sub(fill,'a:srgbClr',val=color);sub(rp,'a:latin',typeface=font)
        sub(rp,'a:ea',typeface=font);sub(rp,'a:cs',typeface=font)
        t=sub(run,'a:t');t.text=line
    return tx

def text_shape(id,box,text,font,size,color,bold=False,fill=None):
    sp=element('p:sp');nv=sub(sp,'p:nvSpPr');sub(nv,'p:cNvPr',id=id,name=f'LCT text {id}');sub(nv,'p:cNvSpPr',txBox=1);sub(nv,'p:nvPr')
    props=sub(sp,'p:spPr');transform(props,box);g=sub(props,'a:prstGeom',prst='rect');sub(g,'a:avLst')
    if fill: sub(sub(props,'a:solidFill'),'a:srgbClr',val=fill)
    else: sub(props,'a:noFill')
    sub(sub(props,'a:ln'),'a:noFill');sp.append(tx_body(text,font,size,color,bold=bold));return sp

def frame(id,box,uri):
    f=element('p:graphicFrame');nv=sub(f,'p:nvGraphicFramePr');sub(nv,'p:cNvPr',id=id,name=f'LCT visual {id}');sub(nv,'p:cNvGraphicFramePr');sub(nv,'p:nvPr')
    transform(f,box,'p:xfrm');data=sub(sub(f,'a:graphic'),'a:graphicData',uri=uri);return f,data

def picture_shape(id,box,rid,description):
    pic=element('p:pic');nv=sub(pic,'p:nvPicPr');sub(nv,'p:cNvPr',id=id,name=f'LCT image {id}',descr=description)
    sub(sub(nv,'p:cNvPicPr'),'a:picLocks',noChangeAspect=1);sub(nv,'p:nvPr')
    fill=sub(pic,'p:blipFill');sub(fill,'a:blip',**{q('r:embed'):rid});sub(sub(fill,'a:stretch'),'a:fillRect')
    props=sub(pic,'p:spPr');transform(props,box);sub(sub(props,'a:prstGeom',prst='rect'),'a:avLst')
    return pic

def table_shape(id,box,rows,font,color,accent,size,background='F3F5F7'):
    from .audit import contrast
    f,data=frame(id,box,'http://schemas.openxmlformats.org/drawingml/2006/table');tbl=sub(data,'a:tbl');sub(tbl,'a:tblPr',firstRow=1,bandRow=1)
    grid=sub(tbl,'a:tblGrid');cols=len(rows[0])
    for _ in range(cols): sub(grid,'a:gridCol',w=int(box.w/cols))
    for i,row in enumerate(rows):
        tr=sub(tbl,'a:tr',h=int(box.h/len(rows)))
        for value in row:
            fill=accent if i==0 else background
            ink='FFFFFF' if i==0 else color
            if contrast(ink,fill)<4.5:ink=max(('000000','FFFFFF'),key=lambda c:contrast(c,fill))
            cell=sub(tr,'a:tc');cell.append(tx_body(str(value),font,size,ink,'a:txBody',i==0))
            prop=sub(cell,'a:tcPr',marL=70000,marR=70000,marT=50000,marB=50000)
            sub(sub(prop,'a:solidFill'),'a:srgbClr',val=fill)
    return f

def chart_parts(chart,font,accent):
    root=ET.Element(q('c:chartSpace'),nsmap={'c':NS['c'],'a':NS['a'],'r':NS['r']})
    sub(root,'c:lang',val='ru-RU');c=sub(root,'c:chart');sub(c,'c:autoTitleDeleted',val=0)
    title=sub(c,'c:title');tx=sub(title,'c:tx');tx.append(tx_body(chart.title or chart.unit or 'Данные',font,16,'111111','c:rich'))
    plot=sub(c,'c:plotArea');sub(plot,'c:layout');bar=sub(plot,'c:barChart');sub(bar,'c:barDir',val='col');sub(bar,'c:grouping',val='clustered')
    for idx,(name,values) in enumerate(chart.series.items()):
        ser=sub(bar,'c:ser');sub(ser,'c:idx',val=idx);sub(ser,'c:order',val=idx);sub(sub(ser,'c:tx'),'c:v').text=name
        prop=sub(ser,'c:spPr');sub(sub(prop,'a:solidFill'),'a:srgbClr',val=accent)
        cr=sub(sub(ser,'c:cat'),'c:strRef');sub(cr,'c:f').text=f'Data!$A$2:$A${len(chart.categories)+1}'
        cat=sub(cr,'c:strCache');sub(cat,'c:ptCount',val=len(chart.categories))
        for n,label in enumerate(chart.categories): sub(sub(cat,'c:pt',idx=n),'c:v').text=label
        vr=sub(sub(ser,'c:val'),'c:numRef');col=chr(66+idx);sub(vr,'c:f').text=f'Data!${col}$2:${col}${len(values)+1}'
        val=sub(vr,'c:numCache');sub(val,'c:formatCode').text='0.##';sub(val,'c:ptCount',val=len(values))
        for n,v in enumerate(values): sub(sub(val,'c:pt',idx=n),'c:v').text=str(v)
    sub(bar,'c:axId',val=100);sub(bar,'c:axId',val=200)
    for tag,id,cross,pos in [('catAx',100,200,'b'),('valAx',200,100,'l')]:
        ax=sub(plot,'c:'+tag);sub(ax,'c:axId',val=id);sub(sub(ax,'c:scaling'),'c:orientation',val='minMax');sub(ax,'c:delete',val=0);sub(ax,'c:axPos',val=pos)
        if tag=='valAx': sub(ax,'c:numFmt',formatCode='0.##',sourceLinked=0)
        sub(ax,'c:tickLblPos',val='nextTo');sub(ax,'c:crossAx',val=cross);sub(ax,'c:crosses',val='autoZero')
    legend=sub(c,'c:legend');sub(legend,'c:legendPos',val='b');sub(c,'c:plotVisOnly',val=1)
    sub(sub(root,'c:externalData',**{q('r:id'):'workbook'}),'c:autoUpdate',val=0)
    return xml(root)

def chart_workbook(chart):
    """Small standards-based workbook, keeping the exact supplied numeric values."""
    from io import BytesIO
    from zipfile import ZipFile,ZIP_DEFLATED
    from xml.sax.saxutils import escape
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rows=[['Category',*chart.series.keys()]]+[[label,*[v[i] for v in chart.series.values()]] for i,label in enumerate(chart.categories)]
    data=[]
    for i,row in enumerate(rows,1):
        cells=[]
        for j,value in enumerate(row):
            ref=f'{chr(65+j)}{i}'
            cells.append(f'<c r="{ref}"><v>{value}</v></c>' if isinstance(value,(int,float)) else f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        data.append(f'<row r="{i}">'+''.join(cells)+'</row>')
    out=BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',f'<Types xmlns="{NS["ct"]}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr('_rels/.rels',f'<Relationships xmlns="{NS["rel"]}"><Relationship Id="rId1" Type="{NS["r"]}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="{NS["r"]}"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',f'<Relationships xmlns="{NS["rel"]}"><Relationship Id="rId1" Type="{NS["r"]}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="{ns}"><sheetData>'+''.join(data)+'</sheetData></worksheet>')
    return out.getvalue()
