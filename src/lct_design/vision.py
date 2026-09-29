from pathlib import Path
from PIL import Image,ImageStat

def analyze_visual(profile,render,folder):
    """Deterministic thumbnail features + nearest-representative clustering."""
    if render.status!='complete':
        profile.analysis['visual']='not_run';return profile
    centers=[];clusters={}
    for p in profile.patterns:
        idx=p.index-1
        if idx>=len(render.images): continue
        with Image.open(Path(folder)/render.images[idx]) as im:
            thumb=im.convert('RGB').resize((8,5))
            pixels=list(thumb.get_flattened_data())
            feat=[v/255 for rgb in pixels for v in rgb]
        feature=p.visual_features+feat
        def distance(c):return sum((x-y)**2 for x,y in zip(feature,c))/len(feature)
        scores=[distance(c) for c in centers]
        if not scores or min(scores)>.045: centers.append(feature);group=len(centers)-1
        else: group=scores.index(min(scores))
        p.visual_features=feature;clusters[p.id]=group
    profile.analysis.update({'visual':'complete','visual_algorithm':'8x5 RGB occupancy + structural features; threshold clustering','clusters':clusters,'cluster_count':len(centers),'semantic':'not_run'})
    return profile
