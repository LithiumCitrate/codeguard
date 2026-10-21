"""Command line interface: index, scan, gate, benchmark, licence reasoning.

Exit codes are part of the contract because ``gate`` is meant to run in CI:
0 = nothing blocking, 1 = blocking finding, 2 = usage/environment error.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import sys
import time

from . import __version__
from .adjudicate import Scanner, iter_sources
from .corpus import build_package, read_manifest, write_manifest
from .evaluate import load_manifest, run_eval, write_eval
from .index import DocRecord, FingerprintIndex, Params
from .license_intel import RISK_LABELS, analyze, normalize_expression, resolve_spdx
from .llm import DISCLOSURE, get_provider
from .normalize import tokenize_source
from .report import (index_fingerprint, provenance_receipt, to_cyclonedx, to_html,
                     to_sarif, write_outputs)
from .score import LogisticRegression

DEFAULT_PACKAGES = [
    "six", "iniconfig", "pyyaml", "tqdm", "requests", "urllib3", "click",
    "python-dotenv", "argparse", "snowballstemmer", "packaging", "pylint",
    "paramiko", "glances", "fava", "mpmath", "defusedxml", "legacy-cgi",
    "websockets",
]
WORKSPACE = ".codeguard"


def workspace(arg):
    root = os.path.abspath(arg or os.environ.get("CODEGUARD_HOME") or WORKSPACE)
    os.makedirs(root, exist_ok=True)
    return root


def _die(message: str, code: int = 2):
    """Usage/environment failures are code 2, never a bare string exit code."""
    print(message, file=sys.stderr)
    sys.exit(code)


def index_path(root):
    return os.path.join(root, "index.bin")


def model_path(root):
    return os.path.join(root, "model.json")


def corpus_root_of(root):
    path = os.path.join(root, "corpus")
    os.makedirs(path, exist_ok=True)
    return path


def load_index(root, required=True):
    path = index_path(root)
    if not os.path.exists(path):
        if required:
            _die("codeguard: 尚未建立索引，请先运行 `codeguard index`（退出码 2）")
        return None
    index = FingerprintIndex.load(path)
    adjacent = os.path.join(root, 'corpus')
    if os.path.isdir(adjacent):
        index.corpus_root = adjacent
    return index


def load_model(root):
    path = model_path(root)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return LogisticRegression.from_json(json.load(fh))
    return None


def check_corpus(index, allow_partial: bool = False) -> str:
    """Return a caveat note, or abort with exit code 2.

    "no findings" and "could not look" must never print the same way: a deleted
    corpus silently deletes every finding, because exact verification re-reads
    the original text.
    """
    total, readable = index.corpus_health()
    if total == 0 or readable == total:
        return ""
    if readable == 0:
        print("codeguard: 语料原文全部缺失（索引 %d 个文档，可读 0）。第二阶段的精确验证"
              "无法进行，此时的“未发现命中”是漏报而不是通过。请重新运行 `codeguard corpus`，"
              "或确认索引与语料在同一台机器的同一目录下。（退出码 2）" % total,
              file=sys.stderr)
        sys.exit(2)
    if not allow_partial:
        print("codeguard: 语料原文不完整（%d/%d 可读）。缺失的文档无法精确验证，会造成漏报。"
              "请重新运行 `codeguard corpus`，或显式加 --allow-partial-corpus "
              "接受不完整检查并把它记入报告。（退出码 2）" % (readable, total),
              file=sys.stderr)
        sys.exit(2)
    note = ("警告：语料原文不完整（%d/%d 可读），未读到的文档只能依赖草图估计，"
            "本报告的覆盖面受限。" % (readable, total))
    print("codeguard: %s" % note)
    return note


# --------------------------------------------------------------------- commands

def cmd_corpus(args):
    root = workspace(args.workspace)
    croot = corpus_root_of(root)
    names = DEFAULT_PACKAGES
    if args.packages:
        with open(args.packages, encoding="utf-8") as fh:
            names = [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    from codeguard.license_intel import load_spdx
    spdx = load_spdx()
    entries = []
    import concurrent.futures

    def work(name):
        try:
            return build_package(name, "", croot, spdx, max_files=args.max_files,
                                 log=lambda m: print(m, flush=True))
        except Exception as exc:
            print("FAIL %-16s %s: %s" % (name, type(exc).__name__, exc), flush=True)
            return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(work, names):
            entries.extend(result)
    manifest = os.path.join(croot, "corpus.json")
    write_manifest(entries, manifest, {"packages": names,
                                       "max_files_per_package": args.max_files})
    counts = {}
    for e in entries:
        counts[e.license_spdx] = counts.get(e.license_spdx, 0) + 1
    print("\n语料就绪：%d 个文件 / %d 个包" % (len(entries), len({e.package for e in entries})))
    for lic, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print("  %-20s %5d files" % (lic, n))
    print("manifest: %s" % manifest)


def cmd_index(args):
    root = workspace(args.workspace)
    croot = corpus_root_of(root)
    manifest = os.path.join(croot, "corpus.json")
    if not os.path.exists(manifest):
        _die("codeguard: 找不到语料清单，请先 `codeguard corpus`（退出码 2）")
    entries = read_manifest(manifest)
    index = FingerprintIndex(Params(window=args.window, stride=args.stride))
    index.corpus_root = croot
    ids = itertools.count()
    t0 = time.time()
    added = skipped = 0
    by_folder = {}
    for e in entries:
        by_folder.setdefault((e.package, e.version), []).append(e)
    for (package, version), group in by_folder.items():
        for e in group:
            path = os.path.join(croot, e.path.replace("/", os.sep))
            if not os.path.exists(path):
                skipped += 1
                continue
            text = open(path, encoding="utf-8", errors="replace").read()
            if len(text) < args.min_bytes:
                skipped += 1
                continue
            doc = DocRecord(next(ids), package, version, e.path, e.license_spdx,
                            e.license_source, e.language, text.count("\n") + 1,
                            len(tokenize_source(text)), e.sha256, len(text))
            index.add_document(doc, text)
            added += 1
    index.finalize()
    size = index.save(index_path(root))
    st = index.stats()
    print("索引完成：documents=%d chunks=%d packages=%d 用时 %.1fs 体积 %.1f KB"
          % (added, st["chunks"], st["packages"], time.time() - t0, size / 1024))
    print("跳过：%d" % skipped)
    print("许可证分布：%s" % ", ".join(st["licenses"]))
    print("索引文件：%s" % index_path(root))


def _scanner(index, args, usage):
    model = load_model(workspace(args.workspace))
    return Scanner(index, model=model, threshold=args.threshold,
                   usage=usage, top_verify=args.top_verify,
                   min_span_prob=args.min_span_prob,
                   corroborate_coverage=args.corroborate_coverage,
                   corroborate_verbatim=args.corroborate_verbatim,
                   corroborate_confidence=args.corroborate_confidence)


def cmd_scan(args):
    root = workspace(args.workspace)
    index = load_index(root)
    caveat = check_corpus(index, args.allow_partial_corpus)
    results = []
    targets = []
    for item in args.paths:
        targets.extend(iter_sources(item, tuple("." + e for e in args.ext.split(","))))
    if not targets:
        _die("codeguard: 没有匹配到待扫描文件（退出码 2）")
    scanner = _scanner(index, args, args.usage)
    provider = get_provider(args.explain)
    out_dir = args.out or os.path.join(root, "reports")
    total_findings = 0
    for path in targets:
        text = open(path, encoding="utf-8", errors="replace").read()
        scan = scanner.scan_text(strip_diff_markers(text), target=path.replace(os.sep, "/"),
                                 target_license=args.license,
                                 package_hint=os.path.basename(path).split(".")[0])
        if caveat:
            scan.notes.append(caveat)
        explanations = {f.key: provider.describe(f) for f in scan.findings}
        written = write_outputs(scan, index, out_dir, explanations,
                                tuple(args.format.split(",")))
        total_findings += len(scan.findings)
        print("%s: 片段 %d/%d 命中，来源 %d 个" % (path.replace(os.sep, "/"),
                                                  scan.matched_spans, scan.total_spans,
                                                  len(scan.findings)))
        for f in scan.findings[:args.max_show]:
            print("   [%s] %-14s %-18s conf=%.2f cov=%.2f %s"
                  % (f.risk, f.license_spdx, f.package, f.confidence, f.coverage,
                     f.path.split("/")[-1]))
        for p in written:
            print("   -> %s" % p.replace(os.sep, "/"))
        results.append(scan)
    print("\n合计命中来源 %d 个；输出目录 %s" % (total_findings, out_dir.replace(os.sep, "/")))
    if args.explain == "llm":
        print("说明：已启用外部大模型撰写处置建议；%s" % DISCLOSURE)


def strip_diff_markers(text: str) -> str:
    """Keep added lines from a unified diff, drop context markers."""
    if not text.startswith("@@") and "\n@@" not in text and "diff --git" not in text:
        return text
    out = []
    for line in text.splitlines():
        if line.startswith("@@") or line.startswith("diff ") or line.startswith("index ") \
                or line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            out.append(line[1:])
        elif line.startswith(" "):
            continue
        else:
            out.append(line)
    return "\n".join(out)


def read_diff_argument(value: str) -> str:
    """Accept a path, ``-`` for stdin, or an inline diff body."""
    if not value or value == "-":
        return sys.stdin.read()
    if os.path.exists(value):
        with open(value, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    return value


def cmd_gate(args):
    root = workspace(args.workspace)
    index = load_index(root)
    caveat = check_corpus(index, args.allow_partial_corpus)
    text = strip_diff_markers(read_diff_argument(args.diff))
    if not text.strip():
        print("codeguard gate: 没有新增代码可检查")
        return 0
    scanner = _scanner(index, args, args.usage)
    scan = scanner.scan_text(text, target=args.name or "diff",
                             target_license=args.license, package_hint="")
    if caveat:
        scan.notes.append(caveat)
    blocking = [f for f in scan.findings if f.risk in args.fail_on.split(",")]
    out_dir = args.out or os.path.join(root, "reports")
    provider = get_provider("offline")
    write_outputs(scan, index, out_dir,
                  {f.key: provider.describe(f) for f in scan.findings}, ("json", "html"))
    if args.sarif:
        parent = os.path.dirname(os.path.abspath(args.sarif))
        os.makedirs(parent, exist_ok=True)
        with open(args.sarif, "w", encoding="utf-8") as fh:
            json.dump(to_sarif(scan, index), fh, ensure_ascii=False, indent=1)
    if not scan.findings:
        print("CodeGuard: 未发现语料库来源的复用（检查 %d 个片段）" % scan.total_spans)
        return 0
    print("CodeGuard 合规门禁 · 目标 %s · 项目许可证 %s" % (scan.target, scan.target_license))
    for f in scan.findings:
        mark = "x" if f.risk in args.fail_on.split(",") else "!" if f.risk == "S2" else "-"
        print(" [%s] %-9s %-18s conf=%.2f  来源 %s@%s:%s" % (
            mark, f.risk, f.license_spdx, f.confidence, f.package, f.version,
            f.path.split("/")[-1]))
    print("\n共 %d 条来源，其中阻断级 %d 条；报告：%s"
          % (len(scan.findings), len(blocking), out_dir.replace(os.sep, "/")))
    for n in scan.notes:
        if "降级" in n:
            print(" " + n)
    if blocking:
        print("门禁失败：请替换实现、改用兼容许可证，或按 copyleft 条款公开源码。")
        return 1
    return 0


def cmd_licenses(args):
    src, sorigin = resolve_spdx([(args.source, "arg")])
    dst, dorigin = resolve_spdx([(args.target, "arg")])
    verdict = analyze(src, dst, args.usage)
    print("来源 %s (%s) -> 目标 %s (%s) 使用方式 %s" % (src, sorigin, dst, dorigin, args.usage))
    print("结论：%s" % verdict.status)
    for c in verdict.conflicts:
        print("  冲突：%s" % c)
    for o in verdict.obligations:
        print("  义务：%s" % o)
    for n in verdict.notes:
        print("  说明：%s" % n)
    risk = risk_for(verdict, 0.9, args.usage)
    print("  风险：%s %s" % (risk, RISK_LABELS[risk]))
    return 0 if verdict.status != "incompatible" else 1


def risk_for(verdict, confidence, usage):
    from .license_intel import risk_level
    return risk_level(verdict.status, confidence, usage)


def cmd_model(args):
    root = workspace(args.workspace)
    if args.show:
        path = model_path(root)
        if not os.path.exists(path):
            _die("codeguard: 模型不存在，请先运行 `codeguard benchmark --train`")
        print(open(path, encoding="utf-8").read())
        return
    _die("codeguard: 使用 `codeguard benchmark --train` 训练判定模型")


def cmd_doctor(args):
    root = workspace(args.workspace)
    index = load_index(root, required=False)
    print("codeguard %s · Python %s" % (__version__, sys.version.split()[0]))
    print("工作目录：%s" % root.replace(os.sep, "/"))
    if index is None:
        print("索引：未建立（运行 codeguard corpus && codeguard index）")
        return 0
    st = index.stats()
    print("索引：documents=%d chunks=%d packages=%d buckets=%d"
          % (st["documents"], st["chunks"], st["packages"], st["buckets"]))
    print("许可证：%s" % ", ".join(st["licenses"]))
    print("参数：window=%d stride=%d layers=%s"
          % (st["params"]["window"], st["params"]["stride"], st["params"]["active_layers"]))
    total, readable = index.corpus_health()
    print("语料原文：%d/%d 文档可读（%s）"
          % (readable, total, index.corpus_root or "未设置 corpus_root"))
    if readable < total:
        print("  注意：缺失的文档无法进行第二阶段精确验证，扫描会产生漏报；"
              "请重新运行 codeguard corpus")
    print("模型：%s" % ("已加载" if load_model(root) else "未训练（使用规则回退打分）"))
    print("AI 使用：%s" % DISCLOSURE)
    return 0


def cmd_benchmark(args):
    from .benchmark import run_benchmark
    root = workspace(args.workspace)
    run_benchmark(root, out=args.out, train=not args.no_train,
                  per_package=args.per_package, seed=args.seed,
                  mutations=args.mutations, files=args.files, chars=args.chars,
                  fp_sample=args.fp_study, min_chars=args.min_chars)


def cmd_eval(args):
    root = workspace(args.workspace)
    index = load_index(root)
    caveat = check_corpus(index, args.allow_partial_corpus)
    samples = load_manifest(args.manifest)
    if args.limit:
        samples = samples[:args.limit]
    model = load_model(root)
    model_sha = None
    if os.path.exists(model_path(root)):
        with open(model_path(root), "rb") as fh:
            model_sha = hashlib.sha256(fh.read()).hexdigest()
    metadata = {
        "tool": "codeguard",
        "version": __version__,
        "index_fingerprint": index_fingerprint(index),
        "index": index.stats(),
        "model": "logistic-regression" if model else "rule-fallback",
        "model_sha256": model_sha,
        "manifest": os.path.abspath(args.manifest).replace(os.sep, "/"),
    }
    payload = run_eval(
        index, model, samples, fail_on=tuple(x.strip() for x in args.fail_on.split(",") if x.strip()),
        min_span_prob=args.min_span_prob, top_verify=args.top_verify,
        corroborate_coverage=args.corroborate_coverage,
        corroborate_verbatim=args.corroborate_verbatim,
        corroborate_confidence=args.corroborate_confidence, metadata=metadata)
    if caveat:
        payload["notes"].append(caveat)
    out_dir = args.out or os.path.join(root, "eval")
    written = write_eval(payload, out_dir, title=args.title or "CodeGuard 外部评测")
    s = payload["summary"]
    print("CodeGuard 外部评测：%d 个样本（clean %d / copied %d）"
          % (s["samples"], s["clean"], s["copied"]))
    if s["clean"]:
        print("  干净样本阻断级误报：%d / %d（%.2f%%）；95%% 单侧上限 %.2f%%"
              % (s["clean_blocking"], s["clean"], 100.0 * s["clean_blocking_rate"],
                 100.0 * s["clean_blocking_upper95"]))
        print("  干净样本任意命中：%d；S2 及以上：%d"
              % (s["clean_any_finding"], s["clean_s2_or_higher"]))
    if s["copied"]:
        print("  复制样本归因：%d / %d（%.2f%%）；达到阻断阈值：%d / %d（%.2f%%）"
              % (s["copied_attributed"], s["copied"],
                 100.0 * (s["copied_attribution_rate"] or 0.0),
                 s["copied_detected"], s["copied"],
                 100.0 * (s["copied_detection_rate"] or 0.0)))
    print("  片段 %d/%d；p50 %.1f ms / p95 %.1f ms"
          % (s["matched_spans"], s["total_spans"],
             s["latency_ms"]["p50"], s["latency_ms"]["p95"]))
    for path in written:
        print("  -> %s" % path.replace(os.sep, "/"))
    failed = s["clean_blocking"] > 0
    if s["copied"] and s["copied_detection_rate"] is not None \
            and s["copied_detection_rate"] < args.min_detection:
        print("评测失败：复制样本检出率 %.2f%% 低于要求 %.2f%%"
              % (100.0 * s["copied_detection_rate"], 100.0 * args.min_detection))
        failed = True
    if failed:
        print("评测失败：存在干净样本被判定为阻断级风险。")
        return 1
    return 0


# ------------------------------------------------------------------------- main

def build_parser():
    ap = argparse.ArgumentParser(prog="codeguard",
                                 description="开源许可证污染溯源与合规门禁")
    ap.add_argument("--version", action="version", version="codeguard " + __version__)
    ap.add_argument("--workspace", default="", help="数据目录（默认 .codeguard）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("corpus", help="下载许可证多样的真实开源包作为语料")
    p.add_argument("--packages", default="")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--max-files", type=int, default=70)
    p.set_defaults(func=cmd_corpus)

    p = sub.add_parser("index", help="构建指纹索引（仅存哈希与定位信息）")
    p.add_argument("--window", type=int, default=48)
    p.add_argument("--stride", type=int, default=24)
    p.add_argument("--min-bytes", type=int, default=300)
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("scan", help="扫描文件或目录")
    p.add_argument("paths", nargs="+")
    p.add_argument("--license", default="MIT", help="被扫描项目的许可证 SPDX id")
    p.add_argument("--usage", default="inline_copy",
                   choices=["internal_use", "inline_copy", "static_link", "dynamic_link",
                            "tool_interface", "network_service", "distribution"])
    p.add_argument("--ext", default="py")
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--min-span-prob", type=float, default=0.55)
    p.add_argument("--top-verify", type=int, default=4)
    p.add_argument("--format", default="json,cdx,html")
    p.add_argument("--out", default="")
    p.add_argument("--explain", default="auto", choices=["auto", "offline", "llm"])
    p.add_argument("--allow-partial-corpus", action="store_true",
                   help="语料原文不全时仍继续（结论覆盖面受限，会写进报告）")
    p.add_argument("--max-show", type=int, default=5)
    p.add_argument("--corroborate-coverage", type=float, default=0.15,
                   help="阻断级发现所需的最低片段覆盖率（0 关闭佐证要求）")
    p.add_argument("--corroborate-verbatim", type=int, default=20,
                   help="阻断级发现所需的最低逐字 token 命中数")
    p.add_argument("--corroborate-confidence", type=float, default=0.75,
                   help="阻断级发现所需的最低文件级置信度")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("gate", help="CI 门禁：读取 diff，阻断级风险返回退出码 1")
    p.add_argument("--diff", default="", help="diff/源码路径，- 或省略表示 stdin")
    p.add_argument("--name", default="")
    p.add_argument("--license", default="MIT")
    p.add_argument("--usage", default="distribution")
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--min-span-prob", type=float, default=0.55)
    p.add_argument("--top-verify", type=int, default=4)
    p.add_argument("--fail-on", default="S3,S4")
    p.add_argument("--allow-partial-corpus", action="store_true",
                   help="语料原文不全时仍继续（会有漏报风险，写进报告）")
    p.add_argument("--corroborate-coverage", type=float, default=0.15,
                   help="阻断级发现所需的最低片段覆盖率（0 关闭佐证要求）")
    p.add_argument("--corroborate-verbatim", type=int, default=20,
                   help="阻断级发现所需的最低逐字 token 命中数")
    p.add_argument("--corroborate-confidence", type=float, default=0.75,
                   help="阻断级发现所需的最低文件级置信度")
    p.add_argument("--out", default="")
    p.add_argument("--sarif", default="", help="额外写出 SARIF 2.1.0 文件（GitHub Code Scanning）")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("licenses", help="仅做许可证兼容性推理")
    p.add_argument("source")
    p.add_argument("target")
    p.add_argument("--usage", default="distribution")
    p.set_defaults(func=cmd_licenses)

    p = sub.add_parser("model", help="查看判定模型")
    p.add_argument("--show", action="store_true")
    p.set_defaults(func=cmd_model)

    p = sub.add_parser("benchmark", help="变异基准与消融实验")
    p.add_argument("--out", default="")
    p.add_argument("--per-package", type=int, default=2)
    p.add_argument("--files", type=int, default=0, help="限定来源文件数（0=按 --per-package）")
    p.add_argument("--chars", type=int, default=5000, help="每个用例的字符上限")
    p.add_argument("--seed", type=int, default=20260101)
    p.add_argument("--mutations", default="")
    p.add_argument("--min-span-prob", type=float, default=None)
    p.add_argument("--min-chars", type=int, default=1500,
                   help="来源文件的最小字节数（小样本自检时可降低）")
    p.add_argument("--fp-study", type=int, default=0,
                   help="额外用生产索引抽查 N 个语料文件，统计跨包误报")
    p.add_argument("--no-train", action="store_true")
    p.set_defaults(func=cmd_benchmark)

    p = sub.add_parser("eval", help="用 JSONL 清单评测干净/复制样本（外部验证）")
    p.add_argument("--manifest", required=True, help="JSONL 清单；每行含 id/label/code 或 path")
    p.add_argument("--out", default="", help="输出目录（默认 .codeguard/eval）")
    p.add_argument("--title", default="", help="Markdown 标题")
    p.add_argument("--limit", type=int, default=0, help="只评测前 N 个样本")
    p.add_argument("--fail-on", default="S3,S4", help="视为阻断的风险等级")
    p.add_argument("--min-detection", type=float, default=0.0,
                   help="复制样本检出率下限（0 表示不设下限）")
    p.add_argument("--min-span-prob", type=float, default=0.55)
    p.add_argument("--top-verify", type=int, default=4)
    p.add_argument("--corroborate-coverage", type=float, default=0.15)
    p.add_argument("--corroborate-verbatim", type=int, default=20)
    p.add_argument("--corroborate-confidence", type=float, default=0.75)
    p.add_argument("--allow-partial-corpus", action="store_true")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("doctor", help="自检：索引、模型、参数、AI 使用声明")
    p.set_defaults(func=cmd_doctor)
    return ap


def main(argv=None):
    # Windows consoles still default to the local code page (cp936 on zh-CN),
    # which turns the Chinese report output into a UnicodeEncodeError mid-run.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    ap = build_parser()
    args = ap.parse_args(argv)
    # gate and licenses both signal through the exit code; the report commands
    # return None and are success by definition
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
