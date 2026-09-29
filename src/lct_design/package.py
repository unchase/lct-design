"""Bounded OPC package handling. Never extract user paths to the filesystem."""
import posixpath
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED
from lxml import etree as ET

NS = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
      'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'rel':'http://schemas.openxmlformats.org/package/2006/relationships',
      'c':'http://schemas.openxmlformats.org/drawingml/2006/chart',
      'ct':'http://schemas.openxmlformats.org/package/2006/content-types',
      'dgm':'http://schemas.openxmlformats.org/drawingml/2006/diagram'}

class PackageError(ValueError): pass

def q(name):
    prefix, local=name.split(':')
    return '{'+NS[prefix]+'}'+local

def parse_xml(data: bytes):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise PackageError('DTD/entities are forbidden')
    try:
        root=ET.fromstring(data, ET.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False))
        if root.getroottree().docinfo.doctype or any(isinstance(n,ET._Entity) for n in root.iter()):
            raise PackageError('DTD/entities are forbidden in every XML encoding')
        return root
    except ET.XMLSyntaxError as exc: raise PackageError('Invalid XML') from exc

def xml(element): return ET.tostring(element, xml_declaration=True, encoding='UTF-8', standalone=True)

def rels_path(part):
    folder, name=posixpath.split(part)
    return posixpath.join(folder,'_rels',name+'.rels')

def target_part(part, target):
    dest=posixpath.normpath(posixpath.join(posixpath.dirname(part),target)) if not target.startswith('/') else target[1:]
    if dest.startswith('../') or '\\' in dest: raise PackageError('Invalid relationship path')
    return dest

def relationships(parts, part):
    data=parts.get(rels_path(part))
    if not data: return {}
    return {r.get('Id'):(r.get('Type','').rsplit('/',1)[-1], target_part(part,r.get('Target','')))
            for r in parse_xml(data) if r.get('TargetMode')!='External'}

def read_package(path: Path) -> dict[str,bytes]:
    path=Path(path)
    if path.stat().st_size>100*1024**2: raise PackageError('PPTX exceeds 100 MB')
    try:
        with ZipFile(path) as z:
            infos=z.infolist()
            if len(infos)>12000 or sum(i.file_size for i in infos)>512*1024**2:
                raise PackageError('Expanded archive exceeds resource limit')
            parts={}
            for info in infos:
                n=info.filename
                if n.startswith('/') or '\\' in n or '..' in PurePosixPath(n).parts or ':' in n:
                    raise PackageError('Invalid archive path')
                if n in parts: raise PackageError('Duplicate archive part')
                if info.flag_bits&1: raise PackageError('Encrypted archive is unsupported')
                if info.is_dir(): continue
                if info.file_size>100*1024**2: raise PackageError('Part exceeds resource limit')
                data=z.read(info)
                if n.endswith(('.xml','.rels')):
                    tree=parse_xml(data)
                    if n.endswith('.rels'):
                        for rel in list(tree):
                            if rel.get('TargetMode')=='External' or any(x in rel.get('Type','').lower() for x in ('oleobject','vbaproject','activex')):
                                tree.remove(rel)
                        data=xml(tree)
                if any(x in n.lower() for x in ('vbaproject','activex','/embeddings/oleobject')): continue
                parts[n]=data
    except (BadZipFile,RuntimeError) as exc: raise PackageError('Invalid or encrypted PPTX archive') from exc
    if 'ppt/presentation.xml' not in parts or '[Content_Types].xml' not in parts:
        raise PackageError('Not a PowerPoint presentation')
    slides=parse_xml(parts['ppt/presentation.xml']).find('p:sldIdLst',NS)
    if slides is None or not 1<=len(slides)<=100: raise PackageError('Expected 1–100 slides')
    return parts

def write_package(parts,path):
    with ZipFile(path,'w',ZIP_DEFLATED) as z:
        for name,data in parts.items(): z.writestr(name,data)

def validate_relationships(parts):
    missing=[]
    for name,data in parts.items():
        if not name.endswith('.rels'): continue
        if name=='_rels/.rels': base=''
        else: base=name.replace('/_rels/','/')[:-5]
        for rel in parse_xml(data):
            if rel.get('TargetMode')=='External': continue
            dest=target_part(base,rel.get('Target',''))
            if dest not in parts: missing.append(dest)
    return missing
