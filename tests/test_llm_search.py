"""Optional web-search layer: Tavily client, tool loop, fallbacks, verdict safety.

All network-facing tests run against loopback stubs (OpenAI-compatible chat +
Tavily search), so the suite stays offline and deterministic. The adjudication
path must be byte-identical with and without search configured.
"""
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from helpers import build_index, make_corpus, read_negative
import codeguard.llm as llm
from codeguard.llm import (OpenAICompatProvider, load_llm_settings,
                           save_llm_settings, tavily_search)
from codeguard.web import Workbench

KEY = 'sk-test-key-1234567890'
TKEY = 'tvly-test-key-1234567890'


class SearchStubHandler(BaseHTTPRequestHandler):
    """Chat stub with switchable tool behaviour plus a Tavily endpoint."""
    chat_mode = 'tools'      # tools | ignore-tools | reject-tools | loop | boom
    tavily_fail = False
    chat_requests = []
    tavily_requests = []

    def log_message(self, *args):
        pass

    def _reply(self, status, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        payload = json.loads(self.rfile.read(length))
        if self.path == '/search':
            SearchStubHandler.tavily_requests.append(
                {'payload': payload, 'auth': self.headers.get('Authorization', '')})
            if SearchStubHandler.tavily_fail or self.headers.get('Authorization') != 'Bearer ' + TKEY:
                return self._reply(401, {'error': 'bad key'})
            return self._reply(200, {'results': [
                {'title': 'Django', 'url': 'https://www.djangoproject.com/', 'content': 'BSD licensed.'},
                {'title': 'License', 'url': 'https://github.com/django/django/blob/main/LICENSE', 'content': 'BSD-3-Clause text.'},
                {'title': 'bad', 'url': 'javascript:alert(1)', 'content': 'must be dropped'},
            ]})
        SearchStubHandler.chat_requests.append(payload)
        mode = SearchStubHandler.chat_mode
        if mode == 'boom':
            return self._reply(500, {'error': 'upstream'})
        if mode == 'reject-tools' and 'tools' in payload:
            return self._reply(400, {'error': 'tools not supported'})
        has_tool_result = any(m.get('role') == 'tool' for m in payload['messages'])
        if mode in ('tools', 'loop') and 'tools' in payload and (mode == 'loop' or not has_tool_result):
            return self._reply(200, {'choices': [{'message': {
                'content': '', 'tool_calls': [{'id': 'call_1', 'type': 'function',
                    'function': {'name': 'web_search',
                                 'arguments': json.dumps({'query': 'django license'})}}]}}]})
        return self._reply(200, {'choices': [{'message': {'content': 'STUB-SEARCH-PROSE'}}]})


@pytest.fixture
def stub(monkeypatch):
    SearchStubHandler.chat_mode = 'tools'
    SearchStubHandler.tavily_fail = False
    SearchStubHandler.chat_requests = []
    SearchStubHandler.tavily_requests = []
    server = ThreadingHTTPServer(('127.0.0.1', 0), SearchStubHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:%d' % server.server_port
    monkeypatch.setattr(llm, 'TAVILY_ENDPOINT', base + '/search')
    yield base + '/v1'
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


def provider(stub, tavily=TKEY):
    return OpenAICompatProvider(stub, KEY, 'model-a', tavily_api_key=tavily)


# ------------------------------------------------------------- settings I/O

def test_tavily_settings_roundtrip_and_legacy(tmp_path):
    save_llm_settings(tmp_path, 'https://api.example.com/v1', KEY, 'model-a')
    assert load_llm_settings(tmp_path)['tavily_api_key'] == ''  # 旧配置兼容
    save_llm_settings(tmp_path, 'https://api.example.com/v1', KEY, 'model-a', tavily_api_key=TKEY)
    loaded = load_llm_settings(tmp_path)
    assert loaded['tavily_api_key'] == TKEY
    with pytest.raises(ValueError):
        save_llm_settings(tmp_path, 'https://api.example.com/v1', KEY, 'model-a', tavily_api_key='x' * 600)


def test_workbench_save_keeps_tavily_and_never_leaks(app, stub):
    app.llm_save({'base_url': stub, 'api_key': KEY, 'model': 'model-a', 'tavily_api_key': TKEY})
    status = app.llm_status()
    assert status['tavily_configured'] and TKEY not in json.dumps(status)
    app.llm_save({'base_url': stub, 'api_key': '', 'model': 'model-b'})  # 留空沿用两把密钥
    assert load_llm_settings(app.root)['tavily_api_key'] == TKEY
    assert load_llm_settings(app.root)['api_key'] == KEY
    health = app.health()
    assert health['llm']['tavily_configured'] and TKEY not in json.dumps(health)
    app.llm_clear()
    assert not app.llm_status()['tavily_configured']


# ------------------------------------------------------------- tavily client

def test_tavily_search_parses_and_filters(stub):
    results = tavily_search('django license', TKEY)
    assert [r['url'] for r in results] == ['https://www.djangoproject.com/',
                                           'https://github.com/django/django/blob/main/LICENSE']
    request = SearchStubHandler.tavily_requests[-1]
    assert request['auth'] == 'Bearer ' + TKEY
    assert request['payload']['query'] == 'django license'
    with pytest.raises(ValueError, match='401'):
        tavily_search('django license', 'tvly-wrong')
    with pytest.raises(ValueError, match='搜索词'):
        tavily_search('   ', TKEY)
    with pytest.raises(ValueError, match='Tavily API Key'):
        tavily_search('q', '')


# ---------------------------------------------------------------- tool loop

def test_tool_loop_executes_search_and_returns_trace(stub):
    text, searches = provider(stub).chat_with_search('问题', ['seed query'])
    assert text == 'STUB-SEARCH-PROSE'
    assert searches == [{'query': 'django license', 'results': [
        {'title': 'Django', 'url': 'https://www.djangoproject.com/'},
        {'title': 'License', 'url': 'https://github.com/django/django/blob/main/LICENSE'}]}]
    assert len(SearchStubHandler.chat_requests) == 2
    followup = SearchStubHandler.chat_requests[1]
    tool_messages = [m for m in followup['messages'] if m['role'] == 'tool']
    assert len(tool_messages) == 1 and tool_messages[0]['tool_call_id'] == 'call_1'
    assert 'BSD-3-Clause text.' in tool_messages[0]['content']  # 正文进 LLM 上下文
    assert 'content' not in json.dumps(searches)               # 轨迹只带标题/URL


def test_tool_loop_requires_tavily_key(stub):
    with pytest.raises(ValueError, match='Tavily'):
        provider(stub, tavily='').chat_with_search('问题')


def test_reject_tools_falls_back_to_seed_pipeline(stub):
    SearchStubHandler.chat_mode = 'reject-tools'
    text, searches = provider(stub).chat_with_search('问题', ['django license'])
    assert text == 'STUB-SEARCH-PROSE'
    assert searches[0]['query'] == 'django license'
    assert '公开参考材料' in SearchStubHandler.chat_requests[-1]['messages'][0]['content']
    assert 'tools' not in SearchStubHandler.chat_requests[-1]


def test_model_ignoring_tools_falls_back_to_seeds(stub):
    SearchStubHandler.chat_mode = 'ignore-tools'
    text, searches = provider(stub).chat_with_search('问题', ['django license'])
    assert text == 'STUB-SEARCH-PROSE' and searches[0]['query'] == 'django license'


def test_search_failure_degrades_to_prose(stub):
    SearchStubHandler.tavily_fail = True
    text, searches = provider(stub).chat_with_search('问题')
    assert text == 'STUB-SEARCH-PROSE'
    assert searches[0]['error'] and searches[0]['results'] == []


def test_round_cap_forces_final_answer(stub):
    SearchStubHandler.chat_mode = 'loop'
    text, searches = provider(stub).chat_with_search('问题', max_rounds=2)
    assert text == 'STUB-SEARCH-PROSE'
    assert len(searches) == 2                       # 每轮一次检索
    assert 'tools' not in SearchStubHandler.chat_requests[-1]  # 收尾不带工具


# ------------------------------------------------------- workbench integration

def configure(app, stub, tavily=TKEY):
    app.llm_save({'base_url': stub, 'api_key': KEY, 'model': 'model-a', 'tavily_api_key': tavily})


def scan(app, **extra):
    payload = {'code': read_negative('ring_cache.py'), 'name': 'review.py',
               'license': 'MIT', 'usage': 'distribution'}
    payload.update(extra)
    return app.scan(payload)


def test_deep_dive_flow_and_verdict_invariance(app, stub):
    baseline = scan(app)
    configure(app, stub)
    assisted = scan(app, assist=True)
    assert assisted['blocking'] == baseline['blocking']
    assert [f['risk'] for f in assisted['findings']] == [f['risk'] for f in baseline['findings']]
    deep = app.assist({'action': 'deep', 'index': 0})
    assert deep['text'] == 'STUB-SEARCH-PROSE' and deep['searches']
    assert deep['subject'] == baseline['findings'][0]['package'] + '@' + \
        baseline['findings'][0]['version'] + ':' + baseline['findings'][0]['path']
    assert deep['risk'] == baseline['findings'][0]['risk']
    assert TKEY not in json.dumps(deep) and KEY not in json.dumps(deep)


def test_deep_dive_validation(app, stub):
    with pytest.raises(ValueError, match='先完成一次来源审查'):
        app.assist({'action': 'deep', 'index': 0})
    scan(app)
    with pytest.raises(ValueError, match='配置大模型'):
        app.assist({'action': 'deep', 'index': 0})
    configure(app, stub, tavily='')
    with pytest.raises(ValueError, match='Tavily'):
        app.assist({'action': 'deep', 'index': 0})
    configure(app, stub)
    with pytest.raises(ValueError, match='无效'):
        app.assist({'action': 'deep', 'index': 99})
    with pytest.raises(ValueError, match='无效'):
        app.assist({'action': 'deep', 'index': '0'})


def test_ask_with_search_and_interpret_search(app, stub):
    scan(app)
    configure(app, stub)
    answer = app.assist({'action': 'ask', 'question': '这个项目换过许可证吗？', 'search': True})
    assert answer['text'] == 'STUB-SEARCH-PROSE' and answer['searches']
    plain = app.assist({'action': 'ask', 'question': '为何阻断？'})
    assert 'searches' not in plain
    data = app.interpret({'code': '# SPDX-License-Identifier: MIT\nx = 1\n', 'name': 'f.py'})
    assert data['llm']['text'] == 'STUB-SEARCH-PROSE' and data['llm']['searches']
    app.llm_save({'base_url': stub, 'api_key': KEY, 'model': 'model-a', 'tavily_api_key': ''})
    # 显式留空沿用旧密钥，因此仍走搜索；清除后才回到纯解读
    app.llm_clear()
    app.llm_save({'base_url': stub, 'api_key': KEY, 'model': 'model-a'})
    data = app.interpret({'code': 'x = 1\n', 'name': 'f.py'})
    assert 'searches' not in data['llm']
    with pytest.raises(ValueError, match='Tavily'):
        app.assist({'action': 'ask', 'question': '联网查一下', 'search': True})