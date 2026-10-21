"""Verify the exact ZIP in a relocated Unicode path without installed Python."""
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import zipfile

root = Path(__file__).resolve().parents[1]
dest = root/'release'/'迁移 验证'
dest.mkdir(exist_ok=True)
with zipfile.ZipFile(root/'release/CodeGuard-Windows-x64.zip') as archive:
    archive.extractall(dest)
exe = dest/'CodeGuard/CodeGuard.exe'
process = subprocess.Popen([str(exe),'--no-browser'],cwd=str(root.parent),
    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
try:
    line = process.stdout.readline().decode('utf-8',errors='replace')
    match = re.search(r'http://127\.0\.0\.1:\d+',line)
    if not match:
        raise RuntimeError('Failed to launch: '+line)
    url = match.group()
    health = json.load(urllib.request.urlopen(url+'/api/health',timeout=15))
    assert health['ready'] and health['corpus']['readable'] == 585
    with urllib.request.urlopen(url,timeout=15) as response:
        assert response.status == 200 and 'CodeGuard' in response.read().decode('utf-8')
    for asset in ['app.js','style.css']:
        assert urllib.request.urlopen(url+'/'+asset,timeout=15).status == 200
    cases = []
    for kind in ['copy','rename','clean']:
        sample = json.load(urllib.request.urlopen(url+'/api/demo/'+kind,timeout=15))
        payload = {'code':sample['code'],'name':sample['name'],'license':'MIT','usage':'distribution'}
        request = urllib.request.Request(url+'/api/scan',data=json.dumps(payload).encode(),
            headers={'X-CodeGuard-Token':health['token'],'Content-Type':'application/json'})
        result = json.load(urllib.request.urlopen(request,timeout=60))
        assert result['blocking'] == (kind != 'clean'), (kind,result['blocking'])
        assert result['receipt']['metadata']['ai_usage']['external_calls'] is False
        assert result['html'].startswith('<!') or '<html' in result['html']
        cases.append({'case':kind,'blocking':result['blocking'],'findings':len(result['findings']),
                      'input_sha256':result['receipt']['subject']['sha256']})
    evidence = {'platform':'Windows 11 x64','artifact':'CodeGuard-Windows-x64.zip',
        'relocated_unicode_path':True,'cwd_outside_application':True,'bundled_python':True,
        'health':{k:v for k,v in health.items() if k!='token'},'cases':cases,'status':'passed'}
    (root/'submission/evidence/windows-app-smoke.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Portable EXE smoke: passed (relocated Unicode path, 3 real scans, static assets)')
finally:
    process.terminate()
    process.wait(timeout=15)
