from fastapi.testclient import TestClient
from lct_design.api import create_app
from lct_design.pipeline import run_job
from lct_design.package import read_package, parse_xml, relationships, validate_relationships, NS


def test_three_variants_include_native_notes_and_measured_speech(tmp_path, template, monkeypatch):
    monkeypatch.setenv('LCT_RENDERER', 'none')
    app = create_app(tmp_path/'data', start_worker=False)
    with TestClient(app) as client:
        tid = client.post('/api/templates', files={'file': ('template.pptx', template.read_bytes())}).json()['id']
        job = client.post('/api/jobs', json={'template_id': tid, 'content': {
            'title': 'Facts', 'sections': [{'id': 'one', 'title': 'Growth', 'bullets': ['Revenue 24 million'],
                'chart': {'categories': ['2025'], 'series': {'Revenue': [24]}, 'unit': 'million'}}]}}).json()
        result = run_job(app.state.store, job)
        assert result['timing']['generation_seconds'] >= 0
        assert result['timing']['preparation_seconds'] >= 0
        assert result['timing']['budget_seconds'] == 300
        assert result['timing']['budget_status'] == 'not_verified'  # no renderer, not a speed acceptance
        for variant in result['variants']:
            speech = client.get(f'/api/jobs/{job["id"]}/artifacts/{variant["name"]}/speech.md')
            assert speech.status_code == 200
            assert 'Revenue 24 million' in speech.text
            assert '2025' in speech.text
            parts = read_package(app.state.store.root/'jobs'/job['id']/variant['name']/'presentation.pptx')
            assert not validate_relationships(parts)
            slides = [p for kind, p in relationships(parts, 'ppt/presentation.xml').values() if kind == 'slide']
            notes = [p for kind, p in relationships(parts, slides[0]).values() if kind == 'notesSlide']
            assert len(notes) == 1
            text = ' '.join(parse_xml(parts[notes[0]]).xpath('//a:t/text()', namespaces=NS))
            assert 'Revenue 24 million' in text
            assert ' '.join(variant['slides'][0]['speaker_notes'].split()) in text
