"""Development-only validation against downloaded official schemas.

Two artefacts are checked, both against the schema published by the standards
body (files live in ``release/schema``, which is not part of the distributed
package):

* CycloneDX 1.6 - the SBOM the workbench emits for a real scan;
* SARIF 2.1.0 - the report ``codeguard scan --format sarif`` writes, exercised
  through the CLI so the validated document is the one a user gets.

    python scripts/validate_sbom.py
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import jsonschema
from referencing import Registry, Resource

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
from codeguard.web import Workbench

schemas = [json.loads(p.read_text()) for p in (root / 'release' / 'schema').glob('*.json')]
registry = Registry().with_resources([(s['$id'], Resource.from_contents(s)) for s in schemas
                                     if s.get('$id')])
schema = next(s for s in schemas if s['$id'].endswith('bom-1.6.schema.json'))
app = Workbench(root / '.codeguard')
demo = app.demo('copy')
result = app.scan({'code': demo['code'], 'name': demo['name'], 'license': 'MIT', 'usage': 'distribution'})
jsonschema.Draft7Validator(schema, registry=registry).validate(result['sbom'])
out = root / 'submission' / 'evidence'
for name, body in [('web-demo.cdx.json', result['sbom']), ('web-demo.provenance.json', result['receipt'])]:
    (out / name).write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding='utf-8')
(out / 'web-demo.report.html').write_text(result['html'], encoding='utf-8')
print('CycloneDX 1.6 official JSON Schema: passed')

sarif_schema = next((s for s in schemas if 'sarif' in s.get('$id', '')), None)
if sarif_schema is None:
    raise SystemExit('release/schema 里缺少 SARIF 2.1.0 schema：'
                     'https://docs.oasis-open.org/sarif/sarif/v2.1.0/os/schemas/sarif-schema-2.1.0.json')
with tempfile.TemporaryDirectory() as work:
    sample = Path(work) / 'feature_flags.py'
    sample.write_text(demo['code'], encoding='utf-8')
    report_dir = Path(work) / 'reports'
    env = dict(__import__('os').environ, PYTHONPATH=str(root / 'src'))
    code = subprocess.run([sys.executable, '-m', 'codeguard', 'scan', str(sample),
                           '--license', 'MIT', '--usage', 'distribution',
                           '--format', 'sarif', '--out', str(report_dir)],
                          cwd=str(root), env=env).returncode
    produced = sorted(report_dir.glob('*.sarif'))
    if code not in (0, 1) or not produced:
        raise SystemExit('CLI 没有产出 SARIF（退出码 %s，文件 %s）' % (code, produced))
    document = json.loads(produced[0].read_text(encoding='utf-8'))
    jsonschema.Draft7Validator(sarif_schema, registry=registry).validate(document)
    (out / 'web-demo.sarif.json').write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    runs = document['runs'][0]
    print('SARIF 2.1.0 official JSON Schema: passed '
          '(version=%s, rules=%d, results=%d, exit=%d)'
          % (document['version'], len(runs['tool']['driver'].get('rules', [])),
             len(runs.get('results', [])), code))

