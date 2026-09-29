from zipfile import ZipFile
import pytest
from lct_design.package import read_package, parse_xml, PackageError

def test_safe_template(template):
    assert 'ppt/presentation.xml' in read_package(template)

def test_traversal(tmp_path):
    p=tmp_path/'bad.pptx'
    with ZipFile(p,'w') as z: z.writestr('../escape.xml','x')
    with pytest.raises(PackageError, match='path'): read_package(p)

def test_entities_rejected():
    with pytest.raises(PackageError, match='DTD'):
        parse_xml(b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///secret">]><a>&x;</a>')

def test_external_links_neutralized(template):
    with ZipFile(template,'a') as z:
        z.writestr('ppt/slides/_rels/slide1.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="evil" Type="hyperlink" TargetMode="External" Target="https://example.org"/></Relationships>')
    assert b'example.org' not in read_package(template)['ppt/slides/_rels/slide1.xml.rels']
def test_utf16_and_utf32_dtd_are_rejected():
    import pytest
    from lct_design.package import parse_xml,PackageError
    text='<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x SYSTEM "file:///secret">]><a>&x;</a>'
    for encoding in ('utf-16','utf-32'):
        with pytest.raises(PackageError):parse_xml(text.encode(encoding))
