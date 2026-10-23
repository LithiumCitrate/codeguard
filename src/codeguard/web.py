"""Loopback-only, offline review workbench. Submitted code is never executed.

v0.4.0 adds the optional LLM interpretation layer: a first-run setup that
stores base URL / API key / model in the local workspace (never in the repo,
never returned to the browser), model listing, AI file reading, scan summaries
and grounded Q&A. Risk verdicts stay deterministic in every code path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .adjudicate import Scanner
from .cli import load_model
from .index import FingerprintIndex
from .license_intel import RISK_LABELS, analyze
from .llm import (DISCLOSURE, clear_llm_settings, extract_license_markers,
                  list_models, load_llm_settings, mask_key, provider_from_settings,
                  save_llm_settings, validate_base_url)
from .llm import get_provider
from .report import provenance_receipt, to_cyclonedx, to_html

USAGES = {'internal_use', 'inline_copy', 'static_link', 'dynamic_link', 'distribution', 'network_service'}


class Workbench:
    def __init__(self, workspace):
        self.root = Path(workspace).resolve()
        self.index = FingerprintIndex.load(str(self.root / 'index.bin'))
        # Persisted indexes contain the original machine's absolute path.
        # The adjacent corpus is authoritative for portable distributions.
        self.index.corpus_root = str(self.root / 'corpus')
        self.model = load_model(str(self.root))
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.last_digest = None

    # ------------------------------------------------------------------- llm

    def llm_status(self):
        data = load_llm_settings(self.root)
        if data:
            return {'configured': True, 'base_url': data['base_url'],
                    'model': data['model'], 'key_masked': mask_key(data['api_key'])}
        return {'configured': False, 'base_url': '', 'model': '', 'key_masked': ''}

    def llm_models(self, data):
        return {'models': list_models(data.get('base_url'), data.get('api_key'))}

    def llm_save(self, data):
        existing = load_llm_settings(self.root)
        api_key = data.get('api_key')
        if not api_key and existing and data.get('base_url', '').strip().rstrip('/') == existing['base_url']:
            api_key = existing['api_key']  # 只改模型/不改密钥时沿用已保存密钥
        save_llm_settings(self.root, data.get('base_url'), api_key, data.get('model'))
        return self.llm_status()

    def llm_clear(self):
        return {'cleared': clear_llm_settings(self.root)}

    def interpret(self, data):
        code = data.get('code')
        if not isinstance(code, str) or not code.strip():
            raise ValueError('请输入需要解读的源代码')
        if len(code.encode('utf-8')) > 200_000:
            raise ValueError('单次代码上限为 200 KB，请拆分文件')
        name = str(data.get('name', 'review.py'))[:120].replace('\\', '/').split('/')[-1]
        markers = extract_license_markers(code)
        provider = provider_from_settings(self.root)
        llm = None
        if provider is not None:
            try:
                llm = {'model': provider.model, 'text': provider.interpret_file(code, name, markers)}
            except ValueError as exc:
                llm = {'model': provider.model, 'error': '解读失败：%s' % exc}
        return {'markers': markers, 'llm': llm,
                'statement': DISCLOSURE}

    def assist(self, data):
        action = data.get('action', 'summary')
        if self.last_digest is None:
            raise ValueError('请先完成一次来源审查，再使用 AI 摘要或提问')
        provider = provider_from_settings(self.root)
        if action == 'summary':
            if provider is None:
                return {'offline': True, 'model': '', 'text': self._offline_summary(self.last_digest)}
            try:
                return {'offline': False, 'model': provider.model,
                        'text': provider.summarize_scan(self.last_digest)}
            except ValueError as exc:
                return {'offline': True, 'model': provider.model,
                        'text': self._offline_summary(self.last_digest) + '\n（大模型调用失败，已回退到确定性摘要：%s）' % exc}
        if action == 'ask':
            question = data.get('question')
            if not isinstance(question, str) or not (2 <= len(question.strip()) <= 1000):
                raise ValueError('问题长度需在 2–1000 字之间')
            if provider is None:
                raise ValueError('追问需要大模型支持；请先在右上角配置大模型')
            return {'offline': False, 'model': provider.model,
                    'text': provider.answer_question(question.strip(), self.last_digest)}
        raise ValueError('无效的 assist 动作')

    @staticmethod
    def _offline_summary(digest):
        findings = digest['findings']
        head = '目标 %s（%s / %s）：片段命中 %d/%d，%s。' % (
            digest['target'], digest['target_license'], digest['usage'],
            digest['matched_spans'], digest['total_spans'],
            '建议阻断' if digest['blocking'] else '未触发阻断')
        if not findings:
            return head + '\n当前语料内未发现足够来源证据；未命中不代表已排查所有开源项目。'
        lines = [head]
        for f in findings[:5]:
            lines.append('%s@%s（%s）：%s，证据评分 %.3f，最长逐字 %d token，义务 %d 项。' % (
                f['package'], f['version'], f['license_spdx'], f['risk'],
                f['confidence'], f['max_verbatim_run'], len(f['obligations'])))
        return '\n'.join(lines)

    def license_explain(self, data):
        usage = data.get('usage', 'distribution')
        if usage not in USAGES:
            raise ValueError('无效使用方式')
        analysis = analyze(str(data.get('source', ''))[:100], str(data.get('target', ''))[:100], usage)
        provider = provider_from_settings(self.root)
        llm = None
        if provider is not None:
            try:
                llm = {'model': provider.model, 'text': provider.explain_licence(analysis.as_dict())}
            except ValueError as exc:
                llm = {'model': provider.model, 'error': '解释失败：%s' % exc}
        return {'analysis': analysis.as_dict(), 'llm': llm}

    def health(self):
        total, readable = self.index.corpus_health()
        mismatched = 0
        for doc in self.index.docs:
            try:
                digest = hashlib.sha256(Path(self.index.corpus_file(doc)).read_bytes()).hexdigest()
                mismatched += digest != doc.sha256
            except OSError:
                continue
        llm = self.llm_status()
        return {'stats': self.index.stats(), 'corpus': {'total': total, 'readable': readable, 'mismatched': mismatched},
                'ready': total > 0 and total == readable and mismatched == 0,
                'model': '12维逻辑回归' if self.model else '规则回退（未加载模型）',
                'llm': {'configured': llm['configured'], 'model': llm['model'], 'base_url': llm['base_url']},
                'privacy': '本机离线分析；代码不执行、不上传、不持久保存；仅在你主动点击 AI 功能时才调用你配置的大模型接口',
                'token': self.token}

    def scan(self, data):
        code = data.get('code')
        if not isinstance(code, str) or not code.strip():
            raise ValueError('请输入需要审查的源代码')
        if len(code.encode('utf-8')) > 200_000:
            raise ValueError('单次代码上限为 200 KB，请拆分文件')
        usage = data.get('usage', 'distribution')
        license_id = data.get('license', 'MIT')
        if usage not in USAGES or not isinstance(license_id, str) or len(license_id) > 100:
            raise ValueError('许可证或使用方式无效')
        if not self.health()['ready']:
            raise ValueError('语料原文缺失或哈希不一致，无法完成可信验证；请重新建立语料')
        name = str(data.get('name', 'review.py'))[:120].replace('\\', '/').split('/')[-1]
        with self.lock:
            result = Scanner(self.index, model=self.model, usage=usage).scan_text(
                code, target=name, target_license=license_id)
            llm_provider = provider_from_settings(self.root) if data.get('assist') else None
            provider = llm_provider or get_provider('offline')
            explanations = {f.key: provider.describe(f) for f in result.findings}
            receipt = provenance_receipt(result, self.index, explanations)
            receipt['metadata']['ai_usage'].update(
                provider=provider.name, external_calls=bool(llm_provider),
                model=getattr(provider, 'model', ''))
            receipt['metadata'].pop('corpus_root', None)
            receipt['subject']['sha256'] = hashlib.sha256(code.encode()).hexdigest()
            model_file = self.root / 'model.json'
            receipt['metadata']['judge'] = {
                'type': 'logistic-regression' if self.model else 'rule-fallback',
                'sha256': hashlib.sha256(model_file.read_bytes()).hexdigest() if model_file.exists() else None}
            details = []
            for finding in result.findings:
                item = finding.as_dict()
                item['explanation'] = explanations[finding.key]
                item['snippets'] = []
                doc = next(d for d in self.index.docs if d.path == finding.path and d.package == finding.package)
                source = Path(self.index.corpus_file(doc)).read_text(encoding='utf-8', errors='replace').splitlines()
                query = code.splitlines()
                for span in finding.spans[:4]:
                    a, b = span.lines
                    c, d = span.pair.line_start, span.pair.line_end
                    item['snippets'].append({'query_start': a, 'source_start': c,
                        'query': '\n'.join(query[a-1:b]), 'source': '\n'.join(source[c-1:d])})
                details.append(item)
            self.last_digest = {
                'target': result.target, 'target_license': result.target_license,
                'usage': result.usage, 'blocking': result.blocking,
                'total_spans': result.total_spans, 'matched_spans': result.matched_spans,
                'findings': [{'package': f.package, 'version': f.version, 'path': f.path,
                              'license_spdx': f.license_spdx, 'risk': f.risk,
                              'risk_label': RISK_LABELS[f.risk], 'confidence': f.confidence,
                              'coverage': f.coverage, 'max_verbatim_run': f.max_verbatim_run,
                              'status': f.verdict.status,
                              'obligations': f.verdict.obligations,
                              'conflicts': f.verdict.conflicts}
                             for f in result.findings]}
            return {'scan': result.as_dict(), 'blocking': result.blocking, 'findings': details,
                    'receipt': receipt, 'sbom': to_cyclonedx(result, self.index), 'html': to_html(receipt),
                    'llm_assisted': bool(llm_provider),
                    'llm_model': llm_provider.model if llm_provider else ''}

    def demo(self, kind):
        if kind == 'clean':
            path = Path(__file__).parent / 'data' / 'negatives' / 'word_tally.py'
            return {'name': 'independent_word_tally.py', 'code': path.read_text(encoding='utf-8'),
                    'note': '自研独立实现负例；未命中只代表当前语料覆盖范围内未发现来源。'}
        docs = [d for d in self.index.docs if d.license_spdx.startswith(('GPL-', 'AGPL-')) and d.tokens > 250]
        if not docs:
            raise ValueError('当前语料没有可用的 copyleft 演示来源')
        doc = sorted(docs, key=lambda d: (d.tokens, d.path))[0]
        code = Path(self.index.corpus_file(doc)).read_text(encoding='utf-8', errors='replace')
        if kind == 'rename':
            from .mutations import apply_mutation
            code = apply_mutation(code, 'rename', 2026)
        return {'name': 'ai_generated_demo.py', 'code': code,
                'note': '受控来源演示：%s@%s / %s；%s。该案例不等同于真实模型泄漏实验。' %
                        (doc.package, doc.version, doc.license_spdx, '变量改名' if kind == 'rename' else '原文复制')}


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body, mime='application/json; charset=utf-8'):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') in {'127.0.0.1:%d' % self.server.server_port, 'localhost:%d' % self.server.server_port}

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error': '仅允许本机访问'})
            try:
                if self.path == '/api/health':
                    return self.send(200, app.health())
                if self.path.startswith('/api/demo/'):
                    kind = self.path.rsplit('/', 1)[-1]
                    if kind not in {'copy', 'rename', 'clean'}:
                        raise ValueError('无效演示')
                    return self.send(200, app.demo(kind))
                assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                          '/style.css': ('style.css', 'text/css'),
                          '/fonts/Saira.ttf': ('fonts/Saira.ttf', 'font/ttf')}
                if self.path not in assets:
                    return self.send(404, {'error': '页面不存在'})
                name, mime = assets[self.path]
                return self.send(200, (Path(__file__).parent / 'static' / name).read_bytes(), mime + '; charset=utf-8')
            except ValueError as exc:
                self.send(400, {'error': str(exc)})
            except Exception:
                self.send(500, {'error': '读取失败，请检查语料与程序文件'})

        def do_POST(self):
            if not self.valid_host() or self.headers.get('X-CodeGuard-Token') != app.token:
                return self.send(403, {'error': '会话失效，请刷新页面'})
            routes = {'/api/scan': app.scan, '/api/licenses': None,
                      '/api/llm/models': app.llm_models, '/api/llm/config': app.llm_save,
                      '/api/llm/clear': app.llm_clear, '/api/interpret': app.interpret,
                      '/api/assist': app.assist, '/api/license/explain': app.license_explain}
            if self.path not in routes:
                return self.send(404, {'error': '接口不存在'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 1_300_000:
                    return self.send(413, {'error': '请求大小超限'})
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('请求必须是对象')
                if self.path == '/api/licenses':
                    usage = data.get('usage', 'distribution')
                    if usage not in USAGES:
                        raise ValueError('无效使用方式')
                    return self.send(200, analyze(str(data.get('source', ''))[:100], str(data.get('target', ''))[:100], usage).as_dict())
                self.send(200, routes[self.path](data))
            except (ValueError, TypeError) as exc:
                self.send(400, {'error': str(exc)})
            except Exception:
                self.send(500, {'error': '分析失败，请检查语料完整性或拆分输入文件'})
    return Handler


def serve(workspace='.codeguard', port=8765, open_browser=True):
    app = Workbench(workspace)
    server = ThreadingHTTPServer(('127.0.0.1', port), handler_for(app))
    server.daemon_threads = True
    url = 'http://127.0.0.1:%d' % server.server_port
    print('CodeGuard 工作台：' + url, flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', default='.codeguard')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    serve(args.workspace, args.port, not args.no_browser)


if __name__ == '__main__':
    main()
