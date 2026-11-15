"""Round-1 real-case test for the llmFusion minimal version.

Keys come from environment variables at runtime; nothing secret is written to
disk except the workbench's own gitignored workspace config. Results (no keys)
are saved next to this script for inspection.
"""
import json
import os
import sys
import time
import urllib.request

BASE = 'http://127.0.0.1:8765'
OUT = os.path.dirname(os.path.abspath(__file__))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.load(r)


def post(path, data, token, timeout=300):
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode('utf-8'),
                                 headers={'Content-Type': 'application/json',
                                          'X-CodeGuard-Token': token})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'codeguard-llmfusion-test'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8', 'replace')


def main():
    health = get('/api/health')
    token = health['token']
    assert health['ready'], 'corpus not ready'
    cfg = post('/api/llm/config', {
        'base_url': os.environ['LLM_BASE'], 'api_key': os.environ['LLM_KEY'],
        'model': os.environ['LLM_MODEL'], 'tavily_api_key': os.environ['TAVILY_KEY']}, token)
    print('configured:', cfg['model'], '| tavily:', cfg['tavily_configured'], flush=True)

    sys.path.insert(0, os.path.join(os.path.dirname(OUT), '..', 'codeguard', 'src'))
    from codeguard.mutations import apply_mutation

    print('fetching real GitHub files...', flush=True)
    minio = fetch('https://raw.githubusercontent.com/minio/minio/7aac2a2c5b/cmd/api-resources.go')
    git_c = fetch('https://raw.githubusercontent.com/git/git/7e34d8174d/builtin/hash-object.c')
    clean = fetch('https://raw.githubusercontent.com/pallets/itsdangerous/main/src/itsdangerous/timed.py')
    vendor = fetch('https://raw.githubusercontent.com/pypa/pip/main/src/pip/_vendor/urllib3/util/url.py')
    cases = [
        {'id': 'A-minio-agpl-copy', 'name': 'api-resources.go', 'code': minio,
         'license': 'LicenseRef-Proprietary', 'usage': 'distribution',
         'expect': 'AGPL 原文复制，应命中 minio 且阻断级'},
        {'id': 'B-git-gpl-renamed', 'name': 'hash-object.c',
         'code': apply_mutation(git_c, 'rename', 2026),
         'license': 'LicenseRef-Proprietary', 'usage': 'distribution',
         'expect': 'GPL 改名变异，应命中 git'},
        {'id': 'C-itsdangerous-clean', 'name': 'timed.py', 'code': clean,
         'license': 'MIT', 'usage': 'distribution',
         'expect': '语料外独立项目，不应阻断'},
        {'id': 'D-pip-vendored-urllib3', 'name': 'url.py', 'code': vendor,
         'license': 'MIT', 'usage': 'distribution',
         'expect': '真实 vendoring，可能命中 urllib3，观察评级'},
    ]
    results = []
    for case in cases:
        t0 = time.time()
        scan = post('/api/scan', {'code': case['code'], 'name': case['name'],
                                  'license': case['license'], 'usage': case['usage']}, token)
        entry = {'id': case['id'], 'expect': case['expect'],
                 'source_sha256': __import__('hashlib').sha256(case['code'].encode()).hexdigest(),
                 'scan_seconds': round(time.time() - t0, 2),
                 'blocking': scan['blocking'],
                 'findings': [{'key': f['package'] + '@' + f['version'] + ':' + f['path'],
                               'risk': f['risk'], 'confidence': f['confidence'],
                               'coverage': f['coverage'], 'verbatim': f['max_verbatim_run']}
                              for f in scan['findings']]}
        print('\n==', case['id'], '| blocking:', scan['blocking'],
              '| findings:', len(scan['findings']), flush=True)
        for f in entry['findings'][:3]:
            print('   ', f['risk'], f['key'], 'conf=%.3f' % f['confidence'], flush=True)
        if scan['findings']:
            t0 = time.time()
            deep = post('/api/assist', {'action': 'deep', 'index': 0}, token)
            entry['deep'] = {'seconds': round(time.time() - t0, 2),
                             'model': deep['model'], 'risk': deep['risk'],
                             'text': deep['text'], 'searches': deep['searches']}
            print('    deep dive: %d searches, %.1fs' % (len(deep['searches']), entry['deep']['seconds']), flush=True)
            for s in deep['searches']:
                print('      q:', s['query'], '| results:', len(s.get('results', [])),
                      ('| ERROR: ' + s['error']) if s.get('error') else '', flush=True)
        t0 = time.time()
        ask = post('/api/assist', {'action': 'ask', 'search': True,
                                   'question': '结合公开资料，这个审查结果里最需要注意的合规风险是什么？来源项目的许可证近年有没有变化？'}, token)
        entry['ask'] = {'seconds': round(time.time() - t0, 2), 'text': ask['text'],
                        'searches': ask.get('searches', [])}
        print('    ask+search: %d searches, %.1fs' % (len(ask.get('searches', [])), entry['ask']['seconds']), flush=True)
        results.append(entry)

    blob = json.dumps(results, ensure_ascii=False, indent=2)
    for secret in (os.environ['LLM_KEY'], os.environ['TAVILY_KEY']):
        assert secret not in blob, 'SECRET LEAKED INTO RESULTS'
    with open(os.path.join(OUT, 'round1-results.json'), 'w', encoding='utf-8') as fh:
        fh.write(blob)
    print('\nsaved round1-results.json (key-leak check passed)', flush=True)


if __name__ == '__main__':
    main()