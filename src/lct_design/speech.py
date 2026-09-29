"""Source-derived speaker text: no extra inference calls or invented facts."""
import re
from lxml import etree as ET
from .package import NS, q, xml, rels_path


def speaker_text(slide):
    paragraphs = [slide.title, *slide.bullets]
    if slide.table:
        headers = slide.table[0]
        for row in slide.table[1:]:
            paragraphs.append('; '.join(f'{h}: {v}' for h, v in zip(headers, row)))
    if slide.chart:
        for name, values in slide.chart.series.items():
            paragraphs.append(name + ': ' + '; '.join(f'{c} — {v:g} {slide.chart.unit}'.strip()
                for c, v in zip(slide.chart.categories, values)))
    if slide.diagram:
        paragraphs.append(' → '.join(slide.diagram) if slide.diagram_kind == 'process' else '; '.join(slide.diagram))
    return '\n\n'.join(dict.fromkeys(p.strip() for p in paragraphs if p.strip()))


def speech_document(plan):
    words = sum(len(re.findall(r'\w+', s.speaker_notes)) for s in plan.slides)
    intro = f'# {plan.title}\n\nТекст составлен из исходных фактов. Оценка при 130 словах/мин: {words / 130:.1f} мин ({words} слов).\n'
    return intro + ''.join(f'\n## {i}. {s.title}\n\n{s.speaker_notes}\n' for i, s in enumerate(plan.slides, 1))


def notes_part(text):
    root = ET.Element(q('p:notes'), nsmap={k: NS[k] for k in ('p', 'a', 'r')})
    common = ET.SubElement(root, q('p:cSld')); shapes = ET.SubElement(common, q('p:spTree'))
    group = ET.SubElement(shapes, q('p:nvGrpSpPr'))
    ET.SubElement(group, q('p:cNvPr'), id='1', name='')
    ET.SubElement(group, q('p:cNvGrpSpPr')); ET.SubElement(group, q('p:nvPr'))
    ET.SubElement(shapes, q('p:grpSpPr'))
    shape = ET.SubElement(shapes, q('p:sp')); nv = ET.SubElement(shape, q('p:nvSpPr'))
    ET.SubElement(nv, q('p:cNvPr'), id='2', name='Speaker notes')
    ET.SubElement(nv, q('p:cNvSpPr')); ph = ET.SubElement(nv, q('p:nvPr'))
    ET.SubElement(ph, q('p:ph'), type='body', idx='1')
    ET.SubElement(shape, q('p:spPr')); body = ET.SubElement(shape, q('p:txBody'))
    ET.SubElement(body, q('a:bodyPr')); ET.SubElement(body, q('a:lstStyle'))
    for line in text.splitlines():
        paragraph = ET.SubElement(body, q('a:p'))
        run = ET.SubElement(paragraph, q('a:r')); ET.SubElement(run, q('a:t')).text = line
    override = ET.SubElement(root, q('p:clrMapOvr')); ET.SubElement(override, q('a:masterClrMapping'))
    return xml(root)


def attach_notes(parts, slide_part, slide_rels, text, index):
    name = f'ppt/notesSlides/notesSlide{index + 10000}.xml'
    parts[name] = notes_part(text)
    rels = ET.Element('{'+NS['rel']+'}Relationships', nsmap={None:NS['rel']})
    ET.SubElement(rels, '{'+NS['rel']+'}Relationship', Id='slide', Type=NS['r']+'/slide', Target='../slides/'+slide_part.rsplit('/',1)[1])
    parts[rels_path(name)] = xml(rels)
    ET.SubElement(slide_rels, '{'+NS['rel']+'}Relationship', Id='lctNotes', Type=NS['r']+'/notesSlide', Target='../notesSlides/'+name.rsplit('/',1)[1])
    return name
