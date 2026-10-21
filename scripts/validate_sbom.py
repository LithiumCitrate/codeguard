"""Development-only validation against downloaded official CycloneDX schemas."""
import json
from pathlib import Path
import sys
import jsonschema
from referencing import Registry, Resource

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
from codeguard.web import Workbench

schemas = [json.loads(p.read_text()) for p in (root / 'release' / 'schema').glob('*.json')]
registry = Registry().with_resources([(s['$id'], Resource.from_contents(s)) for s in schemas])
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
