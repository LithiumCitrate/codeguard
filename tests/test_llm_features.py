"""LLM interpretation layer: settings hygiene, model listing, grounded tasks.

All network-facing tests run against a loopback stub that speaks the
OpenAI-compatible protocol, so the suite stays offline and deterministic.
"""
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from helpers import build_index, make_corpus, read_negative
from codeguard.llm import (OpenAICompatProvider, _compact_digest,
                           clear_llm_settings, extract_license_markers,
                           list_models, load_llm_settings, mask_key,
                           save_llm_settings)
from codeguard.web import Workbench

KEY = 'sk-test-key-1234567890'


class StubHandler(BaseHTTPRequestHandler):
    """Records the last chat request so prompts can be asserted offline."""
    last_chat = None

    def log_message(self, *args):
        pass

    def _reply(self, status, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/v1/models':
            auth = self.headers.get('Authorization', '')
            if auth != 'Bearer ' + KEY:
                return self._reply(401, {'error': 'bad key'})
            return self._reply(200, {'data': [{'id': 'model-b'}, {'id': 'model-a'}, {'id': 'model-a'}]})
        self._reply(404, {})

    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        StubHandler.last_chat = json.loads(self.rfile.read(length))
        if StubHandler.last_chat.get('model') == 'boom':
            return self._reply(500, {'error': 'upstream'})
        return self._reply(200, {'choices': [{'message': {'content': 'STUB-PROSE'}}]})


@pytest.fixture
def stub():
    server = ThreadingHTTPServer(('127.0.0.1', 0), StubHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield 'http://127.0.0.1:%d/v1' % server.server_port
    server.shutdown()
    server.server_close()


@pytest.fixture
def app(tmp_path):
    corpus = tmp_path / 'corpus'
    docs, texts = make_corpus(['ring_cache.py'], str(corpus))
    docs[0].license_spdx = 'GPL-3.0-only'
    index = build_index(str(corpus), docs, texts)
    index.save(str(tmp_path / 'index.bin'))
    return Workbench(tmp_path)


# ------------------------------------------------------------- settings I/O

def test_settings_roundtrip_and_mask(tmp_path):
    assert load_llm_settings(tmp_path) is None
    saved = save_llm_settings(tmp_path, 'https://api.example.com/v1/', KEY, 'model-a')
    assert saved['base_url'] == 'https://api.example.com/v1'
    loaded = load_llm_settings(tmp_path)
    assert loaded['api_key'] == KEY and loaded['model'] == 'model-a'
    assert KEY not in mask_key(KEY)
    assert clear_llm_settings(tmp_path) and load_llm_settings(tmp_path) is None


@pytest.mark.parametrize('base,key,model', [
    ('ftp://x', KEY, 'm'), ('', KEY, 'm'), ('http://', KEY, 'm'),
    ('https://api.example.com', '', 'm'), ('https://api.example.com', KEY, ''),
    ('https://api.example.com', KEY, ' ' * 300),
])
def test_settings_validation(tmp_path, base, key, model):
    with pytest.raises(ValueError):
        save_llm_settings(tmp_path, base, key, model)


def test_corrupt_settings_ignored(tmp_path):
    (tmp_path / 'llm_config.json').write_text('{not json', encoding='utf-8')
    assert load_llm_settings(tmp_path) is None
    (tmp_path / 'llm_config.json').write_text('[]', encoding='utf-8')
    assert load_llm_settings(tmp_path) is None


# ---------------------------------------------------------------- model list

def test_list_models_dedupes_and_sorts(stub):
    assert list_models(stub, KEY) == ['model-a', 'model-b']


def test_list_models_bad_key_reports_auth(stub):
    with pytest.raises(ValueError, match='401'):
        list_models(stub, 'sk-wrong')
    with pytest.raises(ValueError, match='Base URL'):
        list_models('notaurl', KEY)
    with pytest.raises(ValueError, match='API Key'):
        list_models(stub, '  ')


# ------------------------------------------------------------ offline markers

def test_markers_deterministic_extraction():
    code = ('# SPDX-License-Identifier: Apache-2.0\n'
            '# Copyright 2024 Somebody\n'
            '# adapted from https://github.com/example/project/blob/main/x.py\n'
            'import os\n')
    markers = extract_license_markers(code)
    again = extract_license_markers(code)
    assert markers == again
    assert markers['spdx'] == ['Apache-2.0']
    assert markers['copyright_lines'] and 'Copyright 2024 Somebody' in markers['copyright_lines'][0]
    assert markers['vendored_hints'] and 'adapted from' in markers['vendored_hints'][0]
    assert markers['source_urls']
    empty = extract_license_markers('x = 1\n')
    assert '未在注释或声明中发现显式许可证标记' in empty['summary']


def test_markers_ignore_code_calls_and_bare_c_parens():
    js_code = (
        "class PeerRoom {\n"
        "  init() {\n"
        "    this.peer.on('connection', c => this.accept(c));\n"
        "  }\n"
        "  accept(c) {\n"
        "    return cardText(c);\n"
        "  }\n"
        "}\n"
        "def helper():\n"
        '    """Test helper based on standard fixture."""\n'
        "    return self._parse_config_item(c)\n"
    )
    markers = extract_license_markers(js_code)
    assert markers['copyright_lines'] == []
    assert markers['vendored_hints'] == []

    bare_c = "# (c) Alice without year or notice\n"
    assert extract_license_markers(bare_c)['copyright_lines'] == []

    real_headers = (
        "/*\n * Copyright (c) 2017 STMicroelectronics.\n * © 2025 Acme Corp\n"
        " * adapted from https://github.com/org/repo/blob/main/a.c\n */\n"
        "int accept(int c) { return c; }\n"
    )
    m2 = extract_license_markers(real_headers)
    assert len(m2['copyright_lines']) == 2
    assert len(m2['vendored_hints']) == 1


def test_compact_digest_keeps_valid_json_and_counts_omitted(stub):
    digest = {
        'target': '文件夹审查：30 个文件',
        'target_license': 'MIT',
        'usage': 'distribution',
        'blocking': False,
        'findings_omitted': 2,
        'findings': [
            {
                'file': 'mod_%02d.py' % i,
                'package': 'glances',
                'version': '4.5.7',
                'path': 'glances/main.py',
                'license_spdx': 'LGPL-3.0-only',
                'risk': 'S2',
                'confidence': 0.55,
                'coverage': 0.04,
                'matched_spans': 1,
                'max_verbatim_run': 5,
                'corroborated': False,
                'obligations': ['x' * 120],
                'conflicts': [],
            }
            for i in range(40)
        ],
    }
    snapshot = json.dumps(digest, sort_keys=True)
    compacted = _compact_digest(digest, max_chars=1200)
    assert len(compacted) <= 1200
    parsed = json.loads(compacted)
    assert parsed['findings_omitted'] == 2 + (40 - len(parsed['findings']))
    assert len(parsed['findings']) < 40
    assert json.dumps(digest, sort_keys=True) == snapshot

    provider = OpenAICompatProvider(stub, KEY, 'model-a')
    provider.summarize_scan(digest)
    prompt_sum = StubHandler.last_chat['messages'][0]['content']
    assert 'corroborated' in prompt_sum and '严禁声称' in prompt_sum
    provider.answer_question('需要修改吗？', digest)
    prompt_qa = StubHandler.last_chat['messages'][0]['content']
    assert 'corroborated' in prompt_qa


# ------------------------------------------------------------- provider tasks

def test_provider_chat_and_prompts(stub):
    provider = OpenAICompatProvider(stub, KEY, 'model-a')
    assert provider.interpret_file('x=1', 'a.py', {}) == 'STUB-PROSE'
    assert '源代码' in StubHandler.last_chat['messages'][0]['content']
    assert provider.summarize_scan({'findings': []}) == 'STUB-PROSE'
    assert '执行摘要' in StubHandler.last_chat['messages'][0]['content']
    assert provider.answer_question('为何阻断？', {'findings': []}) == 'STUB-PROSE'
    assert '为何阻断？' in StubHandler.last_chat['messages'][0]['content']
    assert provider.explain_licence({'status': 'incompatible'}) == 'STUB-PROSE'
    assert '规则引擎' in StubHandler.last_chat['messages'][0]['content']
    assert StubHandler.last_chat['model'] == 'model-a'
    assert StubHandler.last_chat['temperature'] == 0.2


def test_provider_describe_falls_back_offline_on_error(stub):
    provider = OpenAICompatProvider(stub, KEY, 'boom')
    from codeguard.llm import OfflineTemplateProvider
    class FakeFinding:
        class verdict:
            status, target_spdx, usage = 'incompatible', 'MIT', 'distribution'
            conflicts, notes, obligations = ['c1'], [], ['o1']
        target, spans, package, version, path = 't.py', [], 'p', '1', 'f.py'
        matched_query_lines, max_verbatim_run, license_spdx, risk = (1, 2), 3, 'GPL-3.0-only', 'S4'
        key = 'k'
        def as_dict(self):
            return {}
    text = provider.describe(FakeFinding())
    assert text.startswith(OfflineTemplateProvider().describe(FakeFinding()))
    assert '回退到离线模板' in text


# -------------------------------------------------------------- workbench API

def configure(app, stub):
    app.llm_save({'base_url': stub, 'api_key': KEY, 'model': 'model-a'})


def test_llm_status_never_leaks_key(app, stub):
    status = app.llm_status()
    assert status == {'configured': False, 'base_url': '', 'model': '', 'key_masked': '',
                      'tavily_configured': False, 'tavily_key_masked': ''}
    configure(app, stub)
    status = app.llm_status()
    assert status['configured'] and status['model'] == 'model-a'
    assert KEY not in json.dumps(status)
    assert 'llm' in app.health() and KEY not in json.dumps(app.health())
    assert app.llm_save({'base_url': stub, 'api_key': '', 'model': 'model-b'})['model'] == 'model-b'
    assert load_llm_settings(app.root)['api_key'] == KEY  # 留空沿用旧密钥
    assert app.llm_clear() == {'cleared': True} and not app.llm_status()['configured']


def test_interpret_offline_and_with_llm(app, stub):
    code = '# SPDX-License-Identifier: MIT\ndef f():\n    return 1\n'
    data = app.interpret({'code': code, 'name': 'f.py'})
    assert data['llm'] is None and data['markers']['spdx'] == ['MIT']
    configure(app, stub)
    data = app.interpret({'code': code, 'name': 'f.py'})
    assert data['llm']['text'] == 'STUB-PROSE' and data['llm']['model'] == 'model-a'
    with pytest.raises(ValueError, match='请输入'):
        app.interpret({'code': '   '})
    app.llm_save({'base_url': stub, 'api_key': KEY, 'model': 'boom'})
    data = app.interpret({'code': code, 'name': 'f.py'})
    assert data['llm']['error'] and data['markers']['spdx'] == ['MIT']


def scan(app, **extra):
    payload = {'code': read_negative('ring_cache.py'), 'name': 'review.py',
               'license': 'MIT', 'usage': 'distribution'}
    payload.update(extra)
    return app.scan(payload)


def test_assist_summary_and_ask_flow(app, stub):
    with pytest.raises(ValueError, match='先完成一次来源审查'):
        app.assist({'action': 'summary'})
    plain = scan(app)
    assert plain['llm_assisted'] is False
    assert plain['receipt']['metadata']['ai_usage']['external_calls'] is False
    offline = app.assist({'action': 'summary'})
    assert offline['offline'] and '片段命中' in offline['text']
    with pytest.raises(ValueError, match='配置大模型'):
        app.assist({'action': 'ask', 'question': '哪个命中风险最高？'})
    # 文件夹审查共用同一入口：digest 缺失会让 assist 永远报"先完成一次来源审查"
    tree = app.scan_tree({'files': [
        {'path': 'pkg/copied.py', 'content': read_negative('ring_cache.py')},
        {'path': 'pkg/clean.py', 'content': read_negative('word_tally.py')}],
        'license': 'MIT', 'usage': 'distribution'})
    assert tree['summary']['blocked'] == 1
    tree_offline = app.assist({'action': 'summary'})
    assert tree_offline['offline'] and '文件夹审查：2 个文件' in tree_offline['text']
    assert app.last_digest['findings'][0]['file'] == 'pkg/copied.py'
    assert app.last_findings[0].package == app.index.docs[0].package
    configure(app, stub)
    summary = app.assist({'action': 'summary'})
    assert summary == {'offline': False, 'model': 'model-a', 'text': 'STUB-PROSE'}
    assert 'pkg/copied.py' in json.dumps(StubHandler.last_chat, ensure_ascii=False)
    scan(app)
    assert app.assist({'action': 'summary'})['text'] == 'STUB-PROSE'
    answer = app.assist({'action': 'ask', 'question': '为何阻断？'})
    assert answer['text'] == 'STUB-PROSE'
    with pytest.raises(ValueError, match='2–1000'):
        app.assist({'action': 'ask', 'question': 'x'})
    with pytest.raises(ValueError, match='无效'):
        app.assist({'action': 'rebase'})


def test_scan_with_assist_records_honest_ai_usage(app, stub):
    scan(app)  # establish digest
    configure(app, stub)
    data = scan(app, assist=True)
    usage = data['receipt']['metadata']['ai_usage']
    assert data['llm_assisted'] is True and data['llm_model'] == 'model-a'
    assert usage['provider'] == 'openai-compatible' and usage['external_calls'] is True
    assert usage['model'] == 'model-a'
    assert data['findings'][0]['explanation'] == 'STUB-PROSE'
    assert KEY not in json.dumps(data['receipt'])
    again = scan(app)  # 不勾选 assist 时回到离线模板
    assert again['llm_assisted'] is False
    assert again['receipt']['metadata']['ai_usage']['external_calls'] is False


def test_license_explain_with_and_without_llm(app, stub):
    data = app.license_explain({'source': 'GPL-3.0-only', 'target': 'MIT', 'usage': 'distribution'})
    assert data['llm'] is None and data['analysis']['status'] == 'incompatible'
    configure(app, stub)
    data = app.license_explain({'source': 'GPL-3.0-only', 'target': 'MIT', 'usage': 'distribution'})
    assert data['llm']['text'] == 'STUB-PROSE'


def test_new_endpoints_token_gated(app, stub):
    from codeguard.web import handler_for
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(app))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:%d' % server.server_port
    try:
        health = json.load(urllib.request.urlopen(url + '/api/health'))
        token = health['token']
        payload = json.dumps({'base_url': stub, 'api_key': KEY, 'model': 'model-a'}).encode()
        req = urllib.request.Request(url + '/api/llm/config', data=payload)
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(req)
        assert error.value.code == 403
        req.add_header('X-CodeGuard-Token', token)
        saved = json.load(urllib.request.urlopen(req))
        assert saved['model'] == 'model-a' and KEY not in json.dumps(saved)
        body = json.dumps({'base_url': stub, 'api_key': KEY}).encode()
        models = json.load(urllib.request.urlopen(urllib.request.Request(
            url + '/api/llm/models', data=body, headers={'X-CodeGuard-Token': token})))
        assert models == {'models': ['model-a', 'model-b']}
        bad = urllib.request.Request(url + '/api/llm/models',
                                     data=json.dumps({'base_url': stub, 'api_key': 'wrong'}).encode(),
                                     headers={'X-CodeGuard-Token': token})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(bad)
        assert error.value.code == 400  # 上游 401 被转成可读的 ValueError
        missing = urllib.request.Request(url + '/api/nope', data=b'{}',
                                         headers={'X-CodeGuard-Token': token})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(missing)
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
