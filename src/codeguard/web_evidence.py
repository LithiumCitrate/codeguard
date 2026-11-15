"""Web provenance probe: break the local-corpus coverage limit, deterministically.

The offline engine can only attest to what the shipped corpus covers. This
optional channel widens the search without weakening the gate:

1. the configured LLM (with Tavily search) proposes candidate upstream raw
   source URLs, reasoning from public metadata and functional descriptions —
   search queries never carry verbatim user code;
2. fetches are restricted to an allowlist of public https raw hosts, with a
   size cap, a timeout and guarded redirects;
3. fetched documents are indexed into a temporary in-memory FingerprintIndex
   that *shares the production Count-Min sketch*, so IDF weighting keeps its
   corpus semantics, and the whole deterministic pipeline runs unchanged:
   LSH retrieval, exact verification, judge, licence reasoning, corroboration;
4. web findings are advisory. The upstream licence is model-inferred and not
   corpus-verified, so this channel never blocks (risk capped at S3), never
   writes to the corpus or index, and never mutates the offline verdict.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from .adjudicate import Scanner, language_for
from .index import DocRecord, FingerprintIndex
from .license_intel import RISK_LABELS, analyze, risk_level
from .normalize import tokenize_source

MAX_FETCH_BYTES = 200_000
FETCH_TIMEOUT = 20
MAX_CANDIDATES = 4
RAW_HOSTS = ("raw.githubusercontent.com", "gist.githubusercontent.com")


def validate_fetch_url(url) -> str:
    """Only public https raw-source endpoints may be fetched."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("候选地址为空")
    url = url.strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":
        raise ValueError("仅允许 https 来源地址")
    if parts.username or parts.password:
        raise ValueError("来源地址不允许携带凭据")
    host = (parts.hostname or "").lower()
    path = parts.path or ""
    if host in RAW_HOSTS:
        pass
    elif host == "gitlab.com" and "/-/raw/" in path:
        pass
    elif host == "gitee.com" and "/raw/" in path:
        pass
    else:
        raise ValueError("仅允许拉取公开 raw 源码地址（GitHub/GitLab/Gitee）")
    if not path.strip("/"):
        raise ValueError("来源地址缺少文件路径")
    return url


class _GuardedRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect may not smuggle the fetch off the allowlist."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_fetch_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_opener():
    return urllib.request.build_opener(_GuardedRedirect)


class _FetchHTTPError(ValueError):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def fetch_source(url: str, timeout: int = FETCH_TIMEOUT) -> dict:
    checked = validate_fetch_url(url)
    request = urllib.request.Request(
        checked, headers={"User-Agent": "CodeGuard-WebProbe/1.0",
                          "Accept": "text/plain, */*"})
    try:
        with _build_opener().open(request, timeout=timeout) as resp:
            raw = resp.read(MAX_FETCH_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise _FetchHTTPError(exc.code, "拉取失败：HTTP %d（%s）" % (exc.code, checked)) from exc
    except urllib.error.URLError as exc:
        raise ValueError("拉取失败：无法连接 %s（%s）" % (checked, exc.reason)) from exc
    except (TimeoutError, OSError) as exc:
        raise ValueError("拉取超时或网络错误：%s" % checked) from exc
    if len(raw) > MAX_FETCH_BYTES:
        raise ValueError("来源文件超过 200KB 上限：%s" % checked)
    if b"\x00" in raw:
        raise ValueError("来源不是文本文件：%s" % checked)
    text = raw.decode("utf-8", errors="replace")
    if not text.strip():
        raise ValueError("来源文件为空：%s" % checked)
    return {"url": checked, "text": text, "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "fetched_at": int(time.time())}


_DEFAULT_REFS = ("master", "main", "develop")
_RAW_REF = re.compile(r"^(https://raw\.githubusercontent\.com/[^/]+/[^/]+/)([^/]+)(/.+)$")


def _ref_fallbacks(url: str):
    """Models guess the wrong default branch often; a 404 on one ref is worth
    retrying on the other common defaults. Bounded, and harmless to precision:
    any fetched text still has to pass exact verification to become a finding."""
    m = _RAW_REF.match(url)
    if not m:
        return
    prefix, ref, suffix = m.groups()
    for alt in _DEFAULT_REFS:
        if alt != ref:
            yield prefix + alt + suffix


def fetch_with_fallback(url: str, timeout: int = FETCH_TIMEOUT) -> dict:
    try:
        return fetch_source(url, timeout)
    except _FetchHTTPError as exc:
        if exc.code != 404:
            raise
    for alt in _ref_fallbacks(url):
        try:
            return fetch_source(alt, timeout)
        except ValueError:
            continue
    raise ValueError("拉取失败：HTTP 404（%s，已尝试常见默认分支）" % url)


# ------------------------------------------------- licence-text grounding

# Characteristic TITLE signatures, ordered so the more specific copyleft family
# wins (AGPL > LGPL > GPL) and BSD-3's extra clause beats BSD-2. Anchored to a
# line-start title immediately followed by its version: GPL-3.0 §13 *mentions*
# the Affero/Lesser licences mid-sentence, so an unanchored match would
# misread a plain GPL licence as AGPL/LGPL. Deterministic: same LICENSE text
# always yields the same SPDX id, or "" when unrecognised.
_LIC_SIGNATURES = (
    ("AGPL-3.0-only", r"^\s*gnu affero general public license[\s\S]{0,40}?version 3"),
    ("LGPL-3.0", r"^\s*gnu lesser general public license[\s\S]{0,40}?version 3"),
    ("LGPL-2.1", r"^\s*gnu (lesser|library) general public license[\s\S]{0,40}?version 2"),
    ("GPL-3.0-only", r"^\s*gnu general public license[\s\S]{0,40}?version 3"),
    ("GPL-2.0-only", r"^\s*gnu general public license[\s\S]{0,40}?version 2"),
    ("Apache-2.0", r"apache license[\s\S]{0,40}?version 2\.0"),
    ("MPL-2.0", r"mozilla public license[\s\S]{0,40}?version 2\.0"),
    ("Unlicense", r"this is free and unencumbered software released into the public domain"),
    ("MIT", r"permission is hereby granted, free of charge"),
    ("BSD-3-Clause", r"redistribution and use in source and binary forms[\s\S]{0,2000}?neither the name"),
    ("BSD-2-Clause", r"redistribution and use in source and binary forms"),
)
_LIC_NAMES = ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING")


def classify_license_text(text: str) -> str:
    low = (text or "").lower()
    for spdx, pattern in _LIC_SIGNATURES:
        if re.search(pattern, low, re.M):
            return spdx
    return ""


def ground_license(source_url: str, max_tries: int = 3) -> dict:
    """Fetch the upstream LICENSE and classify it deterministically, upgrading
    a model-inferred licence to a text-verified one. Bounded and graceful: any
    failure leaves the caller on the model-inferred licence."""
    m = _RAW_REF.match(source_url or "")
    if not m:
        return {}
    root = m.group(1) + m.group(2) + "/"
    for name in _LIC_NAMES[:max_tries]:
        try:
            src = fetch_source(root + name)
        except ValueError:
            continue
        spdx = classify_license_text(src["text"])
        if spdx:
            return {"spdx": spdx, "url": src["url"], "sha256": src["sha256"]}
    return {}


_GITHUB_BLOB = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$")
_CODE_EXTS = {".py", ".pyw", ".c", ".h", ".cpp", ".cc", ".hpp", ".go", ".rs",
              ".js", ".mjs", ".ts", ".jsx", ".tsx", ".java", ".rb", ".php"}


def github_blob_to_raw(url: str) -> str:
    """Deterministic assist: a github blob link in the code becomes a raw URL."""
    parts = urllib.parse.urlsplit(str(url).strip())
    m = _GITHUB_BLOB.match("https://%s%s" % (parts.netloc, parts.path))
    if not m or parts.netloc.lower() != "github.com":
        return ""
    owner, repo, ref, path = m.groups()
    return "https://raw.githubusercontent.com/%s/%s/%s/%s" % (owner, repo, ref, path)


def harvest_search_urls(searches, name: str) -> list:
    """The search often locates the exact upstream file even when the model's
    JSON candidate mis-guesses the path. Harvest raw-convertible source links
    from the already-fetched results (no extra API cost); verification still
    gates every one, so this only adds recall, never false positives."""
    ext = os.path.splitext(name)[1].lower()
    exts = {ext} if ext in _CODE_EXTS else _CODE_EXTS
    out = []
    for trace in searches or []:
        for result in trace.get("results", []):
            raw = github_blob_to_raw(result.get("url", ""))
            if raw and os.path.splitext(urllib.parse.urlsplit(raw).path)[1].lower() in exts:
                out.append(raw)
    return out


# --------------------------------------------------------------- proposal

_PROPOSE_PROMPT = (
    "你是代码溯源助手。下面这段代码可能是大模型从训练语料里“背”出来的开源代码，"
    "也可能包含开发者复制的第三方片段。请判断它最可能来自哪个开源项目的哪个文件：\n"
    "1) 先分析代码的功能、API 风格与注释线索；\n"
    "2) 用 web_search 核实候选项目的官方仓库、文件路径与许可证（查询词只能用项目名、"
    "API 名、功能关键词等公开元数据，严禁逐字包含下面的源代码）；\n"
    "3) 最后输出一个 JSON 代码块，格式固定：\n"
    '```json\n{"candidates": [{"url": "https://raw.githubusercontent.com/owner/repo/分支/路径.py", '
    '"package": "项目名", "version": "版本或分支", "license_spdx": "SPDX标识", "reason": "一句话依据"}]}\n```\n'
    "要求：url 必须是可直接下载的 raw 源码文件地址（raw.githubusercontent.com、"
    "gist.githubusercontent.com、gitlab.com 的 /-/raw/ 路径、gitee.com 的 /raw/ 路径），"
    "最多 %d 个，按可能性排序；license_spdx 必须来自检索到的证据，不确定就填 UNKNOWN；"
    "没有把握时输出 {\"candidates\": []}，不要编造地址。\n"
    "文件名：%s\n文件内确定性提取的标记（可信）：\n%s\n源代码：\n%s"
)


def parse_candidates(text: str) -> list:
    """Pull candidate objects out of the model reply, fenced or bare."""
    found = []
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", text or ""):
        try:
            obj, _ = decoder.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("candidates"), list):
            found.extend(obj["candidates"])
    out, seen = [], set()
    for item in found:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()[:500]
        if not url.startswith("https://") or url in seen:
            continue
        seen.add(url)
        out.append({"url": url,
                    "package": str(item.get("package", ""))[:80] or "web-source",
                    "version": str(item.get("version", ""))[:40] or "web",
                    "license_spdx": str(item.get("license_spdx", "")).strip()[:60] or "UNKNOWN",
                    "reason": str(item.get("reason", ""))[:300]})
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def propose_upstream(provider, code: str, name: str, markers: dict):
    prompt = _PROPOSE_PROMPT % (MAX_CANDIDATES, name,
                                json.dumps(markers, ensure_ascii=False)[:2000],
                                code[:30000])
    seeds = ["%s %s license" % (name, spdx) for spdx in (markers.get("spdx") or [])[:1]]
    seeds += (markers.get("source_urls") or [])[:1]
    text, searches = provider.chat_with_search(prompt, seeds, timeout=120, max_rounds=3)
    candidates = parse_candidates(text)
    if not candidates:
        # Some models end with a textual tool call instead of the JSON block;
        # one plain re-ask recovers the candidates without another search round.
        retry = ("你上一条回复没有给出可用的候选 JSON。请仅输出一个 JSON 代码块，格式：\n"
                 '```json\n{"candidates": [{"url": "raw 源码文件地址", "package": "项目名", '
                 '"version": "版本或分支", "license_spdx": "SPDX标识或UNKNOWN", "reason": "一句话依据"}]}\n```\n'
                 "不要再调用任何工具；无法确定时输出 {\"candidates\": []}。\n你上一条回复的结尾：\n"
                 + text[-1500:])
        try:
            text = provider.chat(retry, timeout=60)
            candidates = parse_candidates(text)
        except ValueError:
            pass
    for cand in candidates:
        raw = github_blob_to_raw(cand["url"])
        if raw:
            cand["url"] = raw
    known = {c["url"] for c in candidates}

    def add(url, reason):
        if url and url not in known and len(candidates) < MAX_CANDIDATES:
            known.add(url)
            candidates.append({"url": url, "package": "web-source", "version": "web",
                               "license_spdx": "UNKNOWN", "reason": reason})

    for url in (markers.get("source_urls") or []):
        add(github_blob_to_raw(url), "代码注释中出现的仓库链接（确定性转换）")
    for url in harvest_search_urls(searches, name):
        add(url, "检索结果中的源码链接（确定性转换）")
    return candidates, searches, text


# ------------------------------------------------------------ verification

def _lang_for_url(url: str) -> str:
    ext = os.path.splitext(urllib.parse.urlsplit(url).path)[1].lower()
    return {".py": "python", ".pyw": "python"}.get(ext, "generic")


def _safe_name(url: str, ordinal: int) -> str:
    base = os.path.basename(urllib.parse.urlsplit(url).path) or "source.txt"
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:80]
    return "web/%02d_%s" % (ordinal, base)


def verify_web_candidates(base_index, model, code: str, name: str, candidates: list,
                          usage: str, target_license: str) -> dict:
    """Run fetched web documents through the unchanged deterministic pipeline."""
    fetched = []
    tmp_root = tempfile.mkdtemp(prefix="cg-webprobe-")
    try:
        temp = FingerprintIndex(base_index.params)
        temp.corpus_root = tmp_root
        for ordinal, cand in enumerate(candidates[:MAX_CANDIDATES]):
            entry = dict(cand)
            try:
                source = fetch_with_fallback(cand["url"])
            except ValueError as exc:
                entry["error"] = str(exc)
                fetched.append(entry)
                continue
            entry["url"] = source["url"]  # record the ref that actually resolved
            lang = _lang_for_url(cand["url"])
            rel = _safe_name(cand["url"], ordinal)
            dest = os.path.join(tmp_root, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(source["text"])
            doc = DocRecord(len(temp.docs), cand["package"], cand["version"], rel,
                            cand["license_spdx"], "web:llm-inferred", lang,
                            source["text"].count("\n") + 1,
                            len(tokenize_source(source["text"])),
                            source["sha256"], source["bytes"])
            temp.add_document(doc, source["text"], lang)
            entry.update({"path": rel, "sha256": source["sha256"],
                          "bytes": source["bytes"], "fetched_at": source["fetched_at"]})
            fetched.append(entry)
        if not temp.docs:
            return {"findings": [], "fetched": fetched, "blocking": False,
                    "total_spans": 0, "matched_spans": 0, "timings": {},
                    "notes": ["候选上游全部拉取失败，未能完成联网验证；请检查网络或稍后重试。"]}
        # IDF must keep production semantics: web shingles are weighed against
        # the shipped corpus, not against the handful of fetched files.
        temp.cms = base_index.cms
        temp.finalize()
        result = Scanner(temp, model=model, usage=usage).scan_text(
            code, target=name, target_license=target_license,
            package_hint="", language=language_for(name))
        findings = []
        for finding in result.findings:
            item = finding.as_dict()
            # The upstream licence is model-inferred, not corpus-verified:
            # advisory only, never a build break on this channel.
            risk = "S3" if finding.risk == "S4" else finding.risk
            item["risk"] = risk
            item["risk_label"] = RISK_LABELS[risk]
            item["web_sourced"] = True
            prov = next((e for e in fetched if e.get("path") == finding.path), {})
            item["provenance"] = {"url": prov.get("url", ""),
                                  "sha256": prov.get("sha256", ""),
                                  "fetched_at": prov.get("fetched_at", 0),
                                  "license_source": "web:llm-inferred",
                                  "reason": prov.get("reason", "")}
            findings.append(item)
        # Upgrade model-inferred licences to text-verified ones where the upstream
        # LICENSE can be fetched and deterministically classified. Bounded to the
        # matched findings; failure leaves the advisory model-inferred licence.
        for item in findings:
            prov = item["provenance"]
            grounded = ground_license(prov["url"]) if prov.get("url") else {}
            if not grounded:
                continue
            verdict = analyze(grounded["spdx"], target_license, usage)
            risk = risk_level(verdict.status, item["confidence"], usage)
            risk = "S3" if risk == "S4" else risk
            item["license_spdx"] = grounded["spdx"]
            item["verdict"] = verdict.as_dict()
            item["risk"] = risk
            item["risk_label"] = RISK_LABELS[risk]
            prov["license_source"] = "web:license-text-verified"
            prov["license_spdx_verified"] = grounded["spdx"]
            prov["license_url"] = grounded["url"]
            prov["license_sha256"] = grounded["sha256"]
        notes = ["联网溯源为独立补充通道：候选上游由大模型联网推断，拉取原文后走与本地语料"
                 "完全相同的确定性验证（检索→精确验证→判定→义务推演→佐证门槛）。",
                 "命中后会尝试拉取上游 LICENSE 原文做确定性 SPDX 核验；核验成功的许可证标注"
                 "web:license-text-verified，失败则保留模型推断（web:llm-inferred）。",
                 "联网命中最高按 S3 提示，不直接阻断；请人工确认上游许可证后再决定处置。",
                 "本通道不修改本地语料、索引与离线审查结论。"]
        return {"findings": findings, "fetched": fetched, "blocking": False,
                "total_spans": result.total_spans, "matched_spans": result.matched_spans,
                "timings": result.timings, "notes": notes}
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def run_web_probe(base_index, model, provider, code: str, name: str, markers: dict,
                  usage: str, target_license: str) -> dict:
    t0 = time.time()
    candidates, searches, proposal = propose_upstream(provider, code, name, markers)
    if not candidates:
        return {"findings": [], "fetched": [], "searches": searches, "proposal": proposal,
                "model": provider.model, "blocking": False,
                "total_spans": 0, "matched_spans": 0, "timings": {},
                "notes": ["模型未能给出可核验的候选上游地址；未验证不代表没有来源，"
                          "可人工补充 raw 源码线索后重试。"],
                "elapsed_ms": int((time.time() - t0) * 1000)}
    verified = verify_web_candidates(base_index, model, code, name, candidates,
                                     usage, target_license)
    verified.update({"searches": searches, "proposal": proposal,
                     "model": provider.model,
                     "elapsed_ms": int((time.time() - t0) * 1000)})
    return verified