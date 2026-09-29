from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Box(Model):
    x: float
    y: float
    w: float
    h: float

class Slot(Model):
    id: str
    role: str = 'body'
    box: Box
    font: str = 'Arial'
    size: float = 20
    color: str = '111111'
    text: str = ''

class Pattern(Model):
    id: str
    part: str
    index: int
    scope: str
    slots: list[Slot] = []
    family: str = 'content'
    complexity: int = 0
    background: str = 'FFFFFF'
    confidence: float = .7
    visual_features: list[float] = []
    artwork: list[Box] = []
    frames: list[Box] = []
    schema: dict = {}

class TemplateProfile(Model):
    version: str = '1.0'
    hash: str
    filename: str
    width: int
    height: int
    colors: list[str]
    fonts: list[str]
    font_sizes: list[float]
    patterns: list[Pattern]
    warnings: list[str] = []
    asset_count: int = 0
    analysis: dict = {}

class Chart(Model):
    title: str = ''
    categories: list[str] = Field(min_length=1, max_length=30)
    series: dict[str, list[float]]
    unit: str = ''

    @model_validator(mode='after')
    def dimensions(self):
        import math
        if not 1 <= len(self.series) <= 5 or any(len(v)!=len(self.categories) for v in self.series.values()):
            raise ValueError('Chart dimensions do not match categories (1–5 series)')
        if any(not math.isfinite(n) for values in self.series.values() for n in values):
            raise ValueError('Chart values must be finite')
        return self

class Item(Model):
    """One block of a slide: a card, list row, step or metric."""
    heading: str = Field(default='', max_length=300)
    text: str = Field(default='', max_length=2000)
    value: str = Field(default='', max_length=40)

class Section(Model):
    id: str
    title: str = Field(min_length=1, max_length=500)
    bullets: list[str] = []
    lead: str = Field(default='', max_length=1000)
    items: list[Item] = Field(default_factory=list, max_length=12)
    note: str = Field(default='', max_length=1000)
    button: str = Field(default='', max_length=60)
    table: list[list[str]] | None = None
    chart: Chart | None = None
    diagram: list[str] | None = None
    diagram_kind: Literal['process', 'hierarchy'] = 'process'
    diagram_parents: list[int | None] | None = None
    diagram_assistant: int | None = None
    image: str | None = None
    notes: str = Field(default='', max_length=5000)

    @model_validator(mode='after')
    def bounded_visual(self):
        if sum(x is not None for x in (self.table,self.chart,self.diagram,self.image))>1:
            raise ValueError('Use one visual per section; separate charts, tables and images into sections')
        if len(self.bullets)>50 or any(len(b)>10000 for b in self.bullets):raise ValueError('At most 50 bullets of 10000 characters')
        if self.table is not None and (not self.table or not self.table[0] or len(self.table)>40 or max(map(len,self.table))>12 or len(set(map(len,self.table)))!=1 or any(len(v)>5000 for row in self.table for v in row)):
            raise ValueError('Table must be nonempty and rectangular, at most 40 × 12')
        if self.diagram is not None and (not 1<=len(self.diagram)<=20 or any(len(v)>500 for v in self.diagram)):
            raise ValueError('Diagram needs 1–20 labels of at most 500 characters')
        if self.diagram_parents is not None:
            if not self.diagram or self.diagram_kind!='hierarchy' or len(self.diagram_parents)!=len(self.diagram):raise ValueError('Parents must match hierarchy labels')
            for i,parent in enumerate(self.diagram_parents):
                if (i==0 and parent is not None) or (i>0 and (parent is None or not 0<=parent<i)):raise ValueError('Hierarchy: first node is root; each following node references an earlier parent')
        if self.diagram_assistant is not None and (not self.diagram or self.diagram_kind!='hierarchy' or not 1<=self.diagram_assistant<len(self.diagram)):
            raise ValueError('Assistant must reference a non-root hierarchy node')
        if self.image:
            from .images import decode_image
            decode_image(self.image)
        return self

class ContentPackage(Model):
    title: str = Field(min_length=1, max_length=500)
    brief: str = Field(default='', max_length=50000)
    purpose: str = 'product'
    language: str = 'ru'
    sections: list[Section] = Field(default_factory=list, max_length=50)
    synthetic: bool = False
    speaker: str = Field(default='', max_length=200)
    link: str = Field(default='', max_length=500)

    @model_validator(mode='after')
    def unique_sources(self):
        ids=[s.id for s in self.sections]
        if len(ids)!=len(set(ids)): raise ValueError('Section source IDs must be unique')
        for s in self.sections:
            if s.table and (len(s.table)>40 or max(map(len,s.table))>12 or len(set(map(len,s.table)))!=1):
                raise ValueError('Table must be rectangular, at most 40 rows and 12 columns')
        return self

class LayoutChoice(Model):
    pattern_id:str
    body_slot_ids:list[str]=Field(default_factory=list,max_length=6)

class PlannedSlide(Model):
    title: str
    speaker_notes: str = ''
    source_ids: list[str]
    bullets: list[str] = []
    table: list[list[str]] | None = None
    chart: Chart | None = None
    diagram: list[str] | None = None
    diagram_kind: str = 'process'
    diagram_parents: list[int | None] | None = None
    diagram_assistant: int | None = None
    image: str | None = None
    lead: str = ''
    items: list[Item] = []
    note: str = ''
    button: str = ''
    layouts:dict[str,LayoutChoice]=Field(default_factory=dict)

class DeckPlan(Model):
    title: str
    slides: list[PlannedSlide]
    mode: Literal['offline','live']
    model: str | None = None
    usage: dict = {}
    outline_usage: dict = {}
    speaker: str = ''
    link: str = ''
    warnings: list[str] = []

class Finding(Model):
    id: str
    rule: str
    severity: Literal['error','warning','info']
    kind: Literal['deterministic','heuristic','contextual'] = 'deterministic'
    status: Literal['failed','warning','not_run','passed'] = 'failed'
    slide: int | None = None
    object_id: str | None = None
    box: Box | None = None
    message: str
    evidence: dict = {}
    repair: str | None = None

class RenderResult(Model):
    status: Literal['complete','unavailable','failed']
    pdf: str | None = None
    images: list[str] = []
    error: str | None = None
    engine: str = ''
    seconds: float = 0

class GenerateRequest(Model):
    template_id: str
    content: ContentPackage
    variants: list[Literal['sequential','comparison','focus']] = ['sequential','comparison','focus']
    mode: Literal['offline','live'] = 'offline'
    slide_count: int = Field(default=12, ge=1, le=50)
