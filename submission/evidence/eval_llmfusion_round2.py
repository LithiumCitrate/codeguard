"""Round-2 real-project benchmark for the llmFusion aggressive version.

Inputs are real source files from shallow git clones of public GitHub repos
(no built-in demos). LLM candidate proposal is non-deterministic, so each case
runs N trials. Safety invariants are hard-asserted on EVERY trial; detection is
reported as a rate across trials. For each trial: offline scan baseline ->
/api/webprobe -> offline scan again, asserting the offline verdict is untouched.
Keys come from environment variables at runtime; results are leak-checked.
"""
import hashlib
import json
import os
import time
import urllib.request

BASE = 'http://127.0.0.1:8765'
OUT = os.path.dirname(os.path.abspath(__file__))
REPOS = os.path.join(OUT, 'repos')
N_TRIALS = 5


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.load(r)


def post(path, data, token, timeout=600):
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode('utf-8'),
                                 headers={'Content-Type': 'application/json',
                                          'X-CodeGuard-Token': token})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def read_repo_file(rel):
    with open(os.path.join(REPOS, rel), encoding='utf-8') as fh:
        return fh.read()


def verdict_signature(scan):
    return {'blocking': scan['blocking'],
            'findings': [{'key': f['package'] + '@' + f['version'] + ':' + f['path'],
                          'risk': f['risk'], 'confidence': f['confidence'],
                          'coverage': f['coverage'], 'verbatim': f['max_verbatim_run']}
                         for f in scan['findings']]}


CASES = [
    {'id': 'W1-ranger-gpl-out-of-corpus',
     'file': 'ranger/ranger/ext/rifle.py', 'name': 'rifle.py',
     'license': 'LicenseRef-Proprietary', 'usage': 'distribution',
     'upstream': 'ranger', 'permissive': False,
     'expect': '语料外 GPL-3.0 原文：离线不阻断，联网溯源应能命中 ranger（最高 S3）'},
    {'id': 'W2-itsdangerous-mit-out-of-corpus',
     'file': 'itsdangerous/src/itsdangerous/serializer.py',
     'name': 'serializer.py', 'license': 'MIT', 'usage': 'distribution',
     'upstream': 'itsdangerous', 'permissive': True,
     'expect': '语料外宽松许可原文：即使命中也应不阻断、不过度定级'},
    {'id': 'W3-toml-mit-niche',
     'file': 'toml/toml/decoder.py', 'name': 'decoder.py',
     'license': 'MIT', 'usage': 'distribution',
     'upstream': 'toml', 'permissive': True,
     'expect': '小众 MIT 真实文件：不得产生阻断级误报'},
    {'id': 'W4-synapse-license-drift',
     'file': 'synapse/synapse/util/stringutils.py', 'name': 'stringutils.py',
     'license': 'LicenseRef-Proprietary', 'usage': 'distribution',
     'upstream': 'synapse', 'permissive': True,
     'expect': '许可证漂移观察：仓库现 Apache-2.0，模型记忆可能滞后；只记录不强制命中'},
]


def run_trial(case, code, token):
    before = post('/api/scan', {'code': code, 'name': case['name'],
                                'license': case['license'], 'usage': case['usage']}, token)
    t0 = time.time()
    probe = post('/api/webprobe', {'code': code, 'name': case['name'],
                                   'license': case['license'], 'usage': case['usage']}, token)
    elapsed = round(time.time() - t0, 2)
    after = post('/api/scan', {'code': code, 'name': case['name'],
                               'license': case['license'], 'usage': case['usage']}, token)

    # ---- safety invariants: must hold on EVERY trial --------------------
    assert verdict_signature(before) == verdict_signature(after), 'offline verdict mutated'
    assert probe['blocking'] is False, 'web channel must never block'
    for f in probe.get('findings', []):
        assert f['risk'] != 'S4', 'web findings must cap at S3'
        assert f.get('web_sourced') is True
        assert f['provenance']['url'].startswith('https://')
        assert f['provenance']['sha256'] and f['provenance']['fetched_at'], 'audit fields missing'
        if case['permissive']:
            assert f['risk'] in ('S0', 'S1', 'S2'), 'permissive source over-graded: ' + f['risk']

    findings = probe.get('findings', [])
    top = findings[0] if findings else None
    return {'seconds': elapsed,
            'offline_blocking': before['blocking'],
            'offline_findings': len(before['findings']),
            'detected': bool(findings),
            'fetched': len(probe.get('fetched', [])),
            'searches': len(probe.get('searches', [])),
            'search_errors': sum(1 for s in probe.get('searches', []) if s.get('error')),
            'top': ({'risk': top['risk'], 'package': top['package'],
                     'license': top['license_spdx'], 'confidence': top['confidence'],
                     'verbatim': top['max_verbatim_run'],
                     'url': top['provenance']['url']} if top else None),
            'fetched_urls': [f.get('url') for f in probe.get('fetched', [])],
            'fetch_errors': [f.get('error') for f in probe.get('fetched', []) if f.get('error')]}


def main():
    health = get('/api/health')
    token = health['token']
    assert health['ready'], 'corpus not ready'
    if os.environ.get('LLM_KEY'):
        cfg = post('/api/llm/config', {
            'base_url': os.environ['LLM_BASE'], 'api_key': os.environ['LLM_KEY'],
            'model': os.environ['LLM_MODEL'], 'tavily_api_key': os.environ['TAVILY_KEY']}, token)
        print('configured:', cfg['model'], '| tavily:', cfg['tavily_configured'], flush=True)

    results = []
    for case in CASES:
        code = read_repo_file(case['file'])
        entry = {'id': case['id'], 'expect': case['expect'], 'file': case['file'],
                 'upstream': case['upstream'],
                 'source_sha256': hashlib.sha256(code.encode()).hexdigest(),
                 'chars': len(code), 'trials': []}
        print('\n==', case['id'], '(%d chars, %d trials)' % (len(code), N_TRIALS), flush=True)
        for i in range(N_TRIALS):
            trial = run_trial(case, code, token)
            entry['trials'].append(trial)
            t = trial['top']
            print('   trial %d: %.1fs detected=%s' % (i + 1, trial['seconds'], trial['detected'])
                  + (' -> %s %s %s conf=%.3f verbatim=%d' % (
                      t['risk'], t['package'], t['license'], t['confidence'], t['verbatim']) if t else '')
                  + (' | fetch_errors=%s' % trial['fetch_errors'] if trial['fetch_errors'] else '')
                  + (' | search_errors=%d' % trial['search_errors'] if trial['search_errors'] else ''),
                  flush=True)
        hits = sum(1 for t in entry['trials'] if t['detected'])
        entry['detection_rate'] = '%d/%d' % (hits, N_TRIALS)
        entry['correct_upstream_rate'] = '%d/%d' % (
            sum(1 for t in entry['trials'] if t['top'] and case['upstream'] in t['top']['url']), N_TRIALS)
        print('   detection %s | correct-upstream %s' % (
            entry['detection_rate'], entry['correct_upstream_rate']), flush=True)
        results.append(entry)

    # ---- safety assertions: hard guarantees, independent of LLM luck ------
    # Detection is a measured rate (LLM proposal is non-deterministic); the
    # guarantees below must hold on every trial regardless of detection.
    for entry in results:
        assert all(not t['offline_blocking'] for t in entry['trials']), 'offline baseline blocking'
        for t in entry['trials']:
            if t['top']:
                assert entry['upstream'] in t['top']['url'], \
                    '%s: detected wrong upstream %s' % (entry['id'], t['top']['url'])
                if entry['id'].startswith('W1'):
                    assert t['top']['risk'] in ('S2', 'S3'), 'W1 grading'
    w1 = results[0]
    assert not any(t['offline_blocking'] for t in w1['trials']), 'ranger should be out of corpus'

    summary = {'trials_per_case': N_TRIALS,
               'safety_invariants': 'held on all %d trials' % (len(CASES) * N_TRIALS),
               'cases': [{'id': e['id'], 'detection_rate': e['detection_rate'],
                          'correct_upstream_rate': e['correct_upstream_rate']} for e in results]}
    blob = json.dumps({'summary': summary, 'results': results}, ensure_ascii=False, indent=2)
    for secret in (os.environ.get('LLM_KEY', ''), os.environ.get('TAVILY_KEY', '')):
        if secret:
            assert secret not in blob, 'SECRET LEAKED INTO RESULTS'
    with open(os.path.join(OUT, 'round2-results.json'), 'w', encoding='utf-8') as fh:
        fh.write(blob)
    print('\nSUMMARY:', json.dumps(summary, ensure_ascii=False), flush=True)
    print('SAFETY INVARIANTS HELD ON ALL TRIALS — saved round2-results.json (key-leak check passed)', flush=True)


if __name__ == '__main__':
    main()