from .models import Box
from .visuals import element,sub,transform

def vector_boxes(labels,kind,parents,box):
    n=len(labels);regions=[]
    if kind=='hierarchy':
        parents=parents or [None]+[0]*(n-1);depths=[0]*n
        for i in range(1,n):depths[i]=depths[parents[i]]+1
        rows=max(depths)+1;rowheight=box.h/rows
        for i in range(n):
            peers=[j for j in range(n) if depths[j]==depths[i]];width=box.w/len(peers);pos=peers.index(i)
            regions.append(Box(x=box.x+pos*width+width*.04,y=box.y+depths[i]*rowheight,w=width*.92,h=rowheight*.65))
        return regions,[(parents[i],i) for i in range(1,n)]
    cols=min(n,4);rows=(n+cols-1)//cols;cw=box.w/cols;rh=box.h/rows
    for i in range(n):regions.append(Box(x=box.x+(i%cols)*cw,y=box.y+(i//cols)*rh+rh*.2,w=cw*.84,h=rh*.55))
    return regions,[(i,i+1) for i in range(n-1)]

def connector(id,a,b,color):
    x1,y1=a.x+a.w/2,a.y+a.h;x2,y2=b.x+b.w/2,b.y
    if abs(a.y-b.y)<1:x1,y1,x2,y2=a.x+a.w,a.y+a.h/2,b.x,b.y+b.h/2
    sp=element('p:cxnSp');nv=sub(sp,'p:nvCxnSpPr');sub(nv,'p:cNvPr',id=id,name=f'LCT connector {id}');sub(nv,'p:cNvCxnSpPr');sub(nv,'p:nvPr')
    props=sub(sp,'p:spPr');t=transform(props,Box(x=min(x1,x2),y=min(y1,y2),w=max(1,abs(x2-x1)),h=max(1,abs(y2-y1))))
    if x2<x1:t.set('flipH','1')
    if y2<y1:t.set('flipV','1')
    sub(sub(props,'a:prstGeom',prst='line'),'a:avLst');line=sub(props,'a:ln',w=19050);sub(sub(line,'a:solidFill'),'a:srgbClr',val=color);sub(line,'a:tailEnd',type='triangle')
    return sp
