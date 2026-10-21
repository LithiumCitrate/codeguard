"""Assemble portable application and clean source ZIPs, with checksums."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

root = Path(__file__).resolve().parents[1]
release = root / 'release'
app = release / 'app' / 'CodeGuard'
if not (app / 'CodeGuard.exe').exists():
    raise SystemExit('Build the Windows EXE first')
integrity = json.loads((root/'submission/evidence/corpus-integrity.json').read_text(encoding='utf-8'))
data = app / '.codeguard'
data.mkdir(exist_ok=True)
shutil.copytree(root/'.codeguard/corpus', data/'corpus', dirs_exist_ok=True)
for name in ['index.bin','model.json']:
    shutil.copyfile(root/'.codeguard'/name,data/name)
archives = app/'third-party-source'
archives.mkdir(exist_ok=True)
for entry in integrity:
    source = root/'.codeguard/upstream-archives'/entry['archive']
    if hashlib.sha256(source.read_bytes()).hexdigest() != entry['sha256']:
        raise SystemExit('Archive changed: '+entry['archive'])
    shutil.copyfile(source, archives/source.name)
for name in ['LICENSE','NOTICE','THIRD_PARTY_NOTICES.md']:
    shutil.copyfile(root/name,app/name)
shutil.copyfile(root/'docs/WORKBENCH.md',app/'使用说明.md')
shutil.copyfile(root/'submission/evidence/corpus-integrity.json',app/'corpus-integrity.json')
shutil.copyfile(Path(sys.base_prefix)/'LICENSE.txt',app/'PYTHON-LICENSE.txt')
shutil.copyfile(release/'PYINSTALLER-COPYING.txt',app/'PYINSTALLER-COPYING.txt')
bench = root/'.codeguard/benchmark-20261020'
for suffix in ['json','md']:
    shutil.copyfile(bench/('benchmark.'+suffix),root/'submission/evidence'/('benchmark-20261020.'+suffix))
shutil.copyfile(root/'output/pdf/CodeGuard-技术报告-升级版.pdf',root/'submission/CodeGuard-技术报告-升级版.pdf')


def zip_tree(path, filename, prefix):
    with zipfile.ZipFile(filename, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for item in sorted(path.rglob('*')):
            if item.is_file() and '__pycache__' not in item.parts:
                archive.write(item, str(Path(prefix)/item.relative_to(path)))


if '--source-only' not in sys.argv:
    zip_tree(app,release/'CodeGuard-Windows-x64.zip','CodeGuard')
source_zip = release/'CodeGuard-Source.zip'
selected_dirs = ['src/codeguard','tests','scripts','docs','submission','.github','hooks']
selected_files = ['README.md','LICENSE','NOTICE','THIRD_PARTY_NOTICES.md','CONTRIBUTING.md','CHANGELOG.md',
                  'SECURITY.md','pyproject.toml','launch.py','启动工作台.cmd','.gitignore','CodeGuard.spec']
with zipfile.ZipFile(source_zip,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for folder in selected_dirs:
        for item in sorted((root/folder).rglob('*')):
            if item.is_file() and '__pycache__' not in item.parts:
                archive.write(item,str(Path('CodeGuard-Source')/item.relative_to(root)))
    for filename in selected_files:
        archive.write(root/filename,str(Path('CodeGuard-Source')/filename))
checksums = []
handover = sorted(p.name for p in release.glob('CodeGuard-队友材料包-*.zip'))
for filename in ['CodeGuard-Windows-x64.zip','CodeGuard-Source.zip'] + handover:
    path = release/filename
    checksums.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+filename)
    print('%s: %.2f MB' % (filename,path.stat().st_size/1024**2))
(release/'SHA256SUMS.txt').write_text('\n'.join(checksums)+'\n',encoding='utf-8')
