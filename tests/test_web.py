"""Offline API, evidence serialization and relocatable distribution checks."""
import json
from pathlib import Path
import shutil
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from helpers import build_index, make_corpus, read_negative
from codeguard.web import Workbench, handler_for
from codeguard.cli import load_index
from codeguard.report import to_cyclonedx


@pytest.fixture
def app(tmp_path):
    corpus = tmp_path / 'corpus'
    docs, texts = make_corpus(['ring_cache.py'], str(corpus))
    docs[0].license_spdx = 'GPL-3.0-only'
    index = build_index(str(corpus), docs, texts)
    index.save(str(tmp_path / 'index.bin'))
    relocated = tmp_path / 'moved'
    relocated.mkdir()
    shutil.copytree(corpus, relocated / 'corpus')
    shutil.copyfile(tmp_path / 'index.bin', relocated / 'index.bin')
    # Prove that the serialized original path is unusable.
    shutil.rmtree(corpus)
    return Workbench(relocated)


def scan(app):
    return app.scan({'code': read_negative('ring_cache.py'), 'name': '<script>.py',
                     'license': 'MIT', 'usage': 'distribution'})


def test_relocated_scan_serializes_evidence_and_blocks(app):
    data = scan(app)
    assert data['blocking']
    assert data['scan']['findings'][0]['evidence'][0]['pair']['exact']
    assert data['findings'][0]['snippets'][0]['source']
    assert 'corpus_root' not in data['receipt']['metadata']
    assert len(data['receipt']['subject']['sha256']) == 64
    assert not data['receipt']['metadata']['ai_usage']['external_calls']
    assert '&lt;script&gt;' in data['html']
    json.dumps(data)
    assert load_index(str(app.root)).corpus_health() == (1, 1)


def test_missing_corpus_cannot_pass(app):
    shutil.rmtree(app.root / 'corpus')
    assert not app.health()['ready']
    with pytest.raises(ValueError, match='缺失'):
        scan(app)


def test_changed_corpus_cannot_silently_pass(app):
    path = next((app.root / 'corpus').rglob('*.py'))
    path.write_text('# replaced source\n', encoding='utf-8')
    assert app.health()['corpus']['mismatched'] == 1
    assert not app.health()['ready']
    with pytest.raises(ValueError, match='哈希'):
        scan(app)


@pytest.mark.parametrize('data', [ {'code':''}, {'code':1}, {'code':'x'*200001},
    {'code':'x', 'usage':'saas'}, {'code':'x','license':1} ])
def test_invalid_scan_rejected(app, data):
    with pytest.raises(ValueError):
        app.scan(data)


def test_scan_tree_aggregates_risks_and_blocks(app):
    clean = 'def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n'
    data = app.scan_tree({'files': [
        {'path': 'src/evil.py', 'content': read_negative('ring_cache.py')},
        {'path': 'src/util/clean.py', 'content': clean},
        {'path': 'docs/readme.md', 'content': '# docs\n'},  # 空泛内容不会命中，但 md 不该报错
    ], 'license': 'MIT', 'usage': 'distribution'})
    s = data['summary']
    assert s['files'] == 3
    assert s['blocked'] == 1
    assert s['overall_risk'] == 'S4' and s['overall_label']
    assert s['risk_counts']['S4'] == 1
    top = data['results'][0]
    assert top['path'] == 'src/evil.py' and top['blocking']
    assert top['findings'] and top['findings'][0]['explanation']
    clean_row = next(r for r in data['results'] if r['path'] == 'src/util/clean.py')
    assert clean_row['risk'] == 'S0' and not clean_row['blocking']


def test_scan_tree_rejects_escape_caps_and_empty(app):
    with pytest.raises(ValueError, match='越出'):
        app.scan_tree({'files': [{'path': '../evil.py', 'content': 'x = 1\n'}]})
    with pytest.raises(ValueError, match='最多'):
        app.scan_tree({'files': [{'path': f'f{i}.py', 'content': 'x = 1\n'} for i in range(401)]})
    with pytest.raises(ValueError, match='8 MB'):
        app.scan_tree({'files': [{'path': f'f{i}.py', 'content': 'x' * 200_000} for i in range(41)]})
    with pytest.raises(ValueError, match='没有可分析'):
        app.scan_tree({'files': [{'path': 'huge.py', 'content': 'x' * 300_000}]})
    with pytest.raises(ValueError, match='请先导入'):
        app.scan_tree({'files': []})


def test_sbom_refs_and_occurrence_locations(app):
    from codeguard.adjudicate import Scanner
    result = Scanner(app.index, usage='distribution').scan_text(read_negative('ring_cache.py'), target='review.py', target_license='MIT')
    result.findings.append(result.findings[0])
    bom = to_cyclonedx(result, app.index)
    import uuid
    uuid.UUID(bom['serialNumber'].removeprefix('urn:uuid:'))
    assert len(bom['components']) == 1
    assert bom['metadata']['component']['bom-ref'] == bom['dependencies'][0]['ref']
    component = bom['components'][0]
    assert component['evidence']['identity'][0]['field'] == 'purl'
    assert all(o['location'] == 'review.py' and 'endLine' not in o for o in component['evidence']['occurrences'])


def test_api_host_token_and_body_contract(app):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(app))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = 'http://127.0.0.1:%d' % server.server_port
    try:
        health = json.load(urllib.request.urlopen(url+'/api/health'))
        assert health['ready']
        payload = json.dumps({'source':'GPL-3.0-only','target':'MIT','usage':'distribution'}).encode()
        req = urllib.request.Request(url+'/api/licenses', data=payload)
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(req)
        assert error.value.code == 403
        req.add_header('X-CodeGuard-Token', health['token'])
        assert json.load(urllib.request.urlopen(req))['status'] == 'incompatible'
        bad_host = urllib.request.Request(url+'/api/health', headers={'Host':'attacker.example'})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(bad_host)
        assert error.value.code == 403
        invalid = urllib.request.Request(url+'/api/scan', data=b'[]', headers={'X-CodeGuard-Token':health['token']})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(invalid)
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
