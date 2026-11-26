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


@pytest.fixture
def policy_app(tmp_path):
    corpus = tmp_path / 'corpus'
    docs, texts = make_corpus(['ring_cache.py', 'roman_form.py'], str(corpus))
    docs[0].package = 'gplpkg'
    docs[0].license_spdx = 'GPL-3.0-only'
    docs[1].package = 'bsd_helper'
    docs[1].license_spdx = 'BSD-3-Clause'
    index = build_index(str(corpus), docs, texts)
    index.save(str(tmp_path / 'index.bin'))
    return Workbench(tmp_path)


def test_scan_returns_valid_sarif_2_1_0(app):
    data = scan(app)
    sarif = data['sarif']
    assert sarif['version'] == '2.1.0'
    assert sarif['$schema'] == 'https://json.schemastore.org/sarif-2.1.0.json'
    assert len(sarif['runs']) == 1
    run = sarif['runs'][0]
    assert run['tool']['driver']['name'] == 'CodeGuard'
    assert len(run['results']) >= 1
    res = run['results'][0]
    assert res['ruleId'] in {'CG001', 'CG002', 'CG003', 'CG004'}
    assert res['locations'][0]['physicalLocation']['region']['startLine'] >= 1
    assert res['relatedLocations']
    assert data['policy_audit'] is None


def test_scan_with_policy_waives_and_denies(policy_app):
    waived = policy_app.scan({
        'code': read_negative('ring_cache.py'),
        'name': 'gpl_copy.py',
        'license': 'MIT',
        'usage': 'distribution',
        'policy': {
            'allow_packages': ['gplpkg'],
            'deny_licenses': [],
            'reason': '法务豁免归档',
        },
    })
    assert not waived['blocking']
    assert waived['findings'][0]['risk'] == 'S1'
    assert waived['findings'][0]['policy_action'] == 'waived'
    assert waived['findings'][0]['policy_reason'] == '法务豁免归档'
    assert waived['policy_audit']['waived_count'] == 1
    assert waived['policy_audit']['denied_count'] == 0
    assert waived['receipt']['policy_audit']['waived_count'] == 1
    assert waived['sarif']['runs'][0]['properties']['policyAudit']['waived_count'] == 1
    assert waived['sarif']['runs'][0]['results'][0]['properties']['policyAction'] == 'waived'
    assert '法务豁免归档' in waived['html']

    baseline_bsd = policy_app.scan({
        'code': read_negative('roman_form.py'),
        'name': 'bsd_copy.py',
        'license': 'MIT',
        'usage': 'distribution',
    })
    assert not baseline_bsd['blocking']
    assert baseline_bsd['findings'][0]['risk'] == 'S1'

    denied = policy_app.scan({
        'code': read_negative('roman_form.py'),
        'name': 'bsd_copy.py',
        'license': 'MIT',
        'usage': 'distribution',
        'policy': {
            'allow_packages': [],
            'deny_licenses': ['BSD-3-Clause'],
            'reason': '',
        },
    })
    assert denied['blocking']
    assert denied['findings'][0]['risk'] == 'S4'
    assert denied['findings'][0]['policy_action'] == 'denied'
    assert denied['policy_audit']['denied_count'] == 1
    assert denied['sarif']['runs'][0]['results'][0]['level'] == 'error'
    assert denied['sarif']['runs'][0]['results'][0]['properties']['policyAction'] == 'denied'


def test_scan_tree_with_policy_waives_and_denies(policy_app):
    clean = 'def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n'
    data = policy_app.scan_tree({
        'files': [
            {'path': 'src/gpl.py', 'content': read_negative('ring_cache.py')},
            {'path': 'src/bsd.py', 'content': read_negative('roman_form.py')},
            {'path': 'src/clean.py', 'content': clean},
        ],
        'license': 'MIT',
        'usage': 'distribution',
        'policy': {
            'allow_packages': ['gplpkg'],
            'deny_licenses': ['BSD-3-Clause'],
            'reason': '整夹合规策略测试',
        },
    })
    assert data['policy_audit']['waived_count'] == 1
    assert data['policy_audit']['denied_count'] == 1
    assert data['summary']['blocked'] == 1
    assert data['summary']['overall_risk'] == 'S4'
    by_path = {r['path']: r for r in data['results']}
    assert by_path['src/gpl.py']['risk'] == 'S1'
    assert not by_path['src/gpl.py']['blocking']
    assert by_path['src/gpl.py']['findings'][0]['policy_action'] == 'waived'
    assert by_path['src/gpl.py']['findings'][0]['policy_reason'] == '整夹合规策略测试'
    assert by_path['src/bsd.py']['risk'] == 'S4'
    assert by_path['src/bsd.py']['blocking']
    assert by_path['src/bsd.py']['findings'][0]['policy_action'] == 'denied'


def test_api_http_scan_sarif_policy_and_static_ui(policy_app):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(policy_app))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = 'http://127.0.0.1:%d' % server.server_port
    try:
        html = urllib.request.urlopen(url + '/').read().decode('utf-8')
        for expected in ('id="rcPkgs"', 'id="rcDocs"', 'id="rcChunks"', 'data-export="sarif"',
                         'id="policyBox"', 'id="policyAllow"', 'id="policyDeny"', 'id="policyReason"'):
            assert expected in html
        assert 'data-demo=' not in html
        assert '演示样本' not in html

        health = json.load(urllib.request.urlopen(url + '/api/health'))
        headers = {'Content-Type': 'application/json', 'X-CodeGuard-Token': health['token']}

        scan_req = urllib.request.Request(
            url + '/api/scan',
            data=json.dumps({
                'code': read_negative('ring_cache.py'),
                'name': 'demo.py',
                'license': 'MIT',
                'usage': 'distribution',
                'policy': {'allow_packages': ['gplpkg'], 'reason': 'HTTP 豁免测试'},
            }).encode('utf-8'),
            headers=headers,
        )
        scan_resp = json.load(urllib.request.urlopen(scan_req))
        assert scan_resp['sarif']['version'] == '2.1.0'
        assert not scan_resp['blocking']
        assert scan_resp['policy_audit']['waived_count'] == 1

        tree_req = urllib.request.Request(
            url + '/api/scan_tree',
            data=json.dumps({
                'files': [{'path': 'pkg/mod.py', 'content': read_negative('roman_form.py')}],
                'license': 'MIT',
                'usage': 'distribution',
                'policy': {'deny_licenses': ['BSD-3-Clause']},
            }).encode('utf-8'),
            headers=headers,
        )
        tree_resp = json.load(urllib.request.urlopen(tree_req))
        assert tree_resp['summary']['blocked'] == 1
        assert tree_resp['policy_audit']['denied_count'] == 1

        bad_req = urllib.request.Request(
            url + '/api/scan',
            data=json.dumps({'code': 'x = 1\n', 'policy': {'allow_packages': [123]}}).encode('utf-8'),
            headers=headers,
        )
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(bad_req)
        assert err.value.code == 400
    finally:
        server.shutdown()
        server.server_close()


def test_digest_includes_corroborated_and_scan_tree_reuses_scanner(app, monkeypatch):
    import codeguard.web as web_mod
    init_calls = []
    real_scanner = web_mod.Scanner

    def spy_scanner(*args, **kwargs):
        init_calls.append(1)
        return real_scanner(*args, **kwargs)

    monkeypatch.setattr(web_mod, 'Scanner', spy_scanner)
    app.scan_tree({'files': [
        {'path': 'a.py', 'content': read_negative('ring_cache.py')},
        {'path': 'b.py', 'content': read_negative('word_tally.py')},
        {'path': 'c.py', 'content': 'def f():\n    return 1\n'},
    ], 'license': 'MIT', 'usage': 'distribution'})
    assert len(init_calls) == 1
    assert app.last_digest['findings'][0]['corroborated'] is True
    assert app.last_digest['findings'][0]['matched_spans'] >= 1

    app.scan({'code': read_negative('ring_cache.py'), 'name': 'x.py',
              'license': 'MIT', 'usage': 'distribution'})
    assert app.last_digest['findings'][0]['corroborated'] is True
    assert app.last_digest['findings'][0]['matched_spans'] >= 1


def test_static_app_js_skips_vendor_and_minified_paths():
    app_js = (Path(__file__).resolve().parents[1] / 'src' / 'codeguard' / 'static' / 'app.js').read_text(encoding='utf-8')
    for token in ('.git', 'node_modules', 'dist', 'build', '__pycache__', '.min.js'):
        assert token in app_js


def test_static_markdown_renderer_is_safe_and_styled():
    static_dir = Path(__file__).resolve().parents[1] / 'src' / 'codeguard' / 'static'
    app_js = (static_dir / 'app.js').read_text(encoding='utf-8')
    style_css = (static_dir / 'style.css').read_text(encoding='utf-8')
    assert 'function renderMarkdown(' in app_js
    assert 'innerHTML' not in app_js
    assert 'ai-text md-body' in app_js
    assert 'ai-inline md-body' in app_js
    assert 'renderMarkdown(finding.explanation)' in app_js
    assert '.md-body' in style_css
    assert '.md-body .md-h' in style_css
