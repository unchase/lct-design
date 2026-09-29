"""Fill official LCT template. Source slides 7–11 retain their design/structure."""
import argparse,copy,json,hashlib,sys
from pathlib import Path
from lxml import etree as ET
from lct_design.package import NS,q,read_package,parse_xml,xml,relationships,rels_path,write_package,validate_relationships
from lct_design.exporter import add_override,prune,SLIDE_CT
from lct_design.visuals import sub,table_shape,picture_shape
from lct_design.models import Box
from lct_design.render import render_deck,html_export
from lct_design.pipeline import save_json

def fill(tree,id,text):
    shape=next(s for s in tree.findall('.//p:sp',NS) if s.find('p:nvSpPr/p:cNvPr',NS).get('id')==str(id))
    body=shape.find('p:txBody',NS);old=body.findall('a:p',NS);seed=copy.deepcopy(old[0]) if old else ET.Element(q('a:p'))
    props=seed.find('a:r/a:rPr',NS)
    if props is None:props=seed.find('a:endParaRPr',NS)
    props=copy.deepcopy(props) if props is not None else ET.Element(q('a:rPr'))
    props.tag=q('a:rPr')
    for p in old:body.remove(p)
    for line in text.split('\n'):
        p=copy.deepcopy(seed)
        for n in list(p):
            if n.tag!=q('a:pPr'):p.remove(n)
        r=sub(p,'a:r');r.append(copy.deepcopy(props));sub(r,'a:t').text=line;body.append(p)

def structure(tree):
    t=copy.deepcopy(tree)
    for tx in t.findall('.//p:txBody',NS):tx.getparent().remove(tx)
    return ET.tostring(t,method='c14n')

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--template',required=True,type=Path);parser.add_argument('--output',default=Path('output/pitch'),type=Path);parser.add_argument('--team',type=Path);parser.add_argument('--matrix',type=Path,default=Path('output/matrix/final-runs.json'));args=parser.parse_args()
    team=json.loads(args.team.read_text(encoding='utf-8')) if args.team else {}
    original=read_package(args.template);parts=dict(original);pres=parse_xml(parts['ppt/presentation.xml']);oldids=list(pres.find('p:sldIdLst',NS));source_rels=relationships(parts,'ppt/presentation.xml')
    sourceparts=[source_rels[n.get(q('r:id'))][1] for n in oldids]
    types=parse_xml(parts['[Content_Types].xml']);rels=parse_xml(parts['ppt/_rels/presentation.xml.rels'])
    for n in list(rels):
        if n.get('Type','').endswith('/slide'):rels.remove(n)
    pres.find('p:sldIdLst',NS).clear()
    for tag in ('custShowLst','extLst'):
        for n in pres.findall('p:'+tag,NS):pres.remove(n)
    members=team.get('members',[])
    teamtext=f"Капитан: {team.get('captain','не указан')}\nУчастников: {len(members) if members else 'не указано'}\n{team.get('about','Сведения о команде не предоставлены')}\nГород: {team.get('city','не указан')}"
    pages=[
      (7,{3:'Форма',5:'Цифровой дизайнер презентаций\n'+team.get('name','Название команды не предоставлено'),2:'VK Tech'},None),
      (8,{3:'Фото команды не предоставлено',5:'PPTX-шаблон и материалы превращаются в три редактируемые презентации с отчётом проверок.',8:'Содержание отделено от дизайна. Правила оформления извлекаются из загруженного шаблона; факты связаны с источниками.',14:teamtext},None),
      (9,{7:'КОМАНДА',**{id:(members[i].get('name','Не заполнено') if i<len(members) else 'Не заполнено') for i,id in enumerate([15,58,61,64,67])},**{id:('\n'.join(str(members[i].get(k,'Не указано')) for k in ('role','contact','phone','organization')) if i<len(members) else 'Роль не указана\nКонтакт не указан\nОрганизация не указана') for i,id in enumerate([9,57,60,63,66])}},None),
      (10,{7:'О КОМАНДЕ',37:team.get('history','История команды не предоставлена.'),43:'Задача объединяет анализ документов, геометрию и ИИ. Оформление должно зависеть от шаблона, а не от ручной карты слайдов.',40:'Исправлены неверный формат native-таблиц и масштабирование SmartArt. Результат проверяется повторным рендером; неподтверждённые проверки отмечены отдельно.'},None),
      (11,{3:'OOXML → профиль стиля → план → вёрстка → native PPTX → рендер → аудит.\nPython/FastAPI, React, SQLite. Изолированный renderer.\nБез модели работает диагностический режим; API адаптер подготовлен.',7:'Первый сценарий — материалы продаж и продукта в фирменном стиле.\nПилот: измерить время подготовки и число ручных правок.\nДалее: расширить SmartArt, проверку стиля и модельный аудит.'},None),
      (12,{28:'Проблема',29:'Факты уже собраны.\nОформление всё ещё требует ручной работы.\n\nПри смене шаблона приходится заново выбирать композиции, переносить текст и проверять размеры.'},None),
      (13,{2:'Как работает сервис',3:'1. Разбираем ZIP/OOXML и эффективные стили.\n2. Извлекаем типографику, цвета, области и повторяющиеся композиции.\n3. Планируем содержание, сохраняя ссылки на исходные факты.\n4. Создаём редактируемые объекты и повторно рендерим PPTX.\n5. Показываем проверки и сохраняем исправления новой версией.'},None),
      (15,{6:'От шаблона к файлу',8:'Загрузить фирменный PPTX',9:'Добавить текст, таблицы, числа и изображения',10:'Сравнить три композиционных варианта',11:'Проверить отмеченные области и выбрать исправления',12:'Скачать PPTX, PDF и HTML'},None),
      (13,{2:'Рабочий интерфейс',3:''},'screenshot'),
      (13,{2:'Три шаблона',3:''},'matrix'),
      (15,{6:'Аудит с доказательствами',8:'Геометрия: границы и пересечения содержательных блоков',9:'Текст: оценка переполнения и сравнение с PDF',10:'Стиль: контраст, шрифты и явная замена отсутствующих',11:'Смысл: VLM-проверка только при подключённой модели',12:'Исправления: только выбранные пункты, исходная версия сохраняется'},None),
      (12,{28:'Что уже проверено',29:'Реальные PPTX → PDF → PNG.\nТри шаблона, три варианта.\nNative-текст, таблицы и графики с Excel-данными.\n\nБраузерный сценарий: загрузка, генерация, просмотр, скачивание и ошибка входного файла.'},None),
      (13,{2:'Ограничения',3:'Live LLM/VLM: endpoint и разрешённая модель не предоставлены; замеров нет.\nSmartArt: 4-шаговый процесс и одна организация на 6 узлов; другие структуры — фигуры.\nПроверка ручного редактирования SmartArt в целевом Office не завершена.\nПримеры содержания синтетические. Замена отсутствующих шрифтов видна в отчёте.'},None),
      (15,{6:'Следующие проверки',8:'Подключить inference организатора и официальный контент',9:'Проверить новый шаблон, отсутствующий в dataset',10:'Сравнить факты, качество дизайна и время полного AI-цикла',11:'Проверить PowerPoint и заявленные браузеры на Windows/macOS',12:'Расширить native-схемы без потери топологии'},None),
      (12,{28:'Пилот на ваших материалах',29:'Один контент.\nРазные фирменные стили.\nРедактируемый результат.\n\nКод, спецификация и воспроизводимые проверки подготовлены.\nКонтакты команды: '+team.get('contact','не предоставлены')},None)
    ]
    manifest={'slides':[]};checks=[]
    for index,(source,values,extra) in enumerate(pages,1):
        part=sourceparts[source-1];tree=parse_xml(parts[part]);before=structure(tree)
        for id,value in values.items():fill(tree,id,value)
        if source in (12,13):
            for shape in tree.findall('.//p:sp',NS):
                nv=shape.find('p:nvSpPr/p:cNvPr',NS)
                if nv is not None and int(nv.get('id')) in values and int(nv.get('id')) not in (2,6,28):
                    for props in shape.findall('.//a:rPr',NS):props.set('sz','2200')
        if source in range(7,12):checks.append({'source_slide':source,'output_slide':index,'design_structure_preserved':before==structure(tree)})
        newpart=f'ppt/slides/slide{9000+index}.xml';sr=parse_xml(parts[rels_path(part)])
        for rel in list(sr):
            if rel.get('Type','').endswith(('/notesSlide','/comments')):sr.remove(rel)
        if extra=='screenshot' and Path('output/browser/result.png').exists():
            imagepart='ppt/media/lct-interface.png';parts[imagepart]=Path('output/browser/result.png').read_bytes();add_override(types,imagepart,'image/png')
            ET.SubElement(sr,'{'+NS['rel']+'}Relationship',Id='lctScreenshot',Type=NS['r']+'/image',Target='../media/lct-interface.png')
            # Actual application screenshot, placed inside the original white content panel.
            from PIL import Image
            with Image.open('output/browser/result.png') as im:iw,ih=im.size
            b=Box(x=650000,y=1600000,w=10700000,h=4500000);scale=min(b.w/iw,b.h/ih)
            tree.find('p:cSld/p:spTree',NS).append(picture_shape(9900,Box(x=b.x+(b.w-iw*scale)/2,y=b.y,w=iw*scale,h=ih*scale),'lctScreenshot','Реальный интерфейс сервиса'))
        if extra=='matrix':
            runs=json.loads(args.matrix.read_text(encoding='utf-8')) if args.matrix.exists() else []
            rows=[['Шаблон','Варианты','Время, с','Режим']]
            if isinstance(runs,dict):runs=runs['runs']
            rows += [[('WorkSpace' if 'WorkSpace' in r['template'] else 'Education' if 'Education' in r['template'] else 'VK Tech'),str(len(r['variants'])),str(r.get('timing',{}).get('generation_seconds',r.get('seconds','—'))),'Без LLM'] for r in runs]
            if not runs:rows.append(['Замер ожидается','—','—','Не проверено'])
            tree.find('p:cSld/p:spTree',NS).append(table_shape(9900,Box(x=700000,y=1750000,w=10700000,h=3200000),rows,'Montserrat','310F53','520978',16))
        from lct_design.speech import attach_notes
        note=attach_notes(parts,newpart,sr,'\n\n'.join(values.values()),index)
        add_override(types,note,'application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml')
        parts[newpart]=xml(tree);parts[rels_path(newpart)]=xml(sr);rid=f'lctPitch{index}'
        ET.SubElement(rels,'{'+NS['rel']+'}Relationship',Id=rid,Type=NS['r']+'/slide',Target='slides/'+Path(newpart).name)
        ET.SubElement(pres.find('p:sldIdLst',NS),q('p:sldId'),{'id':str(256+index),q('r:id'):rid});add_override(types,newpart,SLIDE_CT)
        title=next(iter(values.values()));manifest['slides'].append({'number':index,'title':title,'objects':[{'text':v} for v in values.values()]})
    parts['ppt/presentation.xml']=xml(pres);parts['ppt/_rels/presentation.xml.rels']=xml(rels);parts=prune(parts)
    for n in list(types):
        if n.get('PartName') and n.get('PartName').lstrip('/') not in parts:types.remove(n)
    parts['[Content_Types].xml']=xml(types)
    missing=validate_relationships(parts)
    if missing:raise ValueError(missing)
    args.output.mkdir(parents=True,exist_ok=True);path=args.output/'solution-draft.pptx';write_package(parts,path)
    render=render_deck(path,args.output);html_export(manifest,render,args.output)
    save_json(args.output/'template-preservation.json',{'source_sha256':hashlib.sha256(args.template.read_bytes()).hexdigest(),'mandatory':checks,'team_complete':bool(team),'render':render.model_dump()})
    (args.output/'README.md').write_text('Черновик питча, 15 слайдов. Первые пять — обязательные исходные слайды 7–11. Их геометрия, стили и декоративная структура сохранены; изменён только текст. Данные команды '+('загружены из JSON; проверить полноту.' if team else 'не предоставлены — заявка не готова к отправке.')+'\nРендер: '+render.status+'\n',encoding='utf-8')
    print(path)

if __name__=='__main__':main()
