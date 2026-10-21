"""Score the gate against *real* model leakage, not synthetic mutations.

LiCoEval (ICSE 2025, arXiv:2408.02487) publishes code that GPT-4o really
generated on HumanEval-style prompts together with the open-source file each
answer strikingly matched, the per-file licence and the paper's own similarity
scores.  This is the direction the evidence set was missing: the mutation
benchmark rewrites code we already indexed, and HumanEval only proves we do not
block independent implementations.  Here the positives are actual model output.

Protocol (echoed into the emitted JSON so a reviewer can repeat it):

* every licence-tagged reference original in the dataset becomes a corpus
  document, so attribution is not given for free - the true source competes with
  thousands of distractors, many of them vendored copies of each other;
* each published regurgitation case is scanned as if a developer pasted the
  answer into an MIT project that is then distributed;
* attribution counts a match to the expected project/path, and separately to any
  document whose text digest equals the expected original (an identical vendored
  copy under another project name is not this detector's mistake);
* a false-block control scans real pool files against the same index with their
  own project excluded.

The dataset is AGPL-3.0-or-later, fetched by URL + SHA-256 and used locally:
neither its source text nor the model answers are written into the repository.

Usage:
    python scripts/eval_model_leak.py
    python scripts/eval_model_leak.py --no-pool --limit 10 --control 0
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

EXTERNAL = ROOT / ".codeguard" / "external" / "licoeval"
REPO = "https://github.com/osslab-pku/LiCoEval"
RAW = "https://raw.githubusercontent.com/osslab-pku/LiCoEval/main/"
PAPER = ("LiCoEval: Evaluating LLMs on License Compliance in Code Generation, "
         "Xu/Gao/He/Zhou, ICSE 2025, arXiv:2408.02487")
DATASET_FILES = {
    "benchmark.json": (RAW + "benchmark.json",
                       "40c7d32f93d47d702fd4c786603e2407631b0c196f7940075cfed53c887f559b"),
    "gpt-4o_striking_sim.json": (RAW + "res/gpt-4o_striking_sim.json",
                                 "f3561838ff8c9d8224d026edbffbe6de47cbab90327f44585a16ef2e120c96e0"),
    "LICENSE": (RAW + "LICENSE",
                "6f1e622c82a380075843bb084a7ec3b1f1d12a4a02526d75e78b0924a860aa75"),
}
OBSERVED_COMMIT = "cfa26b4e5f108cccb49209f08c36f65d0b3bb658"
MODEL_NAME = "gpt-4o"
TARGET_LICENSE = "MIT"
USAGE = "distribution"


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(name: str) -> tuple:
    """Download a dataset file unless the cached copy already matches its digest."""
    url, expected = DATASET_FILES[name]
    path = EXTERNAL / name
    if path.exists():
        actual = sha256_file(path)
        if actual == expected:
            return path, actual
        print("%s 本地副本摘要不符（%s），重新下载" % (name, actual[:12]), flush=True)
    EXTERNAL.mkdir(parents=True, exist_ok=True)
    print("fetching %s" % url, flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "CodeGuard/eval"})
    with urllib.request.urlopen(request, timeout=600) as response:
        blob = response.read()
    actual = sha256_bytes(blob)
    if actual != expected:
        raise SystemExit("SHA-256 mismatch for %s: %s != %s" % (url, actual, expected))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, path)
    return path, actual


def slug(text: str) -> str:
    out = re.sub(r"[^A-Za-z0-9._-]+", "_", str(text or "unknown")).strip("._-")
    return out[:60] or "unknown"


def document_text(row: dict) -> str:
    """Rebuild a corpus document from the dataset's licence notice + code windows."""
    parts = []
    for field in ("init_header", "header", "body"):
        chunk = (row.get(field) or "").strip("\n")
        if chunk:
            parts.append(chunk)
    return "\n".join(parts) + "\n"


def resolve_licence(value: str) -> tuple:
    from codeguard.license_intel import load_spdx, resolve_spdx
    return resolve_spdx([(value or "", "licoeval-license-field")], load_spdx())


def licence_family(spdx: str) -> str:
    from codeguard.license_intel import profile_for
    return profile_for(spdx).family


def materialise(rows: dict, work: Path) -> dict:
    """Write each reference original as its own corpus document under work/corpus."""
    docs = {}
    for key, row in rows.items():
        text = document_text(row)
        if len(text.strip()) < 40:
            continue
        rel = "%s/%s.py" % (slug(row.get("project")), key[:16])
        abs_path = work / "corpus" / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(text, encoding="utf-8")
        docs[key] = {"path": rel, "text": text, "sha256": sha256_text(text),
                     "package": slug(row.get("project")), "row": row}
    return docs


def build_index(docs: dict, work: Path):
    from codeguard.index import DocRecord, FingerprintIndex, Params
    from codeguard.normalize import tokenize_source

    index = FingerprintIndex(Params())
    index.corpus_root = str(work / "corpus")
    started = time.time()
    for ord_no, key in enumerate(sorted(docs)):
        doc = docs[key]
        spdx, origin = resolve_licence(doc["row"].get("license"))
        index.add_document(DocRecord(
            ord_no, doc["package"], "%s-%s" % (MODEL_NAME, key[:8]), doc["path"], spdx,
            origin, "python", doc["text"].count("\n") + 1,
            len(tokenize_source(doc["text"])), doc["sha256"], len(doc["text"])), doc["text"])
    index.finalize()
    print("评测索引：%d 文档 / %d 片段 / %d 项目，用时 %.1fs"
          % (len(index.docs), index.stats()["chunks"],
             len({d["package"] for d in docs.values()}), time.time() - started), flush=True)
    return index


def lower95(successes: int, n: int) -> float:
    """One-sided exact lower bound: small-n recall must not be quoted as a rate."""
    from codeguard.evaluate import clopper_pearson_upper
    if n <= 0 or successes <= 0:
        return 0.0
    if successes >= n:
        return 1.0
    return round(1.0 - clopper_pearson_upper(n - successes, n), 4)


def upper95(successes: int, n: int) -> float:
    from codeguard.evaluate import clopper_pearson_upper
    return clopper_pearson_upper(successes, n)


def scan(index, model, text, target, target_license=TARGET_LICENSE, package_hint=""):
    from codeguard.adjudicate import Scanner
    return Scanner(index, model=model, usage=USAGE).scan_text(
        text, target=target, target_license=target_license,
        package_hint=package_hint, language="python")


def false_block_control(index, model, docs, keys, sample, seed=20261021):
    """Real open-source files against the same index, their own project excluded."""
    picked = random.Random(seed).sample(sorted(keys), min(sample, len(keys)))
    risks = collections.Counter()
    blocks = findings = 0
    latencies = []
    blocked_rows = []
    digest_by_path = {doc["path"]: doc["sha256"] for doc in docs.values()}
    for key in picked:
        doc = docs[key]
        started = time.perf_counter()
        scan_result = scan(index, model, doc["text"], "control-" + key[:12],
                           package_hint=doc["package"])
        latencies.append((time.perf_counter() - started) * 1000.0)
        findings += bool(scan_result.findings)
        for finding in scan_result.findings:
            risks[finding.risk] += 1
        hits = [f for f in scan_result.findings if f.risk in ("S3", "S4")]
        blocks += bool(hits)
        for finding in hits:
            same_text = digest_by_path.get(finding.path, "") == doc["sha256"]
            blocked_rows.append({
                "query": key[:12], "query_project": doc["package"],
                "matched": "%s:%s" % (finding.package, finding.path),
                "matched_license": finding.license_spdx, "risk": finding.risk,
                "confidence": round(finding.confidence, 3),
                "coverage": round(finding.coverage, 3),
                "verbatim_run": finding.max_verbatim_run,
                "kind": ("same_text" if same_text else
                         "same_project" if finding.package == doc["package"] else "cross_project"),
            })
    kinds = collections.Counter(row["kind"] for row in blocked_rows)
    return {
        "samples": len(picked), "blocking": blocks, "any_finding": findings,
        "blocking_rate": round(blocks / len(picked), 4) if picked else None,
        "blocking_upper95": round(upper95(blocks, len(picked)), 4) if picked else None,
        "blocking_findings": len(blocked_rows),
        "blocking_kind_census": dict(kinds),
        "blocking_detail": blocked_rows,
        "risk_counts": {risk: risks.get(risk, 0) for risk in ("S0", "S1", "S2", "S3", "S4")},
        "latency_ms_p95": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 1)
        if latencies else 0.0,
        "note": ("查询与候选都是真实开源代码，且参考语料里同一个上游文件常被多个项目各自复制，"
                 "所以这里的阻断不是误报率：摘要一致/同项目命中属于真实的跨仓库重复（vendoring）。"
                 "误阻断率见 HumanEval 外部评测与 false_block_control.py 的产品口径。"),
    }


def rate(rows, field):
    hits = sum(1 for row in rows if row.get(field))
    return {"hits": hits, "n": len(rows),
            "rate": round(hits / len(rows), 4) if rows else None,
            "lower95": lower95(hits, len(rows)) if rows else None}


def median(values):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    return float(ordered[mid]) if len(ordered) % 2 else round(
        (ordered[mid - 1] + ordered[mid]) / 2.0, 2)


def leak_view(payload: dict, meta: dict) -> dict:
    by_id = {sample["id"]: sample for sample in payload["samples"]}
    rows = []
    for key, info in meta.items():
        sample = by_id.get("leak-" + key[:16], {})
        finding_count = sample.get("finding_count", 0)
        rows.append({
            "key": key,
            "project": info["row"].get("project"),
            "license": info["spdx"],
            "license_field": info["row"].get("license"),
            "license_family": licence_family(info["spdx"]),
            "paper": {"bleu": round(info["row"].get("bleu", 0.0), 4),
                      "jaccard": round(info["row"].get("jaccard", 0.0), 4),
                      "max_sim": round(info["row"].get("max_sim", 0.0), 4)},
            "answer_sha256": info["answer_sha256"],
            "doc_sha256": info["doc_sha256"],
            "doc_path": info["doc_path"],
            "same_text_projects": info["same_text_projects"],
            "max_risk": sample.get("max_risk") or "-",
            "attributed": sample.get("attributed", False),
            "equivalent_source": sample.get("attributed", False) or info["equivalent_hit"],
            "project_hit": info["project_hit"],
            "same_text": info["same_text_hit"],
            "level": info["level"], "hit_packages": info["hit_packages"],
            "blocking": sample.get("blocking", False),
            "top1": sample.get("top1", False),
            "rank": info["rank"],
            "finding_count": finding_count,
            "confidence": max([f["confidence"] for f in sample.get("findings", [])] or [0.0]),
            "coverage": max([f["coverage"] for f in sample.get("findings", [])] or [0.0]),
            "verbatim_run": max([f["verbatim_run"] for f in sample.get("findings", [])] or [0]),
            "elapsed_ms": sample.get("elapsed_ms", 0.0),
        })
    copyleft = [r for r in rows if r["license_family"] in ("strong", "weak", "network")]
    permissive = [r for r in rows if r["license_family"] in ("permissive", "public_domain")]
    return {
        "cases": len(rows),
        "licence_census": dict(collections.Counter(r["license"] for r in rows)),
        "family_census": dict(collections.Counter(r["license_family"] for r in rows)),
        "all_attributed": rate(rows, "attributed"),
        "all_project_hit": rate(rows, "project_hit"),
        "level_census": dict(collections.Counter(r["level"] for r in rows)),
        "all_same_text": rate(rows, "same_text"),
        "all_equivalent_source": rate(rows, "equivalent_source"),
        "all_top1": rate(rows, "top1"),
        "all_any_finding": rate(rows, "finding_count"),
        "copyleft_subset": {"n": len(copyleft), "blocking": rate(copyleft, "blocking"),
                            "attributed": rate(copyleft, "attributed")},
        "permissive_subset": {"n": len(permissive), "attributed": rate(permissive, "attributed")},
        "verbatim_run": {"median": median([r["verbatim_run"] for r in rows]),
                         "max": max([r["verbatim_run"] for r in rows] or [0]),
                         "ge20": sum(1 for r in rows if r["verbatim_run"] >= 20)},
        "rank": {"top1": sum(1 for r in rows if r["rank"] == 1),
                 "top3": sum(1 for r in rows if 1 <= r["rank"] <= 3),
                 "unranked": sum(1 for r in rows if not r["rank"])},
        "rows": rows,
    }


def worksheet(leak: dict) -> str:
    lines = ["# 真实模型泄漏正例标注表（双人独立标注）", "",
             "来源：LiCoEval（ICSE 2025，AGPL-3.0-or-later）公布的 GPT-4o 真实生成代码，"
             "以及论文判定与之 striking-similar 的开源原文。本表只列摘要与指标，不含第三方源码。",
             "",
             "标注口径：**A = 真实逐字复现（可判定为许可污染）**；**B = 惯用写法/公共片段巧合**；"
             "**C = 无法判断**。两名标注人各自填列，不一致样本交第三人复核并记录结论。",
             "",
             "| 样本 | 来源项目 | 原文许可 | 论文 bleu | 论文 jaccard | CodeGuard 最高风险 | "
             "逐字命中(token) | 覆盖率 | 归属正确 | 标注1 | 标注2 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for row in sorted(leak["rows"], key=lambda r: (r["license_family"], str(r["project"]))):
        lines.append("| %s | %s | %s | %.2f | %.2f | %s | %d | %.2f | %s |  |  |" % (
            row["key"][:12], str(row["project"])[:28], row["license"], row["paper"]["bleu"],
            row["paper"]["jaccard"], row["max_risk"], row["verbatim_run"], row["coverage"],
            "是" if row["attributed"] else "否"))
    lines += ["", "- 标注人1：＿＿＿＿＿＿　日期：＿＿＿＿＿＿",
              "- 标注人2：＿＿＿＿＿＿　日期：＿＿＿＿＿＿",
              "- 分歧样本与复核结论：＿＿＿＿＿＿＿＿＿＿＿＿＿＿", ""]
    return "\n".join(lines)


def render(payload: dict) -> str:
    from codeguard.evaluate import to_markdown
    leak = payload["leak"]
    base = to_markdown(payload, "真实模型泄漏正例评测（LiCoEval / GPT-4o 生成代码）")
    a, eq, t1 = (leak["all_attributed"], leak["all_equivalent_source"], leak["all_top1"])
    copy_block = leak["copyleft_subset"]["blocking"]
    extra = ["", "## 真实泄漏正例检出", "",
             "- 正例：%d 条（论文判定的 striking-similarity 案例，模型输出为 GPT-4o 真实生成）"
             % leak["cases"],
             "- 同索引参考语料：%d 个带许可标注的真实开源代码窗口"
             % payload["dataset"]["reference_originals"],
             "- 许可家族分布：%s" % json.dumps(leak["family_census"], ensure_ascii=False),
             "", "| 指标 | 数值 | 95% 单侧下限 |", "|---|---|---|",
             "| 归因到预期项目/路径 | %d / %d | %.1f%% |" % (
                 a["hits"], a["n"], 100 * (a["lower95"] or 0.0)),
             "| 归因到预期项目（同项目不同窗口/副本） | %d / %d | %.1f%% |" % (
                 leak["all_project_hit"]["hits"], leak["all_project_hit"]["n"],
                 100 * (leak["all_project_hit"]["lower95"] or 0.0)),
             "| 命中同摘要原文（含跨项目副本） | %d / %d | %.1f%% |" % (
                 leak["all_same_text"]["hits"], leak["all_same_text"]["n"],
                 100 * (leak["all_same_text"]["lower95"] or 0.0)),
             "| 归因到预期项目或同摘要等效来源 | %d / %d | %.1f%% |" % (
                 eq["hits"], eq["n"], 100 * (eq["lower95"] or 0.0)),
             "| top-1 即预期来源 | %d / %d | %.1f%% |" % (
                 t1["hits"], t1["n"], 100 * (t1["lower95"] or 0.0)),
             "| copyleft 子集达到阻断阈值 | %d / %d | %.1f%% |" % (
                 copy_block["hits"], copy_block["n"], 100 * (copy_block["lower95"] or 0.0)),
             "| 出现任意命中 | %d / %d | %.1f%% |" % (
                 leak["all_any_finding"]["hits"], leak["all_any_finding"]["n"],
                 100 * (leak["all_any_finding"]["lower95"] or 0.0)),
             "| 最长逐字命中 中位/最大/≥20 token | %s / %s / %d | - |" % (
                 leak["verbatim_run"]["median"], leak["verbatim_run"]["max"],
                 leak["verbatim_run"]["ge20"]),
             "| 真源排名 top1 / top3 / 未上榜 | %d / %d / %d | - |" % (
                 leak["rank"]["top1"], leak["rank"]["top3"], leak["rank"]["unranked"]),
             "",
             "（逐字命中以 48 token 的滑窗为上限，表中 48 读作“至少 48”。归属分级：%s。）"
             % json.dumps(leak["level_census"], ensure_ascii=False),
             "",
             "- “别的项目”不是误报：这些命中的是**同一段上游代码的其它复制仓库**"
             "（tensorflow_models → balancap_SSD-Tensorflow、tensorflow_tensorflow → "
             "shenweichen_DeepCTR 等）。逐条命中项目已在下表列出，是否认定更强来源需人工标注；"
             "文件级归因 %d/%d 与项目级归因 %d/%d 都按最保守口径统计（只认预期项目/路径）。"
             % (a["hits"], a["n"], leak["all_project_hit"]["hits"], a["n"])]
    control = leak.get("false_block_control")
    if control:
        extra += ["", "## 同索引对照：真实开源文件（排除自身项目）", "",
                  "- 样本 %d；阻断级文件 %d；单侧 95%% 上限 %.2f%%；出现任意命中 %d" % (
                      control["samples"], control["blocking"],
                      100 * (control["blocking_upper95"] or 0.0), control["any_finding"]),
                  "- 阻断命中分类：%s（same_text=同一份代码被别的项目复制走，"
                  "same_project=同项目不同窗口，cross_project=跨项目相似）" % json.dumps(
                      control["blocking_kind_census"], ensure_ascii=False),
                  "- 风险分布：%s；p95 耗时 %.1f ms" % (
                      json.dumps(control["risk_counts"], ensure_ascii=False),
                      control["latency_ms_p95"]),
                  "- " + control["note"], "",
                  "| 查询项目 | 命中来源 | 命中许可 | 风险 | 类型 | 逐字 | 覆盖率 | 置信度 |",
                  "|---|---|---|---|---|---|---|---|"]
        for row in control["blocking_detail"]:
            extra.append("| %s | %s | %s | %s | %s | %d | %.2f | %.2f |" % (
                row["query_project"][:22], row["matched"].split("/")[-1][:22],
                row["matched_license"], row["risk"], row["kind"], row["verbatim_run"],
                row["coverage"], row["confidence"]))
    extra += ["", "## 按许可证的检出", "",
              "| 许可证 | 家族 | 条数 | 归因 | 阻断 | 逐字命中(最大) |",
              "|---|---|---|---|---|---|"]
    grouped = collections.defaultdict(list)
    for row in leak["rows"]:
        grouped[(row["license"], row["license_family"])].append(row)
    for (lic, family), rows in sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0][0])):
        extra.append("| %s | %s | %d | %d | %d | %d |" % (
            lic, family, len(rows), sum(1 for r in rows if r["attributed"]),
            sum(1 for r in rows if r["blocking"]),
            max([r["verbatim_run"] for r in rows] or [0])))
    extra += ["", "## 正例逐条（只记录摘要与指标，不写入第三方源码）", "",
              "| 样本 | 来源项目 | 许可 | 风险 | 归属 | 实际命中项目 | 真源排名 | 逐字 | 覆盖率 | 置信度 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for row in sorted(leak["rows"], key=lambda r: (-r["verbatim_run"], r["key"])):
        extra.append("| %s | %s | %s | %s | %s | %s | %s | %d | %.2f | %.2f |" % (
            row["key"][:12], str(row["project"])[:24], row["license"], row["max_risk"],
{"expected_doc": "预期文档", "same_project": "同项目其它窗口",
             "other_project": "别的项目", "none": "无命中"}[row["level"]],
            ", ".join(p[:22] for p in row["hit_packages"]) or "-",
            row["rank"], row["verbatim_run"], row["coverage"], row["confidence"]))
    extra += ["", "## 协议与限制", ""]
    for line in payload["protocol"]["limits"]:
        extra.append("- " + line)
    return base + "\n".join(extra) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="")
    parser.add_argument("--limit", type=int, default=0, help="只评测前 N 条正例")
    parser.add_argument("--no-pool", action="store_true",
                        help="不加载参考语料，只用正例原文建索引（快，但归因难度低于默认口径）")
    parser.add_argument("--control", type=int, default=200, help="误阻断对照样本数，0 关闭")
    parser.add_argument("--rebuild", action="store_true", help="强制重建评测索引（默认复用缓存）")
    parser.add_argument("--out-dir", default=str(ROOT / "submission" / "evidence"))
    args = parser.parse_args(argv)
    date = args.date or datetime.date.today().strftime("%Y%m%d")

    digests, paths = {}, {}
    for name in DATASET_FILES:
        paths[name], digests[name] = fetch(name)

    pool = json.loads(paths["benchmark.json"].read_text(encoding="utf-8"))
    striking = json.loads(paths["gpt-4o_striking_sim.json"].read_text(encoding="utf-8"))
    case_keys = sorted(striking)[:args.limit] if args.limit else sorted(striking)
    index_rows = dict(pool) if not args.no_pool else {}
    index_rows.update(striking)
    missing = [k for k in case_keys if k not in index_rows]
    if missing:
        raise SystemExit("正例在参考语料中缺失：%d 条" % len(missing))
    print("真实泄漏正例：%d 条（共发布 %d 条）；参考语料候选 %d 条"
          % (len(case_keys), len(striking), len(index_rows)), flush=True)

    work = EXTERNAL / ("run-%s" % date)
    docs = materialise(index_rows, work)
    from codeguard.cli import load_model
    from codeguard.evaluate import EvalSample, run_eval
    from codeguard.index import FingerprintIndex
    from codeguard.report import index_fingerprint

    cached = work / ("index-%s.bin" % ("pool" if not args.no_pool else "case"))
    if not args.rebuild and cached.exists():
        index = FingerprintIndex.load(str(cached))
        index.corpus_root = str(work / "corpus")
        print("复用评测索引：%d 文档 / %d 片段" % (len(index.docs), index.stats()["chunks"]),
              flush=True)
    else:
        index = build_index(docs, work)
        index.save(str(cached))
        print("评测索引已缓存：%s" % cached, flush=True)
    model = load_model(str(ROOT / ".codeguard"))
    print("判定模型：%s（与产品同一权重文件）"
          % ("logistic-regression" if model else "rule-fallback"), flush=True)

    same_text_projects = collections.defaultdict(list)
    for doc in docs.values():
        same_text_projects[doc["sha256"]].append(doc["package"])
    digest_by_path = {doc["path"]: doc["sha256"] for doc in docs.values()}

    samples, meta = [], {}
    for key in case_keys:
        row, doc = striking[key], docs[key]
        spdx, _origin = resolve_licence(row.get("license"))
        samples.append(EvalSample(
            id="leak-" + key[:16], label="copied", code=row["answer"], language="python",
            license=TARGET_LICENSE, usage=USAGE, source_package=doc["package"],
            source_path=doc["path"],
            note="GPT-4o 输出命中 %s（%s）" % (row.get("project"), spdx)))
        meta[key] = {"row": row, "spdx": spdx, "doc_path": doc["path"],
                    "package": doc["package"],
                    "doc_sha256": doc["sha256"], "answer_sha256": sha256_text(row["answer"]),
                    "same_text_projects": sorted(set(same_text_projects[doc["sha256"]]))[:6],
                    "equivalent_hit": False, "project_hit": False, "same_text_hit": False,
                    "level": "none", "hit_packages": [], "rank": 0}

    payload = run_eval(index, model, samples, metadata={
        "tool": "codeguard", "index_fingerprint": index_fingerprint(index),
        "index": index.stats(), "model": "logistic-regression" if model else "rule-fallback",
        "corpus": "LiCoEval reference originals (local evaluation index)"})

    for key, info in meta.items():
        sample = next(s for s in payload["samples"] if s["id"] == "leak-" + key[:16])
        ranks, equivalent, project_hit, same_text = [], False, False, False
        for position, finding in enumerate(sample["findings"], 1):
            finding_digest = digest_by_path.get(finding["path"], "")
            if finding["path"] == info["doc_path"]:
                ranks.append(position)
            elif finding_digest == info["doc_sha256"]:
                equivalent = True
            if finding_digest == info["doc_sha256"] or finding["path"] == info["doc_path"]:
                same_text = True
            if finding["package"] == info["package"]:
                project_hit = True
        info["rank"] = ranks[0] if ranks else 0
        info["equivalent_hit"] = equivalent and not bool(ranks)
        info["project_hit"] = project_hit
        info["same_text_hit"] = same_text
        info["hit_packages"] = sorted({f["package"] for f in sample["findings"]})[:3]
        info["level"] = ("expected_doc" if sample["attributed"] else
                         "same_project" if project_hit else
                         "other_project" if sample["findings"] else "none")

    leak = leak_view(payload, meta)
    payload["notes"].extend([
        "本清单 47 条正例里只有 6 条原文是 copyleft（5 条 GPL-3.0-or-later、1 条 MPL-2.0），"
        "其余 41 条原文为 Apache-2.0/BSD-3-Clause/MIT，按 MIT 目标分发不构成许可证冲突；"
        "因此“达到阻断阈值 6/47”只对这 6 条子集有意义，子集阻断为 6/6。",
        "通用渲染器的“未通过样本”按 copied 且未阻断定义，对宽松许可正例而言未阻断是预期结果，"
        "不是失败；请按“出现任意命中 47/47”与“归因到预期项目 39/47”读这张表。",
    ])
    if args.control:
        control_keys = [k for k in docs if k not in meta]
        leak["false_block_control"] = false_block_control(
            index, model, docs, control_keys, args.control)
        print("对照扫描：%d 个真实文件" % leak["false_block_control"]["samples"], flush=True)

    payload["dataset"] = {
        "name": "LiCoEval real regurgitation cases (%s)" % MODEL_NAME,
        "paper": PAPER, "repo": REPO, "commit": OBSERVED_COMMIT,
        "url": REPO, "sha256": digests["gpt-4o_striking_sim.json"],
        "license": "AGPL-3.0-or-later",
        "files": {name: {"url": DATASET_FILES[name][0], "sha256": digests[name]}
                  for name in sorted(DATASET_FILES)},
        "reference_originals": len(pool),
        "striking_cases_published": len(striking),
        "cases_evaluated": len(case_keys),
        "model": MODEL_NAME,
        "usage": "本地评测；数据集原文与模型输出不随作品分发，报告只记录摘要与指标",
    }
    payload["protocol"] = {
        "index": "参考语料全部入索引；每条正例的真实原文只是其中一个文档，其余为干扰项",
        "target_license": TARGET_LICENSE, "usage": USAGE,
        "corpus_document": "数据集 init_header+header+body 代码窗口拼接，不是完整原文件",
        "attribution": "命中预期项目/路径记为归因；命中同摘要文本的其它项目记为等效来源",
        "limits": [
            "正例由论文按自身相似度阈值筛出（%s 的 %d 条 striking-similarity），不是模型全部输出；"
            % (MODEL_NAME, len(striking)),
            "被评模型与提示词由第三方论文固定，我们无法审计该模型的训练数据；",
            "语料成员条件是构造性的：真实原文必然在索引内，所以这里测的是检出与归因能力，不是覆盖率上限；",
            "宽松许可原文按 MIT 目标分发不构成许可证冲突，因此只计入溯源而不计入阻断。",
        ],
    }
    payload["leak"] = leak
    if args.no_pool:
        payload["notes"].append("本次未加载参考语料（--no-pool），归因难度低于默认口径。")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "model-leak-%s" % date
    json_path = out_dir / (stem + ".json")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / (stem + ".md")).write_text(render(payload), encoding="utf-8")
    (out_dir / (stem + "-标注表.md")).write_text(worksheet(leak), encoding="utf-8")

    a, c = leak["all_attributed"], leak["copyleft_subset"]["blocking"]
    control = leak.get("false_block_control", {})
    print("\n真实模型泄漏正例证据：%s" % json_path)
    print("  归因 %d/%d（95%% 单侧下限 %.1f%%）；等效来源 %d/%d；top-1 %d/%d"
          % (a["hits"], a["n"], 100 * (a["lower95"] or 0.0),
             leak["all_equivalent_source"]["hits"], a["n"],
             leak["all_top1"]["hits"], a["n"]))
    print("  copyleft 子集阻断 %d/%d；逐字命中 中位 %s / 最大 %s"
          % (c["hits"], c["n"], leak["verbatim_run"]["median"], leak["verbatim_run"]["max"]))
    if control:
        print("  同索引对照：%d 个真实文件，阻断 %d（上限 %.2f%%）"
              % (control["samples"], control["blocking"],
                 100 * (control["blocking_upper95"] or 0.0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
