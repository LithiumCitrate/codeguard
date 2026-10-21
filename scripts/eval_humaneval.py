"""Build the external clean-implementation benchmark from HumanEval.

HumanEval's canonical solutions are independently written Python functions, not
mutants of the indexed corpus.  They therefore measure the direction the mutation
benchmark cannot: false blocking on code that was not derived from a known
source.  The dataset is MIT-licensed and is fetched by URL + SHA-256; it is not
redistributed in the repository.

Usage:
    python scripts/eval_humaneval.py
    python scripts/eval_humaneval.py --limit 20 --date 20261020
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
EXTERNAL = ROOT / ".codeguard" / "external"
DATA_URL = "https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz"
DATA_SHA256 = "b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef"
LICENSE_URL = "https://raw.githubusercontent.com/openai/human-eval/master/LICENSE"
LICENSE_SHA256 = "bcba3de214851cce46ed5af42d6698044616eeace887c3231bc7a20474ab639e"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, path: Path, expected: str):
    if path.exists() and sha256(path) == expected:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print("fetching %s" % url, flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "CodeGuard/eval"})
    with urllib.request.urlopen(request, timeout=60) as response:
        blob = response.read()
    actual = hashlib.sha256(blob).hexdigest()
    if actual != expected:
        raise SystemExit("SHA-256 mismatch for %s: %s != %s" % (url, actual, expected))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, path)


def build_manifest(limit: int) -> tuple[Path, int]:
    data_path = EXTERNAL / "HumanEval.jsonl.gz"
    fetch(DATA_URL, data_path, DATA_SHA256)
    fetch(LICENSE_URL, EXTERNAL / "LICENSE", LICENSE_SHA256)
    samples = [json.loads(line) for line in
               gzip.open(data_path, "rt", encoding="utf-8")]
    if limit:
        samples = samples[:limit]
    manifest = EXTERNAL / "humaneval-manifest.jsonl"
    with open(manifest, "w", encoding="utf-8") as fh:
        for sample in samples:
            code = sample["prompt"] + sample["canonical_solution"]
            fh.write(json.dumps({
                "id": sample["task_id"],
                "label": "clean",
                "language": "python",
                "license": "LicenseRef-Proprietary",
                "usage": "distribution",
                "code": code,
                "note": "HumanEval canonical solution; independent implementation, not a corpus member",
            }, ensure_ascii=False) + "\n")
    return manifest, len(samples)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--date", default="")
    parser.add_argument("--out-dir", default=str(ROOT / "submission" / "evidence"))
    args = parser.parse_args(argv)
    import datetime
    date = args.date or datetime.date.today().strftime("%Y%m%d")
    manifest, count = build_manifest(args.limit)
    stem = "humaneval-%s" % date + ("-limit%d" % args.limit if args.limit else "")
    tmp_out = EXTERNAL / ("eval-" + stem)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    cmd = [sys.executable, "-m", "codeguard", "eval",
           "--manifest", str(manifest), "--out", str(tmp_out),
           "--title", "HumanEval 独立实现干净负例（%d 例）" % count]
    code = subprocess.run(cmd, cwd=str(ROOT), env=env).returncode
    payload_path = tmp_out / "eval.json"
    if not payload_path.exists():
        raise SystemExit("evaluation did not produce %s (exit %d)" % (payload_path, code))
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["dataset"] = {
        "name": "OpenAI HumanEval",
        "version": "canonical solutions, master branch snapshot",
        "url": DATA_URL,
        "sha256": DATA_SHA256,
        "license": "MIT",
        "license_url": LICENSE_URL,
        "license_sha256": LICENSE_SHA256,
        "samples": count,
        "usage": "external clean negatives; not redistributed in this repository",
    }
    from codeguard.evaluate import to_markdown
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    final_json = out_dir / (stem + ".json")
    final_md = out_dir / (stem + ".md")
    final_json.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    final_md.write_text(to_markdown(payload, "HumanEval 独立实现干净负例（%d 例）" % count),
                        encoding="utf-8")
    s = payload["summary"]
    print("\n外部评测证据：%s" % final_json)
    print("干净样本：%d；阻断级误报：%d；任意命中：%d；95%% 单侧上限：%.2f%%"
          % (s["clean"], s["clean_blocking"], s["clean_any_finding"],
             100.0 * (s["clean_blocking_upper95"] or 0.0)))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
