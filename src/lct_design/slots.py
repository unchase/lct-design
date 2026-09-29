"""Template block semantics: what each sample block is for, and filling it in place.

A template marks its blocks with sample text ("Заголовок", "Текст", "x%", "QR-code").
The schema records those roles and repeated item groups (cards, rows, steps); content
fills a pattern only when every required block receives matching content, and text is
written into the original shapes so bullets, colours, sizes and geometry are kept.
"""
import copy, math, re
from .package import NS, q
from .models import Box, Item
from .layout import estimate_lines

INSTRUCTION = re.compile(r'используются для|можно брать|можно свободно|уже задан|выравнива|шрифт для|иконки можно|icons library|\bbody\s*\{|padding\s*:|font-family|replace this|use this slide')
QR = re.compile(r'\bqr\b|qr[\s-]?code|qr-код')
MEDIA = re.compile(r'(вставить\s*)?(сюда\s*)?(фото\w*|иллюстрац\w*|изображени\w*|скриншот\w*|картинк\w*|photo|image|picture|screenshot)|вставить')
SPEAKER = re.compile(r'имя|фамили|спикер|должност|\bfull name\b|\bposition\b|\bspeaker\b')
BUTTON = re.compile(r'перейти|ссылка|подробнее|узнать больше|кнопка|link|button|learn more')
LABEL = re.compile(r'примечание|пояснение|дата|важно|note|date')
INDEX = re.compile(r'0\d|\d')
METRIC = re.compile(r'[>≈~+\-]?\s*(\d[\d\s.,]*|[xх×]{1,3})\s*(%|\*|млн|тыс|k|m)?\*?')
HEADING = re.compile(r'заголовок|подзаголовок|название( [\wа-я]+)?|важное событие|heading|subheading')
SUBTITLE = re.compile(r'текст описания|описание слайда|subtitle|description')
REPEATABLE = {'heading', 'text', 'list', 'mixed', 'metric', 'speaker', 'index'}


def norm(text):
    return re.sub(r'\s+', ' ', (text or '').replace('​', '').strip().lower())


def para_text(p):
    return ''.join(p.xpath('.//a:t/text()', namespaces=NS))


def run_texts(p):
    return [''.join(r.xpath('./a:t/text()', namespaces=NS)) for r in p.findall('a:r', NS)]


def bulleted(p):
    ppr = p.find('a:pPr', NS)
    return ppr is not None and (ppr.find('a:buChar', NS) is not None or ppr.find('a:buAutoNum', NS) is not None)


def paragraphs(shape):
    body = shape.find('p:txBody', NS)
    return body.findall('a:p', NS) if body is not None else []


def line_kind(text):
    t = norm(text)
    if not t: return None
    if INSTRUCTION.search(t): return 'instruction'
    if QR.search(t): return 'qr'
    if MEDIA.fullmatch(t): return 'media'
    if SPEAKER.search(t) and len(t) <= 40: return 'speaker'
    if BUTTON.fullmatch(t): return 'button'
    if LABEL.fullmatch(t): return 'label'
    if INDEX.fullmatch(t): return 'index'
    if METRIC.fullmatch(t): return 'metric'
    if HEADING.fullmatch(t): return 'heading'
    if SUBTITLE.fullmatch(t): return 'subtitle'
    return 'text'


def slot_kind(shape, slot, smallest):
    paras = [p for p in paragraphs(shape) if norm(para_text(p))]
    if not paras: return 'text'
    kinds = []
    for p in paras:
        runs = [r for r in run_texts(p) if norm(r)]
        # "x% данные показателя": the value is its own run inside the first paragraph.
        first = runs[0] if runs and METRIC.fullmatch(norm(runs[0])) else para_text(p)
        kinds.append(line_kind(first))
    if 'instruction' in kinds: return 'instruction'
    head = kinds[0]
    if head in ('qr', 'media', 'button', 'label', 'index', 'metric'): return head
    if 'speaker' in kinds: return 'speaker'
    if len(paras) >= 2 and head == 'heading': return 'mixed'
    if any(bulleted(p) for p in paras) or (len(paras) >= 2 and all(k == 'text' for k in kinds)): return 'list'
    if head in ('subtitle', 'heading'): return head
    # Real sample content rather than a prompt: a short, larger line is a heading.
    if len(paras) == 1 and len(norm(para_text(paras[0])).split()) <= 4 and slot.size >= smallest * 1.15: return 'heading'
    return 'text'


def _order(group, W, H):
    ys = [s.box.y for s, _ in group]; xs = [s.box.x for s, _ in group]
    if max(ys) - min(ys) <= H * .06: return sorted(group, key=lambda e: e[0].box.x), 'row'
    if max(xs) - min(xs) <= W * .06: return sorted(group, key=lambda e: e[0].box.y), 'column'
    return sorted(group, key=lambda e: (round(e[0].box.y / (H * .1)), e[0].box.x)), 'grid'


def build_schema(tree, slots, width, height):
    """Roles of a pattern's blocks: title, repeated items and single blocks."""
    shapes = {}
    for sp in tree.findall('.//p:sp', NS):
        nv = sp.find('p:nvSpPr/p:cNvPr', NS)
        if nv is not None: shapes[nv.get('id')] = sp
    title = next((s for s in slots if s.role == 'title'), None)
    bodies = [s for s in slots if s.role == 'body' and s.id in shapes]
    smallest = min([s.size for s in bodies] or [18])
    entries = [(s, slot_kind(shapes[s.id], s, smallest)) for s in bodies]
    schema = {'title': title.id if title else None, 'items': [], 'orientation': None, 'singles': [],
              'instruction': any(k == 'instruction' for _, k in entries)}
    groups = []
    for s, k in entries:
        if k not in REPEATABLE: continue
        for g in groups:
            r = g[0][0]
            if g[0][1] == k and abs(s.box.w - r.box.w) <= r.box.w * .25 and abs(s.box.h - r.box.h) <= max(r.box.h * .35, height * .02) and abs(s.size - r.size) <= 1.5:
                g.append((s, k)); break
        else:
            groups.append([(s, k)])
    groups = [g for g in groups if len(g) >= 2]
    grouped = set()
    if groups:
        n = max(len(g) for g in groups)
        chosen = [g for g in groups if len(g) == n]
        items = [dict() for _ in range(n)]
        for g in chosen:
            ordered, orientation = _order(g, width, height)
            schema['orientation'] = schema['orientation'] or orientation
            for i, (s, k) in enumerate(ordered):
                key = k if k not in items[i] else k + '2'
                items[i][key] = s.id; grouped.add(s.id)
        schema['items'] = items
    singles = [(s, k) for s, k in entries if s.id not in grouped]
    # A text block right under the title is its subtitle (lead).
    if title:
        for i, (s, k) in enumerate(singles):
            if k == 'text' and title.box.y + title.box.h * .5 <= s.box.y <= title.box.y + title.box.h + height * .12 and s.box.w >= width * .4:
                singles[i] = (s, 'subtitle')
    # A label ("Примечание") with a text block just below it forms a note.
    for i, (s, k) in enumerate(singles):
        if k != 'label': continue
        for j, (t, tk) in enumerate(singles):
            if tk == 'text' and 0 <= t.box.y - (s.box.y + s.box.h) <= height * .12 and t.box.x < s.box.x + s.box.w and s.box.x < t.box.x + t.box.w:
                singles[i] = (s, 'note_label'); singles[j] = (t, 'note_text'); break
    schema['singles'] = [{'id': s.id, 'kind': k} for s, k in singles]
    return schema


def describe(schema):
    """Compact schema summary for the model: which content a pattern expects."""
    parts = []
    if schema.get('items'):
        kinds = sorted(k.rstrip('2') for k in schema['items'][0])
        parts.append(f"{len(schema['items'])}×[{','.join(kinds)}] {schema.get('orientation') or ''}".strip())
    parts += sorted({s['kind'] for s in schema.get('singles', []) if s['kind'] not in ('index',)})
    return '; '.join(parts) or 'title only'


def units(slide):
    return list(slide.items) if slide.items else [Item(text=b) for b in slide.bullets]


def plan_fill(pattern, slide, deck, visual):
    """Map slide content onto a pattern's blocks, or None when a block would stay wrong or empty."""
    sc = pattern.blocks
    if not sc or sc.get('instruction') or not sc.get('title'): return None
    fill = {sc['title']: {'kind': 'title', 'paras': [slide.title]}}
    content = units(slide); used = False; lead = slide.lead
    kinds = {s['kind'] for s in sc['singles']}
    if not sc['items'] and not kinds & {'text', 'list', 'mixed', 'metric'} and len(content) == 1 and not lead:
        lead = content[0].text or content[0].heading; content = []  # cover: one line becomes the lead
    if sc['items']:
        if len(content) != len(sc['items']): return None
        for n, (item, unit) in enumerate(zip(sc['items'], content), 1):
            for key, sid in item.items():
                kind = key.rstrip('2')
                if kind == 'heading':
                    if not unit.heading: return None
                    fill[sid] = {'kind': 'heading', 'paras': [unit.heading]}
                elif kind == 'text':
                    text = unit.text if 'heading' in item or 'mixed' in item else (f'{unit.heading} — {unit.text}' if unit.heading and unit.text else unit.text or unit.heading)
                    if not text: return None
                    fill[sid] = {'kind': 'text', 'paras': [text]}
                elif kind == 'list':
                    text = unit.text or unit.heading
                    if not text: return None
                    fill[sid] = {'kind': 'list', 'paras': [p.strip() for p in re.split(r';\s+|\n', text) if p.strip()]}
                elif kind == 'mixed':
                    if not (unit.heading and unit.text): return None
                    fill[sid] = {'kind': 'mixed', 'paras': [unit.heading, unit.text]}
                elif kind == 'metric':
                    if not unit.value: return None
                    fill[sid] = {'kind': 'metric', 'paras': [unit.value, unit.heading or unit.text, unit.text if unit.heading else '']}
                elif kind == 'speaker':
                    if not unit.heading: return None
                    fill[sid] = {'kind': 'speaker', 'paras': [unit.heading, unit.text]}
                elif kind == 'index':
                    fill[sid] = {'keep': True}  # step numbers already match the item count
                else:
                    return None
        used = True
    lead_used = False; note_used = False
    for single in sc['singles']:
        sid, kind = single['id'], single['kind']
        if kind in ('subtitle', 'heading'):
            if lead and not lead_used: fill[sid] = {'kind': 'text', 'paras': [lead]}; lead_used = True
            else: fill[sid] = {'remove': True}
        elif kind in ('text', 'list', 'mixed'):
            if not used and content:
                paras = [f'{u.heading} — {u.text}' if u.heading and u.text else (u.text or u.heading) for u in content]
                fill[sid] = {'kind': 'list' if kind == 'list' or len(paras) > 1 else 'text', 'paras': paras}; used = True
            elif lead and not lead_used: fill[sid] = {'kind': 'text', 'paras': [lead]}; lead_used = True
            else: fill[sid] = {'remove': True}
        elif kind == 'metric':
            if used or len(content) != 1 or not content[0].value: return None
            u = content[0]
            fill[sid] = {'kind': 'metric', 'paras': [u.value, u.heading or u.text, u.text if u.heading else '']}; used = True
        elif kind == 'speaker':
            if deck.speaker: fill[sid] = {'kind': 'speaker', 'paras': [p.strip() for p in deck.speaker.split(',', 1) if p.strip()]}
            elif lead and not lead_used: fill[sid] = {'kind': 'text', 'paras': [lead]}; lead_used = True
            else: fill[sid] = {'remove': True}
        elif kind == 'qr':
            if not deck.link: return None
            fill[sid] = {'qr': deck.link}
        elif kind == 'button':
            if not deck.link: return None
            fill[sid] = {'kind': 'button', 'paras': [slide.button or 'Подробнее'], 'link': deck.link}
        elif kind == 'note_label':
            fill[sid] = {'keep': True} if slide.note else {'remove': True}
        elif kind == 'note_text':
            if slide.note: fill[sid] = {'kind': 'text', 'paras': [slide.note]}; note_used = True
            else: fill[sid] = {'remove': True}
        elif kind == 'label':
            fill[sid] = {'remove': True}
        elif kind == 'media':
            if not visual: return None
            fill[sid] = {'media': True}
        elif kind == 'index':
            fill[sid] = {'keep': True}
        else:
            return None
    if content and not used: return None  # the slide's points would be lost
    if visual and not any(v.get('media') for v in fill.values()) and not pattern.frames: return None
    if not visual and pattern.frames: return None
    if not capacity_ok(pattern, fill): return None
    return fill


def capacity_ok(pattern, fill):
    """Every text block holds its content at >=12 pt (or its own smaller template size)."""
    slots = {s.id: s for s in pattern.slots}
    for sid, spec in fill.items():
        slot = slots.get(sid)
        if slot is None or 'paras' not in spec or spec.get('kind') in ('title', 'index'): continue
        size = min(slot.size, 12.0)
        box = effective_box(pattern, slot)
        lines = sum(estimate_lines(t, size, max(1, box.w - 100000)) for t in spec['paras'] if t)
        if lines * size * 1.2 > max(1, box.h / 12700 - 4) * 1.15: return False
    return True


def effective_box(pattern, slot):
    """A block's usable box: it may not run into the next block below it."""
    b = slot.box; below = [s.box.y for s in pattern.slots if s.id != slot.id and s.role != 'footer' and s.box.y > b.y + b.h * .3
                           and s.box.x < b.x + b.w and b.x < s.box.x + s.box.w]
    if below and min(below) < b.y + b.h:
        return Box(x=b.x, y=b.y, w=b.w, h=max(b.h * .35, min(below) - b.y - 60000))
    return b


def fill_score(pattern, fill):
    filled = sum(1 for v in fill.values() if 'paras' in v or 'qr' in v or 'media' in v)
    removed = sum(1 for v in fill.values() if v.get('remove'))
    return filled - removed * 1.2


def choose(profile, slide, deck, variant, index, usage, limit, avoid=None, choice=None, visual=False):
    """Best pattern whose blocks this slide fills completely, honouring the model's choice."""
    candidates = []
    for p in profile.patterns:
        if p.family in ('guide', 'code') or (avoid and p.id in avoid): continue
        fill = plan_fill(p, slide, deck, visual)
        if fill is not None: candidates.append((p, fill))
    if not candidates: return None
    if choice:
        match = next((c for c in candidates if c[0].id == choice.pattern_id), None)
        if match and (not limit or usage.get(match[0].id, 0) < limit): return match

    def score(c):
        p, fill = c; sc = p.blocks; n = len(sc['items'])
        s = fill_score(p, fill)
        if index == 0: s += 4 if p.family == 'cover' else -4
        elif p.family == 'cover': s -= 3
        if variant == 'comparison' and n >= 2 and sc.get('orientation') in ('row', 'grid'): s += 2
        if variant == 'sequential' and (sc.get('orientation') == 'column' or not n): s += 1
        if variant == 'focus': s += 1.5 if n == 0 else -.3 * n
        if slide.button and any(v.get('qr') or v.get('kind') == 'button' for v in fill.values()): s += 3
        s -= usage.get(p.id, 0) * 1.5
        if limit and usage.get(p.id, 0) >= limit: s -= 6
        return s
    return max(candidates, key=score)


def _clone(proto, text):
    p = copy.deepcopy(proto)
    runs = p.findall('a:r', NS)
    for node in list(p):
        if node.tag in (q('a:r'), q('a:br'), q('a:fld')) and (not runs or node is not runs[0]): p.remove(node)
    if runs:
        run = runs[0]
    else:
        run = p.makeelement(q('a:r'), {})
        end = p.find('a:endParaRPr', NS)
        if end is not None:
            rpr = copy.deepcopy(end); rpr.tag = q('a:rPr'); run.append(rpr)
        p.insert(len(p.findall('a:pPr', NS)), run)
    t = run.find('a:t', NS)
    if t is None: t = run.makeelement(q('a:t'), {}); run.append(t)
    t.text = text
    return p


def _metric(protos, paras):
    value, label, text = (paras + ['', '', ''])[:3]
    first = copy.deepcopy(protos[0]); runs = [r for r in first.findall('a:r', NS) if norm(''.join(r.xpath('./a:t/text()', namespaces=NS)))]
    out = []
    if len(runs) >= 2:
        runs[0].find('a:t', NS).text = value
        runs[1].find('a:t', NS).text = (' ' if label else '') + label
        for extra in runs[2:]: first.remove(extra)
        out.append(first)
        if text: out.append(_clone(protos[1] if len(protos) > 1 else protos[0], text))
    else:
        out.append(_clone(protos[0], value))
        if label: out.append(_clone(protos[1] if len(protos) > 1 else protos[0], label))
        if text: out.append(_clone(protos[2] if len(protos) > 2 else protos[-1], text))
    return out


def _sizes(p, default):
    return [float(r.get('sz')) / 100 if r.get('sz') else default for r in p.iter(q('a:rPr'), q('a:endParaRPr'))] or [default]


def _fit(shape, slot, width_emu, scale, extra=1.0, floor_pt=12):
    """Shrink runs to the largest template type size that fits the box (never below floor_pt)."""
    body = shape.find('p:txBody', NS); paras = body.findall('a:p', NS)
    available = max(1, slot.box.h / 12700 - 6)
    top = max(max(_sizes(p, slot.size)) for p in paras) if paras else slot.size
    def height(f):
        return sum(estimate_lines(para_text(p) or ' ', max(_sizes(p, slot.size)) * f, width_emu) * max(_sizes(p, slot.size)) * f * 1.2 for p in paras)
    # Candidate factors come from the template's own type scale, so sizes stay on it.
    steps = sorted({v / top for v in scale if min(floor_pt, top) <= v <= top * extra} | {min(1.0, extra)}, reverse=True)
    f = next((c for c in steps if height(c) <= available), steps[-1])
    if f != 1.0:
        for p in paras:
            for r in p.iter(q('a:rPr'), q('a:endParaRPr')):
                r.set('sz', str(int(round((float(r.get('sz')) / 100 if r.get('sz') else slot.size) * f * 100))))
    bpr = body.find('a:bodyPr', NS)
    if bpr is not None:
        # Keep the template geometry: text must not grow its box over neighbouring blocks.
        for tag in ('a:spAutoFit', 'a:normAutofit'):
            for node in bpr.findall(tag, NS): bpr.remove(node)
    return f, height(f) > available


def _remove(shape, tree):
    parent = shape.getparent()
    if parent is not None: parent.remove(shape)


def apply_fill(tree, pattern, fill, profile, index, repairs=None, recolor=None):
    """Write planned content into the pattern's own shapes. Returns manifest objects and media targets."""
    shapes = {}
    for sp in tree.findall('.//p:sp', NS):
        nv = sp.find('p:nvSpPr/p:cNvPr', NS)
        if nv is not None: shapes[nv.get('id')] = sp
    slots = {s.id: s for s in pattern.slots}
    objects = []; media = []; qr = []; counters = {}
    for sid, spec in fill.items():
        shape = shapes.get(sid); slot = slots.get(sid)
        if shape is None or slot is None: continue
        if spec.get('remove'): _remove(shape, tree); continue
        if spec.get('keep'): continue
        if spec.get('media') or spec.get('qr'):
            for p in paragraphs(shape): p.getparent().remove(p)
            body = shape.find('p:txBody', NS)
            if body is not None: body.append(body.makeelement(q('a:p'), {}))
            b = slot.box
            if spec.get('qr'):
                side = min(b.w, b.h) * .8
                qr.append((Box(x=b.x + (b.w - side) / 2, y=b.y + (b.h - side) / 2, w=side, h=side), spec['qr']))
            else:
                media.append(Box(x=b.x + b.w * .05, y=b.y + b.h * .05, w=b.w * .9, h=b.h * .9))
            continue
        kind = spec['kind']; texts = [t for t in spec['paras'] if t]
        protos = [p for p in paragraphs(shape) if norm(para_text(p))] or paragraphs(shape)
        if not protos or not texts: _remove(shape, tree); continue
        if kind == 'list':
            proto = next((p for p in protos if bulleted(p)), protos[0]); built = [_clone(proto, t) for t in texts]
        elif kind in ('mixed', 'speaker'):
            built = [_clone(protos[min(i, len(protos) - 1)], t) for i, t in enumerate(texts)]
        elif kind == 'metric':
            built = _metric(protos, spec['paras'])
        else:
            built = [_clone(protos[0], t) for t in texts]
        body = shape.find('p:txBody', NS)
        for p in paragraphs(shape): body.remove(p)
        for p in built: body.append(p)
        base = 'title' if kind == 'title' else 'body' if kind in ('text', 'list', 'mixed') else kind
        counters[base] = counters.get(base, -1) + 1
        role = 'title' if kind == 'title' else f'{base}-{counters[base]}'
        extra = .82 if repairs and f'{index + 1}:{role}' in repairs else 1.0
        room = slot.model_copy(update={'box': effective_box(pattern, slot)})
        factor, overflow = _fit(shape, room, max(1, slot.box.w - 100000), profile.font_sizes + list(range(12, int(slot.size) + 1)), extra)
        color = slot.color
        if recolor and role in recolor:
            color = recolor[role]
            for r in shape.iter(q('a:rPr')):
                for old in r.findall('a:solidFill', NS): r.remove(old)
                fill_el = r.makeelement(q('a:solidFill'), {}); clr = fill_el.makeelement(q('a:srgbClr'), {'val': color}); fill_el.append(clr)
                r.insert(0, fill_el)
        objects.append({'id': sid, 'role': role, 'box': slot.box.model_dump(), 'text': '\n'.join(texts), 'font': slot.font,
                        'size': round(slot.size * factor, 1), 'color': color, 'overflow': overflow, 'filled_in_place': True})
    return objects, media, qr
