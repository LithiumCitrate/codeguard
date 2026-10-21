"""Restore exact, hash-pinned experiment inputs from original source archives."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'src'))
from codeguard.corpus import fetch_bytes, _iter_archive_files, SOURCE_FILENAME_RE

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--workspace', default='.codeguard')
parser.add_argument('--archive-dir', default='')
args = parser.parse_args()
workspace = Path(args.workspace).resolve()
corpus = workspace/'corpus'
corpus.mkdir(parents=True, exist_ok=True)
archive_dir = Path(args.archive_dir).resolve() if args.archive_dir else workspace/'upstream-archives'
archive_dir.mkdir(parents=True, exist_ok=True)
manifest = json.loads((root/'submission/evidence/corpus-manifest.json').read_text(encoding='utf-8'))
resources = json.loads((root/'submission/evidence/corpus-integrity.json').read_text(encoding='utf-8'))
count = 0
for resource in resources:
    archive = archive_dir/resource['archive']
    blob = archive.read_bytes() if archive.exists() else fetch_bytes(resource['url'])
    if hashlib.sha256(blob).hexdigest() != resource['sha256']:
        raise SystemExit('Archive checksum failed: '+resource['archive'])
    archive.write_bytes(blob)
    group = {entry['path']: entry for entry in manifest['entries'] if entry['package'] == resource['package'] and entry['version'] == resource['version']}
    folder = resource['package']+'-'+resource['version']
    restored = set()
    for name, data in _iter_archive_files(blob, archive.suffix in {'.zip','.whl'}):
        relative = PurePosixPath('/'.join(name.split('/')[1:]))
        if relative.is_absolute() or '..' in relative.parts:
            raise SystemExit('Unsafe archive member')
        path = folder+'/'+str(relative)
        if path not in group and not SOURCE_FILENAME_RE.search(relative.name):
            continue
        if path in group:
            if hashlib.sha256(data).hexdigest() != group[path]['sha256']:
                raise SystemExit('Source checksum failed: '+path)
            restored.add(path)
        target = corpus/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if restored != set(group):
        raise SystemExit('Missing pinned sources in '+resource['archive'])
    count += len(restored)
for entry in manifest['entries']:
    entry['abs_path'] = str(corpus/entry['path'])
(corpus/'corpus.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=1),encoding='utf-8')
print('Restored %d exact source files from %d pinned archives.' % (count,len(resources)))
