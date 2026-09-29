"""Brief-to-content generation: the model writes structure and wording, code keeps facts grounded."""
import re
from pydantic import ValidationError
from .models import Section, Chart

NUMBER = re.compile(r'\d+(?:[   ]\d{3})*(?:[.,]\d+)?')


def numbers(text):
    """Normalized numeric tokens: '5 000' -> '5000', '2,5' -> '2.5'."""
    found = set()
    for raw in NUMBER.findall(text or ''):
        value = re.sub(r'[   ]', '', raw).replace(',', '.')
        if '.' in value: value = value.rstrip('0').rstrip('.')
        found.add(value.lstrip('0') or '0')
    return found


def grounded(text, allowed):
    return numbers(text) <= allowed


def _number_text(value):
    return f'{value:g}'


def build_sections(data, brief, slide_count):
    """Validate model slides; drop any item whose numbers are absent from the brief."""
    allowed = numbers(brief); warnings = []; sections = []
    slides = data.get('slides') if isinstance(data, dict) else None
    if not isinstance(slides, list) or not slides: raise ValueError('Модель не вернула слайды содержания')
    for i, item in enumerate(slides[:50], 1):
        if not isinstance(item, dict): continue
        title = str(item.get('title') or '').strip()[:300]
        if not title: continue
        if not grounded(title, allowed):
            warnings.append(f'Слайд содержания {i} отброшен: в заголовке есть число, которого нет в брифе.'); continue
        bullets = []
        for b in item.get('bullets') or []:
            b = str(b).strip()[:600]
            if not b: continue
            if grounded(b, allowed): bullets.append(b)
            else: warnings.append(f'Слайд «{title[:60]}»: пункт с числом не из брифа удалён.')
        notes = str(item.get('notes') or '').strip()[:3000]
        if notes and not grounded(notes, allowed):
            warnings.append(f'Слайд «{title[:60]}»: текст выступления с числом не из брифа заменён пунктами слайда.'); notes = ''
        visual = {}
        table, chart, diagram = item.get('table'), item.get('chart'), item.get('diagram')
        try:
            if table:
                cells = [[str(c)[:300] for c in row] for row in table]
                if all(grounded(c, allowed) for row in cells for c in row): visual['table'] = cells
                else: warnings.append(f'Слайд «{title[:60]}»: таблица с числами не из брифа удалена.')
            elif chart:
                parsed = Chart.model_validate(chart)
                values = {_number_text(v) for s in parsed.series.values() for v in s}
                texts = [parsed.title, parsed.unit, *parsed.categories, *parsed.series]
                if values <= allowed and all(grounded(t, allowed) for t in texts): visual['chart'] = parsed
                else: warnings.append(f'Слайд «{title[:60]}»: график с числами не из брифа удалён.')
            elif diagram:
                labels = [str(d).strip()[:200] for d in diagram if str(d).strip()]
                if 2 <= len(labels) <= 8 and all(grounded(l, allowed) for l in labels): visual['diagram'] = labels
        except (ValidationError, TypeError, ValueError):
            warnings.append(f'Слайд «{title[:60]}»: визуализация не прошла проверку и удалена.'); visual = {}
        if not bullets and not visual:
            if notes: bullets = [notes.split('. ')[0][:200]]
            elif i > 1: warnings.append(f'Слайд «{title[:60]}» без содержания отброшен.'); continue
        try: sections.append(Section(id=f'gen-{len(sections)+1}', title=title, bullets=bullets, notes=notes, **visual))
        except ValidationError: sections.append(Section(id=f'gen-{len(sections)+1}', title=title, bullets=bullets, notes=notes))
    if not sections: raise ValueError('После проверки фактов не осталось слайдов содержания')
    if len(sections) != slide_count:
        warnings.append(f'Запрошено {slide_count} слайдов; после проверки фактов осталось {len(sections)}.')
    return sections, warnings
