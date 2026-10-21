"""Loopback-only, offline review workbench. Submitted code is never executed."""
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
from .license_intel import analyze
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

    def health(self):
        total, readable = self.index.corpus_health()
        mismatched = 0
        for doc in self.index.docs:
            try:
                digest = hashlib.sha256(Path(self.index.corpus_file(doc)).read_bytes()).hexdigest()
                mismatched += digest != doc.sha256
            except OSError:
                continue
        return {'stats': self.index.stats(), 'corpus': {'total': total, 'readable': readable, 'mismatched': mismatched},
                'ready': total > 0 and total == readable and mismatched == 0,
                'model': '12维逻辑回归' if self.model else '规则回退（未加载模型）',
                'privacy': '本机离线分析；代码不执行、不上传、不持久保存', 'token': self.token}

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
            provider = get_provider('offline')
            explanations = {f.key: provider.describe(f) for f in result.findings}
            receipt = provenance_receipt(result, self.index, explanations)
            receipt['metadata']['ai_usage'].update(provider='offline-template', external_calls=False, model='')
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
            return {'scan': result.as_dict(), 'blocking': result.blocking, 'findings': details,
                    'receipt': receipt, 'sbom': to_cyclonedx(result, self.index), 'html': to_html(receipt)}

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
                assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
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
            if self.path not in {'/api/scan', '/api/licenses'}:
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
                self.send(200, app.scan(data))
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
