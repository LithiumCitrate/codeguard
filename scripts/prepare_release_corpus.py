"""Verify pinned PyPI archives, retain original legal files for redistribution.

Never executes or installs the corpus packages. Full original source archives
are retained alongside extracted read-only samples for corresponding-source
availability. Publication still requires the team's resource review.
"""
import concurrent.futures
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from codeguard.corpus import fetch_json, fetch_bytes, _iter_archive_files, SOURCE_FILENAME_RE

root = Path(__file__).resolve().parents[1]
corpus = root / '.codeguard' / 'corpus'
entries = json.loads((corpus / 'corpus.json').read_text(encoding='utf-8'))['entries']
groups = {}
for entry in entries:
    groups.setdefault((entry['package'], entry['version']), []).append(entry)
archives = root / '.codeguard' / 'upstream-archives'
archives.mkdir(exist_ok=True)


def prepare(pair):
    (package, version), group = pair
    metadata_path = archives / ('%s-%s.metadata.json' % (package, version))
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    else:
        metadata = retry(lambda: fetch_json('https://pypi.org/pypi/%s/%s/json' % (package, version), timeout=25))
        metadata_path.write_text(json.dumps(metadata), encoding='utf-8')
    expected = group[0]['sdist_sha256']
    distribution = next(u for u in metadata['urls'] if u['digests']['sha256'] == expected)
    target = archives / distribution['filename']
    blob = target.read_bytes() if target.exists() else retry(lambda: fetch_bytes(distribution['url'], timeout=50))
    if hashlib.sha256(blob).hexdigest() != expected:
        raise RuntimeError('%s archive digest mismatch' % package)
    target.write_bytes(blob)
    files = dict(_iter_archive_files(blob, target.suffix == '.zip' or target.suffix == '.whl'))
    legal = []
    for name, data in files.items():
        rel = PurePosixPath('/'.join(name.split('/')[1:]))
        if rel.is_absolute() or '..' in rel.parts:
            raise RuntimeError('Unsafe archive path')
        if SOURCE_FILENAME_RE.search(rel.name):
            out = corpus / ('%s-%s' % (package, version)) / str(rel)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            legal.append(str(rel))
    for entry in group:
        path = corpus / entry['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise RuntimeError('Corpus digest mismatch: ' + entry['path'])
        original = next((data for name, data in files.items()
                         if '/'.join(name.split('/')[1:]) == '/'.join(entry['path'].split('/')[1:])), None)
        if original is None or hashlib.sha256(original).hexdigest() != entry['sha256']:
            raise RuntimeError('Corpus not in original archive: ' + entry['path'])
    if not legal:
        raise RuntimeError('No legal files: ' + package)
    return {'package': package, 'version': version, 'license': group[0]['license_spdx'],
            'url': distribution['url'], 'sha256': expected, 'archive': target.name,
            'files_verified': len(group), 'legal_files': legal}


def retry(action):
    for attempt in range(4):
        try:
            return action()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(attempt + 1)


if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        result = list(pool.map(prepare, groups.items()))
    out = root / 'submission' / 'evidence' / 'corpus-integrity.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Verified %d packages / %d source files with original archives and legal notices.' % (len(result), len(entries)))
