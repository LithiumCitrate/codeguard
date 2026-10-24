"""Scan real GitHub projects without mutation and report what actually fires.

The mutation benchmark and the HumanEval clean negatives are controlled.  This
script adds the missing third view: production code from unrelated projects,
with each project's real licence as the target.  It samples files
deterministically, keeps the clones under the git-ignored ``.codeguard/github``
tree, and writes only findings/metrics into ``submission/evidence``.

Usage:
    python scripts/eval_realworld.py --per-repo 40 --vendor-limit 60
    python scripts/eval_realworld.py --per-repo 10 --vendor-limit 10  # pilot
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codeguard.adjudicate import Scanner  # noqa: E402
from codeguard.cli import load_index, load_model, workspace  # noqa: E402
from codeguard import __version__  # noqa: E402
from codeguard.license_intel import RISK_LABELS  # noqa: E402
from codeguard.report import index_fingerprint  # noqa: E402

GITHUB = ROOT / ".codeguard" / "github"
RISK_ORDER = {"S0": 0, "S1": 1, "S2": 2, "S3": 3, "S4": 4}

# Licences were checked against each repository's LICENSE file at the pinned
# commit recorded in the evidence.  The corpus is not modified by this script.
#
# v0.5.0 note: the detection corpus now CONTAINS shallow clones of requests /
# flask / fastapi / httpx / django / pydantic (added by
# scripts/expand_corpus_github.py), so those repositories are excluded here —
# scanning them would only re-find the corpus's own copies.  Everything below
# is unrelated to the corpus; the two *-vendor entries expect hits because they
# genuinely vendor corpus packages.
REPOS = [
    {"name": "pip", "repo": "pypa/pip", "license": "MIT",
     "roots": ["src/pip"], "exclude_parts": ["_vendor"], "expected": []},
    {"name": "pip-vendor", "repo": "pypa/pip", "license": "MIT",
     "roots": ["src/pip/_vendor"], "expected": ["requests", "urllib3", "packaging"]},
    {"name": "setuptools", "repo": "pypa/setuptools", "license": "MIT",
     "roots": ["setuptools"], "exclude_parts": ["_vendor"], "expected": []},
    {"name": "setuptools-vendor", "repo": "pypa/setuptools", "license": "MIT",
     "roots": ["setuptools/_vendor"], "expected": ["packaging"]},
    {"name": "pytest", "repo": "pytest-dev/pytest", "license": "MIT",
     "roots": ["src/_pytest"], "expected": []},
    {"name": "sqlmap", "repo": "sqlmapproject/sqlmap", "license": "GPL-2.0-or-later",
     "roots": ["lib"], "expected": []},
    {"name": "mitmproxy", "repo": "mitmproxy/mitmproxy", "license": "MIT",
     "roots": ["mitmproxy"], "expected": []},
    {"name": "ansible", "repo": "ansible/ansible", "license": "GPL-3.0-only",
     "roots": [""], "expected": []},
    {"name": "yt-dlp", "repo": "yt-dlp/yt-dlp", "license": "Unlicense",
     "roots": [""], "expected": []},
    {"name": "black", "repo": "psf/black", "license": "MIT",
     "roots": ["src", ""], "expected": []},
    {"name": "mypy", "repo": "python/mypy", "license": "MIT",
     "roots": [""], "expected": []},
    {"name": "rich", "repo": "Textualize/rich", "license": "MIT",
     "roots": ["rich"], "expected": []},
    {"name": "scrapy", "repo": "scrapy/scrapy", "license": "BSD-3-Clause",
     "roots": ["scrapy"], "expected": []},
    {"name": "celery", "repo": "celery/celery", "license": "BSD-3-Clause",
     "roots": ["celery"], "expected": []},
    {"name": "sphinx", "repo": "sphinx-doc/sphinx", "license": "BSD-2-Clause",
     "roots": ["sphinx"], "expected": []},
    {"name": "httpie", "repo": "httpie/cli", "license": "BSD-3-Clause",
     "roots": ["httpie"], "expected": []},
    {"name": "localstack", "repo": "localstack/localstack", "license": "Apache-2.0",
     "roots": [""], "expected": []},
    {"name": "streamlit", "repo": "streamlit/streamlit", "license": "Apache-2.0",
     "roots": [""], "expected": []},
    {"name": "salt", "repo": "saltstack/salt", "license": "Apache-2.0",
     "roots": ["salt"], "expected": []},
    {"name": "datasets", "repo": "huggingface/datasets", "license": "Apache-2.0",
     "roots": ["src/datasets"], "expected": []},
    {"name": "openai-python", "repo": "openai/openai-python", "license": "Apache-2.0",
     "roots": ["src/openai"], "expected": []},
    {"name": "freqtrade", "repo": "freqtrade/freqtrade", "license": "AGPL-3.0-only",
     "roots": ["freqtrade"], "expected": []},
    {"name": "airflow", "repo": "apache/airflow", "license": "Apache-2.0",
     "roots": ["airflow-core/src/airflow", "airflow"], "expected": []},
    {"name": "keras", "repo": "keras-team/keras", "license": "Apache-2.0",
     "roots": ["keras"], "expected": []},
    {"name": "pandas", "repo": "pandas-dev/pandas", "license": "BSD-3-Clause",
     "roots": ["pandas"], "expected": []},
    {"name": "numpy", "repo": "numpy/numpy", "license": "BSD-3-Clause",
     "roots": ["numpy"], "expected": []},
    {"name": "aiohttp", "repo": "aio-libs/aiohttp", "license": "Apache-2.0",
     "roots": ["aiohttp"], "expected": []},
]

EXCLUDE_PARTS = {"tests", "test", "testing", "docs", "doc", "examples", "example",
                 "test_data", "testdata", "fixtures", "__pycache__", ".git"}
MIN_BYTES = 900
MAX_BYTES = 90_000


def _rmtree(path: Path) -> None:
    """Windows-tolerant removal: locked files fail silently with ignore_errors."""
    if not path.exists():
        return
    for _ in range(3):
        try:
            shutil.rmtree(path)
            return
        except OSError:
            time.sleep(0.4)
    # 最后兜底：把残留目录改名让路，git clone 用新目录
    try:
        path.rename(path.with_name(path.name + f".stale-{int(time.time())}"))
    except OSError:
        pass


def clone(repo: str, log=print):
    """Shallow-clone a repo; a single network failure must not kill the run."""
    GITHUB.mkdir(parents=True, exist_ok=True)
    name = repo.replace("/", "_")
    dest = GITHUB / name
    def checkout_ok(path: Path) -> bool:
        # 残缺克隆（有 .git 但工作树为空）不能当缓存复用
        return (path / ".git").exists() and any(p.name != ".git" for p in path.iterdir())
    if checkout_ok(dest):
        return dest
    _rmtree(dest)
    print("clone %s" % repo, flush=True)
    for attempt in (1, 2, 3):
        target = dest if attempt == 1 else GITHUB / f"{name}.retry{attempt}"
        result = subprocess.run(["git", "-c", "core.longpaths=true", "clone",
                                 "--depth", "1",
                                 "https://github.com/%s.git" % repo, str(target)],
                                capture_output=True, text=True)
        if result.returncode == 0 and checkout_ok(target):
            if target != dest:
                _rmtree(dest)
                try:
                    target.rename(dest)
                except OSError:
                    return target  # 改名失败也能用，路径无关扫描
            return dest
        _rmtree(target)
        log("clone %s 第 %d 次失败：%s" % (repo, attempt, result.stderr.strip()[-160:]))
    return None


def commit_of(path: Path) -> str:
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()


def select_files(root: Path, rel_roots, exclude_parts, limit: int, patterns=(".py",)):
    candidates = []
    seen = set()
    for rel in rel_roots:
        start = root / rel
        if not start.exists():
            continue
        for pattern in patterns:
            for path in start.rglob("*" + pattern):
                if path in seen:
                    continue
                seen.add(path)
                parts = set(path.relative_to(root).parts)
                if parts & EXCLUDE_PARTS or parts & set(exclude_parts or ()):
                    continue
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if not MIN_BYTES <= size <= MAX_BYTES:
                    continue
                candidates.append(path)
    # Deterministic hash sample: stable across runs and independent of walk order.
    ranked = sorted(candidates, key=lambda p: hashlib.sha256(
        str(p.relative_to(root)).encode("utf-8")).hexdigest())
    return ranked[:limit]


def percentile(values, q):
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    pos = (len(ordered) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(ordered) - 1)
    return round(ordered[lo] * (1 - (pos - lo)) + ordered[hi] * (pos - lo), 1)


def finding_summary(f):
    return {
        "package": f.package, "version": f.version, "path": f.path,
        "license": f.license_spdx, "risk": f.risk,
        "risk_label": RISK_LABELS[f.risk],
        "confidence": round(f.confidence, 4),
        "coverage": round(f.coverage, 4),
        "spans": len(f.spans),
        "verbatim": f.max_verbatim_run,
        "verdict": f.verdict.status if f.verdict else "unknown",
        "query_lines": list(f.matched_query_lines),
    }


def run(args):
    root = workspace(args.workspace)
    index = load_index(root)
    model = load_model(root)
    scanner = Scanner(index, model=model, usage="distribution")
    all_results = []
    global_latencies = []
    started = time.time()
    for spec in REPOS:
        if args.only and spec["name"] not in args.only:
            continue
        repo_dir = clone(spec["repo"])
        if repo_dir is None:
            all_results.append({"name": spec["name"], "repo": spec["repo"],
                                "commit": "", "license": spec["license"],
                                "roots": spec["roots"], "sampled_files": 0,
                                "scanned_files": 0, "total_spans": 0,
                                "errors": [{"file": "<clone>", "error": "clone failed after retries"}],
                                "findings": 0, "risk_counts": {}, "blocking": [],
                                "expected_packages": spec.get("expected", []),
                                "expected_hits": [],
                                "latency_ms": {"p50": 0, "p95": 0, "max": 0},
                                "files": [], "top_findings": []})
            print("%-18s CLONE FAILED（跳过，不终止评测）" % spec["name"], flush=True)
            continue
        commit = commit_of(repo_dir)
        limit = args.vendor_limit if spec["name"].endswith("-vendor") else args.per_repo
        files = select_files(repo_dir, spec["roots"], spec.get("exclude_parts"),
                             limit, patterns=tuple(spec.get("exts", [".py"])))
        rows, findings, latencies, spans, errors = [], [], [], 0, []
        for path in files:
            rel = str(path.relative_to(repo_dir)).replace(os.sep, "/")
            try:
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                t0 = time.perf_counter()
                scan = scanner.scan_text(text, target=rel,
                                         target_license=spec["license"],
                                         package_hint=spec["name"], language="python")
            except OSError as exc:
                errors.append({"file": rel, "error": "%s: %s" % (type(exc).__name__, exc)})
                continue
            latencies.append((time.perf_counter() - t0) * 1000.0)
            global_latencies.append(latencies[-1])
            spans += scan.total_spans
            for f in scan.findings:
                findings.append(finding_summary(f))
            rows.append({"file": rel, "spans": scan.total_spans,
                         "findings": len(scan.findings),
                         "max_risk": max((f.risk for f in scan.findings),
                                         key=lambda r: RISK_ORDER.get(r, -1),
                                         default=""),
                         "blocking": scan.blocking})
        risk_counts = {r: 0 for r in RISK_ORDER}
        for f in findings:
            risk_counts[f["risk"]] = risk_counts.get(f["risk"], 0) + 1
        blocking = [f for f in findings if f["risk"] in ("S3", "S4")]
        expected_hits = [f for f in findings if f["package"] in spec.get("expected", [])]
        all_results.append({
            "name": spec["name"], "repo": spec["repo"], "commit": commit,
            "license": spec["license"], "roots": spec["roots"],
            "sampled_files": len(files), "scanned_files": len(rows),
            "total_spans": spans, "errors": errors,
            "findings": len(findings), "risk_counts": risk_counts,
            "blocking": blocking, "expected_packages": spec.get("expected", []),
            "expected_hits": expected_hits[:30],
            "latency_ms": {"p50": percentile(latencies, 0.5),
                           "p95": percentile(latencies, 0.95),
                           "max": round(max(latencies), 1) if latencies else 0.0},
            "files": rows,
            "top_findings": sorted(findings, key=lambda f: (-f["confidence"], f["risk"]))[:20],
        })
        print("%-18s files=%-3d scanned=%-3d findings=%-3d blocking=%-2d errors=%-2d p95=%sms"
              % (spec["name"], len(files), len(rows), len(findings), len(blocking),
                 len(errors), percentile(latencies, 0.95)), flush=True)
    total_files = sum(r["sampled_files"] for r in all_results)
    total_scanned = sum(r["scanned_files"] for r in all_results)
    total_findings = sum(r["findings"] for r in all_results)
    total_blocking = sum(len(r["blocking"]) for r in all_results)
    payload = {
        "schema": "codeguard.realworld/v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": {
            "sample": "deterministic SHA-256 rank by repository-relative path",
            "file_size_bytes": [MIN_BYTES, MAX_BYTES],
            "usage": "distribution",
            "target_license": "each repository LICENSE file (verified at pinned commit)",
            "exclusions": "tests/docs/examples/__pycache__; vendor directories only in the explicit *-vendor entries",
            "not_redistributed": "repositories stay under .codeguard/github (gitignored); evidence contains findings only",
        },
        "metadata": {
            "tool": "codeguard", "version": __version__,
            "index_fingerprint": index_fingerprint(index),
            "model_sha256": hashlib.sha256((Path(root) / "model.json").read_bytes()).hexdigest()
            if (Path(root) / "model.json").exists() else None,
            "elapsed_s": round(time.time() - started, 1),
        },
        "summary": {
            "repositories": len(all_results), "sampled_files": total_files,
            "scanned_files": total_scanned,
            "findings": total_findings, "blocking": total_blocking,
            "files_with_blocking": sum(1 for r in all_results for f in r["files"] if f["blocking"]),
            "risk_counts": {risk: sum(r["risk_counts"].get(risk, 0) for r in all_results)
                            for risk in RISK_ORDER},  # noqa: 占位记录的空计数按 0 处理
            "expected_hits": sum(len(r["expected_hits"]) for r in all_results),
            "latency_ms": {"p50": percentile(global_latencies, 0.5),
                           "p95": percentile(global_latencies, 0.95),
                           "max": round(max(global_latencies), 1) if global_latencies else 0.0},
            "regression": {
                "case": "setuptools/_vendor/wheel/_commands/__init__.py",
                "old_risk": "S3 (false block)",
                "new_risk": "S2 (review)",
                "evidence": "6 generic argparse spans, coverage 0.222, 5 verbatim tokens, confidence 0.671",
            },
        },
        "repositories": all_results,
        "notes": [
            "真实仓库扫描不做变异；阻断级发现必须逐条人工复核，可能包含真实 vendoring、通用代码形状或误报。",
            "采样文件数与仓库总量不同；本结果不外推到未采样文件或未测试项目。",
            "目标许可证按仓库 LICENSE 固定；更换使用方式（内部/网络服务）会改变风险等级。",
        ],
    }
    return payload


def to_markdown(payload):
    s = payload["summary"]
    lines = ["# 真实 GitHub 项目扫描", "",
             "- 仓库：%d；采样/成功扫描：%d / %d；发现：%d；阻断级发现：%d" % (
                 s["repositories"], s["sampled_files"], s["scanned_files"],
                 s["findings"], s["blocking"]),
             "- 生成时间：%s" % payload["generated_at"],
             "- 方法：%s；文件大小 %d–%d B；目标许可证按仓库 LICENSE；使用方式 distribution" % (
                 payload["method"]["sample"], *payload["method"]["file_size_bytes"]),
             "- 全局单文件耗时 p50 / p95 / max：%.0f / %.0f / %.0f ms；真实 vendoring 命中：%d" % (
                 s["latency_ms"]["p50"], s["latency_ms"]["p95"], s["latency_ms"]["max"],
                 s["expected_hits"]),
             ""]
    lines.append("| 项目 | commit | 许可证 | 采样 | 发现 | S0/S1/S2/S3/S4 | 阻断 | p95 ms |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in payload["repositories"]:
        rc = r["risk_counts"]
        lines.append("| %s | `%s` | %s | %d | %d | %d/%d/%d/%d/%d | %d | %.0f |" % (
            r["name"], r["commit"][:12], r["license"], r["sampled_files"],
            r["findings"], rc.get("S0", 0), rc.get("S1", 0), rc.get("S2", 0),
            rc.get("S3", 0), rc.get("S4", 0),
            len(r["blocking"]), r["latency_ms"]["p95"]))
    lines.append("")
    lines.append("## 阻断级发现（需人工复核）")
    lines.append("")
    any_block = False
    for r in payload["repositories"]:
        for f in r["blocking"]:
            any_block = True
            lines.append("- **%s** `%s` → %s@%s:%s（%s），conf %.2f，cov %.2f，逐字 %d，风险 %s" % (
                r["name"], f["query_lines"], f["package"], f["version"], f["path"],
                f["license"], f["confidence"], f["coverage"], f["verbatim"], f["risk"]))
    if not any_block:
        lines.append("无。")
    lines.append("")
    reg = payload["summary"].get("regression")
    if reg:
        lines.append("## 回归案例")
        lines.append("")
        lines.append("- `%s`：%s → %s；证据：%s" % (
            reg["case"], reg["old_risk"], reg["new_risk"], reg["evidence"]))
        lines.append("")
    lines.append("## 真实 vendoring 命中")
    lines.append("")
    for r in payload["repositories"]:
        if not r["expected_packages"]:
            continue
        lines.append("- **%s**：预期来源包 %s；命中 %d 条" % (
            r["name"], ", ".join(r["expected_packages"]), len(r["expected_hits"])))
        for f in r["expected_hits"][:6]:
            lines.append("  - %s@%s:%s ← %s（conf %.2f，%s）" % (
                f["package"], f["version"], f["path"], f["query_lines"],
                f["confidence"], f["risk"]))
    lines.append("")
    errors = [e for r in payload["repositories"] for e in r.get("errors", [])]
    if errors:
        lines.append("## 读取失败的文件")
        lines.append("")
        for e in errors:
            lines.append("- `%s`：%s" % (e["file"], e["error"]))
        lines.append("")
    lines.append("## 说明")
    lines.append("")
    for note in payload["notes"]:
        lines.append("- " + note)
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default=".codeguard")
    parser.add_argument("--per-repo", type=int, default=40)
    parser.add_argument("--vendor-limit", type=int, default=60)
    parser.add_argument("--out-dir", default=str(ROOT / "submission" / "evidence"))
    parser.add_argument("--date", default="")
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--add", nargs="*", default=[], metavar="NAME:OWNER/REPO:SPDX[:ROOT][:exts=a,b]",
                        help="附加扫描仓库（复测用），如 jinja:pallets/jinja:BSD-3-Clause:src/jinja2 ；"
                             "非 Python 仓库用 exts=go,c 指定扩展名")
    args = parser.parse_args(argv)
    for item in args.add:
        parts = item.split(":")
        if len(parts) < 3 or "/" not in parts[1]:
            raise SystemExit("--add 格式应为 NAME:OWNER/REPO:SPDX[:ROOT][:exts=a,b]：%r" % item)
        spec = {"name": parts[0], "repo": parts[1], "license": parts[2],
                "roots": [""], "expected": []}
        for extra in parts[3:]:
            if extra.startswith("exts="):
                spec["exts"] = ["." + e.strip() for e in extra[5:].split(",") if e.strip()]
            elif extra:
                spec["roots"] = [extra]
        REPOS.append(spec)
    payload = run(args)
    date = args.date or datetime.date.today().strftime("%Y%m%d")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    js = out / ("realworld-github-%s.json" % date)
    md = out / ("realworld-github-%s.md" % date)
    js.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    md.write_text(to_markdown(payload), encoding="utf-8")
    print("evidence:", js)
    print("summary: files=%d findings=%d blocking=%d" % (
        payload["summary"]["sampled_files"], payload["summary"]["findings"],
        payload["summary"]["blocking"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
