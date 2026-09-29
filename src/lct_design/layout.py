import math
from .models import Box

def estimate_lines(text,size,width):
    # Conservative line estimate in points; actual render must still be audited.
    chars=max(1,int((width/12700)/(size*.55)))
    return sum(max(1,math.ceil(len(line)/chars)) for line in text.split('\n'))

def fit_text(text,box,size,scale):
    available=max(1,box.h/12700-8)
    candidates=sorted({float(n) for n in scale if max(12,size*.65)<=n<=size}|{size},reverse=True)
    # Prefer the template's type scale, then interpolate down to the readability floor.
    candidates += [float(n) for n in range(int(size),11,-1) if n not in candidates]
    for n in candidates:
        if estimate_lines(text,n,box.w-100000)*n*1.18<=available: return n,False
    n=min(candidates)
    return n,estimate_lines(text,n,box.w-100000)*n*1.18>available

def grow_size(text,box,size,scale,cap):
    """Largest template type-scale size above size (up to cap) that still fits the box."""
    available=max(1,box.h/12700-8)
    for n in sorted({float(v) for v in scale if size<v<=cap},reverse=True):
        if estimate_lines(text,n,box.w-100000)*n*1.18<=available*.9:return n
    return size

def variant_boxes(box,profile,variant,visual=False,items=2):
    """Variant axes applied to one content region: two columns for comparison, inset focus."""
    if variant=='comparison' and not visual and items>=2 and box.w>=profile.width*.4:
        gap=profile.width*.025
        return [Box(x=box.x,y=box.y,w=(box.w-gap)/2,h=box.h),Box(x=box.x+(box.w+gap)/2,y=box.y,w=(box.w-gap)/2,h=box.h)]
    if variant=='focus' and not visual:
        return [Box(x=box.x+box.w*.08,y=box.y+box.h*.08,w=box.w*.84,h=box.h*.84)]
    return [box]

def pattern_limit(slides):
    """One composition may carry at most about a third of a deck."""
    return max(2,math.ceil(slides*.34))

def card_row(pattern,profile):
    """Two or more similar body cards side by side: the template's grid of equal blocks."""
    bodies=sorted([s.box for s in pattern.slots if s.role=='body' and s.box.w>=profile.width*.12 and s.box.h>=profile.height*.12],key=lambda b:b.x)
    if len(bodies)<2:return []
    first=bodies[0]
    row=[b for b in bodies if abs(b.y-first.y)<=profile.height*.05 and .6<=b.w*b.h/(first.w*first.h)<=1.6]
    return row if len(row)>=2 else []

def select_pattern(profile,slide,variant,index,visual_regions=None,usage=None,limit=None,avoid=None):
    eligible=[p for p in profile.patterns if p.family not in ('guide','code') and
              any(s.role=='title' and s.box.y<profile.height*.22 for s in p.slots)]
    eligible=eligible or [p for p in profile.patterns if p.family not in ('guide','code')] or profile.patterns
    if avoid:eligible=[p for p in eligible if p.id not in avoid] or eligible
    # Small captions on pictorial/card layouts are not a free text canvas.
    # Prefer a real body region before checking image collisions.
    spacious=[p for p in eligible if any(s.role=='body' and s.box.w>=profile.width*.3 and
        s.box.h>=profile.height*.25 and s.size<=next(t.size for t in p.slots if t.role=='title')*1.5 for s in p.slots)]
    if spacious:eligible=spacious
    if visual_regions:
        visual=bool(slide.chart or slide.table or slide.diagram or slide.image)
        def collision(p):
            boxes=body_boxes(p,profile,variant,visual)+[s.box for s in p.slots if s.role=='title']
            return sum(max(0,min(a.x+a.w,b.x+b.w)-max(a.x,b.x))*max(0,min(a.y+a.h,b.y+b.h)-max(a.y,b.y))
                for a in boxes for b in visual_regions.get(p.id,[]))/(profile.width*profile.height)
        # Preserve pictures by selecting a compatible source composition, instead of
        # deleting artwork or laying new text on top of sample screenshots/charts.
        free=[p for p in eligible if collision(p)<.015]
        if free:eligible=free
        else:
            best=min(collision(p) for p in eligible)
            eligible=[p for p in eligible if collision(p)<=best+.005]
    usage=usage or {}
    visual=bool(slide.chart or slide.table or slide.diagram or slide.image)
    # Media frames (photo/screenshot panels) suit visuals; on text slides they stay empty.
    if not visual:
        unframed=[p for p in eligible if not p.frames]
        if unframed:eligible=unframed
    if variant=='focus' and not visual:
        # Focus shows one message in one large region, not a grid of cards.
        single=[p for p in eligible if not card_row(p,profile)]
        if single:eligible=single
    if limit:
        # Avoid monotony: once a composition hits its share, choose among the others.
        rested=[p for p in eligible if usage.get(p.id,0)<limit]
        if rested:eligible=rested
    def score(p):
        bodies=[s for s in p.slots if s.role=='body']
        title=next(s for s in p.slots if s.role=='title')
        # Empty title layouts are legitimate adaptable canvases. Dense source diagrams,
        # photo cards and oversized numeric callouts are expensive to repurpose.
        score=p.complexity*.12+len(bodies)*.12-title.box.w/profile.width
        score+=sum(3 for s in bodies if s.size>title.size*1.5)
        if variant=='comparison' and len(bodies) in (2,3):score-=.5
        if variant=='focus' and len(bodies)>1:score+=.5
        if visual and p.frames:score-=1
        return score+usage.get(p.id,0)*.35
    eligible.sort(key=score)
    top=eligible[:min(2,len(eligible))]
    return top[(index+(0 if variant=='sequential' else 1 if variant=='comparison' else 2))%len(top)]

def body_boxes(pattern,profile,variant,visual=False):
    bodies=[s for s in pattern.slots if s.role=='body']
    cards=card_row(pattern,profile) if not visual else []
    if cards and variant!='focus':return cards
    if bodies:
        box=max(bodies,key=lambda s:s.box.w*s.box.h).box.model_copy()
    else:
        title=next(s for s in pattern.slots if s.role=='title')
        top=max(profile.height*.25,title.box.y+title.box.h+profile.height*.04)
        box=Box(x=profile.width*.065,y=top,w=profile.width*.87,h=max(profile.height*.25,profile.height*.9-top))
    title=next(s for s in pattern.slots if s.role=='title')
    has_container=bool(bodies) and box.w>=profile.width*.25 and box.h>=profile.height*.25
    if not has_container and (visual or box.w<profile.width*.4 or box.h<profile.height*.22):
        # Infer a content envelope from the template's occupied body regions and title guide.
        usable=[s.box for s in bodies if s.box.y+s.box.h>title.box.y+title.box.h and s.box.w>=profile.width*.12]
        if usable:
            x=min(b.x for b in usable);y=max(min(b.y for b in usable),title.box.y+title.box.h+profile.height*.025)
            right=max(b.x+b.w for b in usable);bottom=max(b.y+b.h for b in usable)
            box=Box(x=x,y=y,w=right-x,h=max(bottom-y,profile.height*.52))
            box.h=min(box.h,profile.height*.9-box.y)
    if variant=='comparison' and not visual:
        usable=[s.box for s in bodies if s.box.h>=profile.height*.2 and s.box.w>=profile.width*.2 and s.box.y>=title.box.y+title.box.h*.8]
        from itertools import combinations
        for a,b in combinations(sorted(usable,key=lambda b:(b.y,b.x)),2):
            overlap=min(a.y+a.h,b.y+b.h)-max(a.y,b.y)
            if overlap>=min(a.h,b.h)*.5 and (a.x+a.w<=b.x or b.x+b.w<=a.x):return sorted([a,b],key=lambda b:b.x)
        gap=profile.width*.025
        return [Box(x=box.x,y=box.y,w=(box.w-gap)/2,h=box.h),Box(x=box.x+(box.w+gap)/2,y=box.y,w=(box.w-gap)/2,h=box.h)]
    if variant=='focus' and not visual:
        return [Box(x=box.x+box.w*.08,y=box.y+box.h*.08,w=box.w*.84,h=box.h*.84)]
    return [box]
