from lxml import etree as ET
from lct_design.models import Box, Item, PlannedSlide, DeckPlan, Pattern, Slot, TemplateProfile
from lct_design.slots import build_schema, plan_fill, apply_fill, choose

NS = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
W, H = 12192000, 6858000


def sp(i, paras, x, y, w, h, ph=None, bullet=False, size=1800):
    nvpr = f'<p:nvPr><p:ph type="{ph}"/></p:nvPr>' if ph else '<p:nvPr/>'
    bu = '<a:pPr><a:buChar char="•"/></a:pPr>' if bullet else ''
    body = ''.join(f'<a:p>{bu}' + ''.join(f'<a:r><a:rPr lang="ru-RU" sz="{sz}"/><a:t>{t}</a:t></a:r>' for t, sz in (runs if isinstance(runs, list) else [(runs, size)])) + '</a:p>' for runs in paras)
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="s{i}"/><p:cNvSpPr/>{nvpr}</p:nvSpPr><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/>'
            f'<a:ext cx="{w}" cy="{h}"/></a:xfrm></p:spPr><p:txBody><a:bodyPr><a:spAutoFit/></a:bodyPr><a:lstStyle/>{body}</p:txBody></p:sp>')


def slot(i, role, x, y, w, h, text, size=18):
    return Slot(id=str(i), role=role, box=Box(x=x, y=y, w=w, h=h), size=size, text=text)


def cards_pattern():
    shapes = [sp(2, ['Заголовок'], 500000, 300000, 9000000, 900000, ph='title', size=3600)]
    slots = [slot(2, 'title', 500000, 300000, 9000000, 900000, 'Заголовок', 36)]
    for n in range(3):
        x = 500000 + n * 3700000
        shapes.append(sp(10 + n, ['Заголовок'], x, 1600000, 3400000, 500000, size=2400))
        shapes.append(sp(20 + n, ['Текст', 'Текст'], x, 2200000, 3400000, 1500000, bullet=True, size=1400))
        slots += [slot(10 + n, 'body', x, 1600000, 3400000, 500000, 'Заголовок', 24), slot(20 + n, 'body', x, 2200000, 3400000, 1500000, 'Текст\nТекст', 14)]
    shapes.append(sp(30, ['Примечание'], 500000, 4400000, 1500000, 350000, size=1400))
    shapes.append(sp(31, ['Текст'], 500000, 4850000, 8000000, 400000, size=1400))
    slots += [slot(30, 'body', 500000, 4400000, 1500000, 350000, 'Примечание', 14), slot(31, 'body', 500000, 4850000, 8000000, 400000, 'Текст', 14)]
    tree = ET.fromstring(f'<p:sld {NS}><p:cSld><p:spTree>{"".join(shapes)}</p:spTree></p:cSld></p:sld>')
    return tree, Pattern(id='cards', part='ppt/slides/slide1.xml', index=1, scope='m', slots=slots, blocks=build_schema(tree, slots, W, H))


def cta_pattern():
    shapes = [sp(2, ['Call to action'], 500000, 1500000, 5000000, 1800000, ph='title', size=6600),
              sp(3, ['QR-code'], 7800000, 1200000, 3500000, 3500000, size=2400),
              sp(4, ['Ссылка'], 500000, 3900000, 2600000, 700000, size=1600)]
    slots = [slot(2, 'title', 500000, 1500000, 5000000, 1800000, 'Call to action', 66), slot(3, 'body', 7800000, 1200000, 3500000, 3500000, 'QR-code', 24),
             slot(4, 'body', 500000, 3900000, 2600000, 700000, 'Ссылка', 16)]
    tree = ET.fromstring(f'<p:sld {NS}><p:cSld><p:spTree>{"".join(shapes)}</p:spTree></p:cSld></p:sld>')
    return tree, Pattern(id='cta', part='ppt/slides/slide2.xml', index=2, scope='m', slots=slots, blocks=build_schema(tree, slots, W, H))


def test_schema_reads_card_row_note_and_cta_blocks():
    _, cards = cards_pattern(); _, cta = cta_pattern()
    items = cards.blocks['items']
    assert len(items) == 3 and set(items[0]) == {'heading', 'list'} and cards.blocks['orientation'] == 'row'
    assert {s['kind'] for s in cards.blocks['singles']} == {'note_label', 'note_text'}
    assert cta.blocks['title'] == '2' and {s['kind'] for s in cta.blocks['singles']} == {'qr', 'button'}


def test_items_must_match_card_count_and_cta_needs_a_link():
    _, cards = cards_pattern(); _, cta = cta_pattern()
    three = PlannedSlide(title='T', source_ids=['a'], items=[Item(heading=f'H{i}', text=f'a{i}; b{i}') for i in range(3)])
    two = PlannedSlide(title='T', source_ids=['a'], items=[Item(heading='H', text='t')] * 2)
    assert plan_fill(cards, three, DeckPlan(title='d', slides=[], mode='live'), False) is not None
    assert plan_fill(cards, two, DeckPlan(title='d', slides=[], mode='live'), False) is None
    ask = PlannedSlide(title='Одобрите бюджет', source_ids=['z'], button='Открыть план')
    assert plan_fill(cta, ask, DeckPlan(title='d', slides=[], mode='live'), False) is None
    assert plan_fill(cta, ask, DeckPlan(title='d', slides=[], mode='live', link='https://example.com'), False) is not None


def test_fill_writes_into_template_shapes_keeping_bullets_and_removing_unused_note():
    tree, cards = cards_pattern()
    slide = PlannedSlide(title='Пилот подтвердил спрос', source_ids=['a'], items=[Item(heading=f'Блок {i}', text=f'Первый {i}; Второй {i}') for i in range(3)])
    deck = DeckPlan(title='d', slides=[], mode='live')
    profile = TemplateProfile(hash='h', filename='t', width=W, height=H, colors=['0077FF'], fonts=['Arial'], font_sizes=[14, 18, 24, 36], patterns=[cards])
    fill = plan_fill(cards, slide, deck, False)
    objects, media, qr = apply_fill(tree, cards, fill, profile, 0)
    ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main', 'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}
    lists = [s for s in tree.findall('.//p:sp', ns) if s.find('p:nvSpPr/p:cNvPr', ns).get('id') == '20']
    paras = lists[0].findall('.//a:p', ns)
    assert [''.join(p.xpath('.//a:t/text()', namespaces=ns)) for p in paras] == ['Первый 0', 'Второй 0']
    assert all(p.find('a:pPr/a:buChar', ns) is not None for p in paras)
    ids = {s.find('p:nvSpPr/p:cNvPr', ns).get('id') for s in tree.findall('.//p:sp', ns)}
    assert '30' not in ids and '31' not in ids  # no note: label and its text are removed, not left as samples
    assert tree.find('.//a:spAutoFit', ns) is None  # boxes keep template geometry
    assert {o['role'] for o in objects} >= {'title', 'heading-0', 'body-0'} and not media and not qr


def test_choose_prefers_a_pattern_the_content_fills():
    tree, cards = cards_pattern(); _, cta = cta_pattern()
    profile = TemplateProfile(hash='h', filename='t', width=W, height=H, colors=[], fonts=[], font_sizes=[14], patterns=[cta, cards])
    slide = PlannedSlide(title='T', source_ids=['a'], items=[Item(heading='H', text='t')] * 3)
    picked = choose(profile, slide, DeckPlan(title='d', slides=[], mode='live'), 'comparison', 3, {}, 4)
    assert picked and picked[0].id == 'cards'
