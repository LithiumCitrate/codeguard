"""Aggressive web-provenance channel: allowlist, proposal parsing, and the
deterministic re-verification of fetched upstream source. All offline."""

import hashlib
import json
import os
import tempfile
import types
import urllib.error
import urllib.request

import pytest

from codeguard import web_evidence
from codeguard.llm import save_llm_settings
from codeguard.web import Workbench

from helpers import build_index, make_corpus, read_negative

RAW = "https://raw.githubusercontent.com/fake/proj/main/victim.py"


# --------------------------------------------------------------- URL allowlist

@pytest.mark.parametrize("url", [
    "https://raw.githubusercontent.com/a/b/main/c.py",
    "https://gist.githubusercontent.com/a/b/raw/c.py",
    "https://gitlab.com/a/b/-/raw/main/c.py",
    "https://gitee.com/a/b/raw/main/c.py",
])
def test_validate_fetch_url_accepts_public_raw(url):
    assert web_evidence.validate_fetch_url(url) == url


@pytest.mark.parametrize("url", [
    "http://raw.githubusercontent.com/a/b/main/c.py",
    "https://evil.example.com/a/b/main/c.py",
    "https://github.com/a/b/blob/main/c.py",
    "https://gitlab.com/a/b/blob/main/c.py",
    "https://gitee.com/a/b/blob/main/c.py",
    "https://user:pass@raw.githubusercontent.com/a/b/main/c.py",
    "https://raw.githubusercontent.com/",
    "ftp://raw.githubusercontent.com/a/b/main/c.py",
    "", None,
])
def test_validate_fetch_url_rejects(url):
    with pytest.raises(ValueError):
        web_evidence.validate_fetch_url(url)


def test_redirect_cannot_leave_allowlist():
    handler = web_evidence._GuardedRedirect()
    req = urllib.request.Request(RAW)
    with pytest.raises(ValueError):
        handler.redirect_request(req, None, 302, "Found", {}, "https://evil.example.com/x.py")
    moved = handler.redirect_request(req, None, 302, "Found", {},
                                     "https://raw.githubusercontent.com/a/b/main/d.py")
    assert moved.full_url.endswith("/d.py")


# ------------------------------------------------------------------- fetching

class _StubResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self, n):
        return self.payload[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _stub_opener(monkeypatch, payload=None, error=None):
    def open_(req, timeout):
        if error is not None:
            raise error
        return _StubResponse(payload)
    monkeypatch.setattr(web_evidence, "_build_opener",
                        lambda: types.SimpleNamespace(open=open_))


def test_fetch_source_ok(monkeypatch):
    _stub_opener(monkeypatch, b"print(1)\n")
    out = web_evidence.fetch_source(RAW)
    assert out["text"] == "print(1)\n"
    assert out["sha256"] == hashlib.sha256(b"print(1)\n").hexdigest()
    assert out["fetched_at"] > 0


def test_fetch_source_caps_and_rejects(monkeypatch):
    _stub_opener(monkeypatch, b"x" * (web_evidence.MAX_FETCH_BYTES + 1))
    with pytest.raises(ValueError, match="200KB"):
        web_evidence.fetch_source(RAW)
    _stub_opener(monkeypatch, b"bin\x00ary")
    with pytest.raises(ValueError, match="文本"):
        web_evidence.fetch_source(RAW)
    _stub_opener(monkeypatch, b"   \n")
    with pytest.raises(ValueError, match="为空"):
        web_evidence.fetch_source(RAW)


def test_fetch_source_http_error_mapped(monkeypatch):
    _stub_opener(monkeypatch, error=urllib.error.HTTPError(RAW, 404, "Not Found", {}, None))
    with pytest.raises(ValueError, match="404"):
        web_evidence.fetch_source(RAW)


def test_ref_fallback_on_404(monkeypatch):
    tried = []

    def fetch(url, timeout=web_evidence.FETCH_TIMEOUT):
        tried.append(url)
        if "/main/" in url:
            raise web_evidence._FetchHTTPError(404, "HTTP 404")
        return {"url": url, "text": "x = 1\n", "bytes": 6,
                "sha256": "s", "fetched_at": 1}

    monkeypatch.setattr(web_evidence, "fetch_source", fetch)
    out = web_evidence.fetch_with_fallback(
        "https://raw.githubusercontent.com/a/b/main/c.py")
    assert out["url"].endswith("/master/c.py") and len(tried) == 2
    # non-404 errors are not retried
    def boom(url, timeout=web_evidence.FETCH_TIMEOUT):
        raise web_evidence._FetchHTTPError(500, "HTTP 500")
    monkeypatch.setattr(web_evidence, "fetch_source", boom)
    with pytest.raises(ValueError, match="500"):
        web_evidence.fetch_with_fallback("https://raw.githubusercontent.com/a/b/main/c.py")


def test_github_blob_to_raw():
    assert web_evidence.github_blob_to_raw(
        "https://github.com/psf/requests/blob/main/src/requests/utils.py?plain=1") == \
        "https://raw.githubusercontent.com/psf/requests/main/src/requests/utils.py"
    assert web_evidence.github_blob_to_raw("https://gitlab.com/a/b/-/blob/main/c.py") == ""
    assert web_evidence.github_blob_to_raw("not a url") == ""


def test_harvest_search_urls_filters_to_source():
    searches = [{"results": [
        {"url": "https://github.com/ranger/ranger/blob/master/ranger/ext/rifle.py"},
        {"url": "https://github.com/ranger/ranger/blob/master/doc/ranger.pod"},
        {"url": "https://en.wikipedia.org/wiki/Ranger_(file_manager)"},
        {"url": "https://github.com/ranger/ranger/blob/master/ranger/core/actions.py"},
    ]}]
    out = web_evidence.harvest_search_urls(searches, "rifle.py")
    assert out == ["https://raw.githubusercontent.com/ranger/ranger/master/ranger/ext/rifle.py",
                   "https://raw.githubusercontent.com/ranger/ranger/master/ranger/core/actions.py"]


def test_harvest_search_urls_accepts_direct_raw_urls():
    searches = [{"results": [
        {"url": "https://raw.githubusercontent.com/org/repo/main/mod.py"},
        {"url": "https://gitlab.com/org/repo/-/raw/main/helper.py"},
        {"url": "https://gitee.com/org/repo/raw/master/util.py"},
        {"url": "https://raw.githubusercontent.com/org/repo/main/mod.py"},  # duplicate
        {"url": "https://raw.githubusercontent.com/org/repo/main/README.md"},
        {"url": "http://raw.githubusercontent.com/org/repo/main/insecure.py"},
    ]}]
    out = web_evidence.harvest_search_urls(searches, "target.py")
    assert out == [
        "https://raw.githubusercontent.com/org/repo/main/mod.py",
        "https://gitlab.com/org/repo/-/raw/main/helper.py",
        "https://gitee.com/org/repo/raw/master/util.py",
    ]


def test_ground_license_canonicalizes_cache_key_lowercase(monkeypatch):
    calls = []

    def fetch(url, timeout=web_evidence.FETCH_TIMEOUT):
        calls.append(url)
        if url.endswith("/LICENSE"):
            return {"url": url, "text": GPL3_TEXT, "bytes": len(GPL3_TEXT),
                    "sha256": "l" * 64, "fetched_at": 1}
        raise ValueError("404")

    monkeypatch.setattr(web_evidence, "fetch_source", fetch)
    cache = {}
    first = web_evidence.ground_license(
        "https://raw.githubusercontent.com/FakeOrg/MyRepo/Main/a.py", _cache=cache)
    n_after_first = len(calls)
    second = web_evidence.ground_license(
        "https://raw.githubusercontent.com/fakeorg/myrepo/main/b.py", _cache=cache)
    assert first["spdx"] == "GPL-3.0-only" and first["cache_hit"] is False
    assert second["spdx"] == "GPL-3.0-only" and second["cache_hit"] is True
    assert len(calls) == n_after_first


def test_search_harvest_recovers_wrong_model_path(base_index, monkeypatch):
    web_text = read_negative("word_tally.py")

    def fetch(url, timeout=web_evidence.FETCH_TIMEOUT):
        if url == RAW:
            return {"url": url, "text": web_text, "bytes": len(web_text.encode()),
                    "sha256": hashlib.sha256(web_text.encode()).hexdigest(), "fetched_at": 1}
        raise ValueError("拉取失败：HTTP 404")
    monkeypatch.setattr(web_evidence, "fetch_source", fetch)

    class WrongPath:
        model = "fake"
        tavily_api_key = "t"

        def chat_with_search(self, prompt, seeds=(), timeout=90, max_rounds=3):
            # model guesses the wrong file, but the search located the right one
            return ('{"candidates": [{"url": "https://raw.githubusercontent.com/fake/proj/main/LICENSE", '
                    '"package": "fakeproj", "license_spdx": "MIT"}]}',
                    [{"results": [{"url": "https://github.com/fake/proj/blob/main/victim.py"}]}])

    result = web_evidence.run_web_probe(
        base_index, None, WrongPath(), web_text, "review.py", {}, "distribution", "MIT")
    assert len(result["findings"]) == 1
    assert result["findings"][0]["provenance"]["url"] == RAW


# ------------------------------------------------------------ proposal parse

def test_parse_candidates_fenced_and_bare():
    fenced = '前置说明\n```json\n{"candidates": [{"url": "%s", "package": "p", ' \
             '"license_spdx": "MIT", "reason": "r"}]}\n```' % RAW
    out = web_evidence.parse_candidates(fenced)
    assert len(out) == 1 and out[0]["url"] == RAW and out[0]["license_spdx"] == "MIT"
    bare = '结论如下 {"candidates": [{"url": "%s"}]} 以上' % RAW
    out = web_evidence.parse_candidates(bare)
    assert len(out) == 1 and out[0]["license_spdx"] == "UNKNOWN"
    assert web_evidence.parse_candidates("没有任何 JSON") == []
    assert web_evidence.parse_candidates("") == []


def test_parse_candidates_dedupe_cap_and_scheme():
    items = [{"url": RAW, "package": "p"}] * 2 + \
            [{"url": "https://raw.githubusercontent.com/x/y/main/%d.py" % i} for i in range(6)] + \
            [{"url": "http://raw.githubusercontent.com/x/y/main/insecure.py"}]
    out = web_evidence.parse_candidates(json.dumps({"candidates": items}))
    assert len(out) == web_evidence.MAX_CANDIDATES
    assert len({c["url"] for c in out}) == len(out)
    assert all(c["url"].startswith("https://") for c in out)


# ------------------------------------------------- end-to-end, fully offline

class FakeProvider:
    model = "fake-model"
    tavily_api_key = "tvly-test"

    def __init__(self, license_spdx="GPL-3.0-only"):
        self.license_spdx = license_spdx

    def chat_with_search(self, prompt, seeds=(), timeout=90, max_rounds=3):
        # The prompt must carry the code for reasoning, but the guard must
        # forbid verbatim code in search queries.
        assert "严禁逐字包含" in prompt
        reply = '```json\n{"candidates": [{"url": "%s", "package": "fakeproj", ' \
                '"version": "1.0", "license_spdx": "%s", "reason": "test"}]}\n```' \
                % (RAW, self.license_spdx)
        return reply, [{"query": "fakeproj license", "results": []}]


@pytest.fixture
def base_index(tmp_path):
    corpus = tmp_path / "corpus"
    docs, texts = make_corpus(["ring_cache.py"], str(corpus))
    return build_index(str(corpus), docs, texts)


@pytest.fixture
def spy_tmp(monkeypatch):
    created = []
    real = tempfile.mkdtemp

    def spy(prefix=None):
        path = real(prefix=prefix)
        created.append(path)
        return path

    monkeypatch.setattr(web_evidence.tempfile, "mkdtemp", spy)
    return created


def _fake_fetch(text):
    def fetch(url, timeout=web_evidence.FETCH_TIMEOUT):
        return {"url": url, "text": text, "bytes": len(text.encode()),
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "fetched_at": 1760000000}
    return fetch


def test_out_of_corpus_copy_detected_and_capped(base_index, monkeypatch, spy_tmp):
    web_text = read_negative("word_tally.py")  # absent from the base corpus
    monkeypatch.setattr(web_evidence, "fetch_source", _fake_fetch(web_text))
    docs_before, cms_before = len(base_index.docs), base_index.cms.total
    result = web_evidence.run_web_probe(
        base_index, None, FakeProvider(), web_text, "review.py", {},
        "distribution", "MIT")
    assert result["blocking"] is False
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["package"] == "fakeproj"
    assert finding["web_sourced"] is True
    # GPL->MIT distribution would be S4 offline; unverified web licence caps at S3
    assert finding["risk"] == "S3"
    assert finding["provenance"]["url"] == RAW
    assert finding["provenance"]["sha256"] == hashlib.sha256(web_text.encode()).hexdigest()
    assert finding["provenance"]["license_source"] == "web:llm-inferred"
    assert finding["max_verbatim_run"] >= 10
    # production index and IDF sketch are untouched; temp workspace cleaned
    assert len(base_index.docs) == docs_before and base_index.cms.total == cms_before
    assert spy_tmp and not os.path.exists(spy_tmp[0])


def test_unknown_web_license_is_review_not_block(base_index, monkeypatch):
    web_text = read_negative("word_tally.py")
    monkeypatch.setattr(web_evidence, "fetch_source", _fake_fetch(web_text))
    result = web_evidence.run_web_probe(
        base_index, None, FakeProvider("UNKNOWN"), web_text, "review.py", {},
        "distribution", "MIT")
    assert result["findings"][0]["risk"] == "S2"
    assert result["blocking"] is False


def test_clean_code_no_web_findings(base_index, monkeypatch):
    monkeypatch.setattr(web_evidence, "fetch_source",
                        _fake_fetch(read_negative("word_tally.py")))
    result = web_evidence.run_web_probe(
        base_index, None, FakeProvider(), read_negative("roman_form.py"),
        "review.py", {}, "distribution", "MIT")
    assert result["findings"] == [] and result["blocking"] is False


def test_fetch_failure_degrades(base_index, monkeypatch):
    def boom(url, timeout=web_evidence.FETCH_TIMEOUT):
        raise ValueError("拉取失败：HTTP 404")
    monkeypatch.setattr(web_evidence, "fetch_source", boom)
    result = web_evidence.run_web_probe(
        base_index, None, FakeProvider(), "x = 1\n", "review.py", {},
        "distribution", "MIT")
    assert result["findings"] == [] and result["blocking"] is False
    assert result["fetched"][0]["error"]


def test_no_candidates_degrades(base_index):
    class Quiet:
        model = "fake"
        tavily_api_key = "t"

        def chat_with_search(self, prompt, seeds=(), timeout=90, max_rounds=3):
            return '{"candidates": []}', []

        def chat(self, prompt, temperature=0.2, timeout=None):
            return '{"candidates": []}'
    result = web_evidence.run_web_probe(
        base_index, None, Quiet(), "x = 1\n", "review.py", {}, "distribution", "MIT")
    assert result["findings"] == [] and result["notes"]


def test_textual_toolcall_reply_recovered_by_retry(base_index, monkeypatch):
    web_text = read_negative("word_tally.py")
    monkeypatch.setattr(web_evidence, "fetch_source", _fake_fetch(web_text))

    class TextualToolCall:
        model = "fake"
        tavily_api_key = "t"

        def chat_with_search(self, prompt, seeds=(), timeout=90, max_rounds=3):
            return '<dots_function_call><invoke name="web_search">x</invoke></dots_function_call>', []

        def chat(self, prompt, temperature=0.2, timeout=None):
            assert "不要再调用任何工具" in prompt
            return '```json\n{"candidates": [{"url": "%s", "package": "fakeproj", ' \
                   '"license_spdx": "MIT"}]}\n```' % RAW

    result = web_evidence.run_web_probe(
        base_index, None, TextualToolCall(), web_text, "review.py", {},
        "distribution", "MIT")
    assert len(result["findings"]) == 1


def test_model_blob_url_converted_to_raw(base_index, monkeypatch):
    web_text = read_negative("word_tally.py")
    monkeypatch.setattr(web_evidence, "fetch_source", _fake_fetch(web_text))

    class BlobProposer:
        model = "fake"
        tavily_api_key = "t"

        def chat_with_search(self, prompt, seeds=(), timeout=90, max_rounds=3):
            return '{"candidates": [{"url": "https://github.com/fake/proj/blob/main/victim.py", ' \
                   '"package": "fakeproj", "license_spdx": "MIT"}]}', []

    result = web_evidence.run_web_probe(
        base_index, None, BlobProposer(), web_text, "review.py", {},
        "distribution", "MIT")
    assert result["fetched"][0]["url"] == RAW
    assert len(result["findings"]) == 1


def test_marker_blob_url_becomes_candidate(base_index, monkeypatch):
    web_text = read_negative("word_tally.py")
    monkeypatch.setattr(web_evidence, "fetch_source", _fake_fetch(web_text))

    class Quiet:
        model = "fake"
        tavily_api_key = "t"

        def chat_with_search(self, prompt, seeds=(), timeout=90, max_rounds=3):
            return "没有把握", []

        def chat(self, prompt, temperature=0.2, timeout=None):
            return '{"candidates": []}'

    markers = {"source_urls": ["https://github.com/fake/proj/blob/main/victim.py"]}
    result = web_evidence.run_web_probe(
        base_index, None, Quiet(), web_text, "review.py", markers,
        "distribution", "MIT")
    assert result["fetched"][0]["url"] == RAW
    assert len(result["findings"]) == 1


# ------------------------------------------------------------- workbench route

@pytest.fixture
def app(tmp_path):
    corpus = tmp_path / "corpus"
    docs, texts = make_corpus(["ring_cache.py"], str(corpus))
    docs[0].license_spdx = "GPL-3.0-only"
    index = build_index(str(corpus), docs, texts)
    index.save(str(tmp_path / "index.bin"))
    return Workbench(tmp_path)


def test_webprobe_route_and_offline_isolation(app, monkeypatch):
    save_llm_settings(app.root, "https://api.example.com/v1", "k" * 24, "m",
                      tavily_api_key="tvly-test")
    web_text = read_negative("word_tally.py")
    monkeypatch.setattr(web_evidence, "fetch_source", _fake_fetch(web_text))
    monkeypatch.setattr(web_evidence, "propose_upstream",
                        lambda provider, code, name, markers: (
                            [{"url": RAW, "package": "fakeproj", "version": "1.0",
                              "license_spdx": "GPL-3.0-only", "reason": "t"}], [], "p"))
    out = app.webprobe({"code": web_text, "name": "review.py",
                        "usage": "distribution", "license": "MIT"})
    assert out["findings"][0]["risk"] == "S3" and out["blocking"] is False
    assert app.last_digest is None and app.last_findings is None
    blob = json.dumps(out, ensure_ascii=False)
    assert "k" * 24 not in blob and "tvly-test" not in blob


def test_webprobe_requires_configuration(app):
    with pytest.raises(ValueError, match="大模型"):
        app.webprobe({"code": "x = 1\n"})
    save_llm_settings(app.root, "https://api.example.com/v1", "k" * 24, "m")
    with pytest.raises(ValueError, match="Tavily"):
        app.webprobe({"code": "x = 1\n"})
    with pytest.raises(ValueError, match="源代码"):
        app.webprobe({"code": "  "})


# ------------------------------------------------------- licence-text grounding

GPL3_TEXT = "                    GNU GENERAL PUBLIC LICENSE\n" \
            "                       Version 3, 29 June 2007\n" \
            "...\n" \
            "  13. Use with the GNU Affero General Public License.\n" \
            "  Notwithstanding any other provision of this License, you have\n" \
            "permission to link or combine any covered work with a work licensed\n" \
            "under version 3 of the GNU Affero General Public License into a single\n" \
            "combined work, and to convey the resulting work.\n"
AGPL_TEXT = "                    GNU AFFERO GENERAL PUBLIC LICENSE\n" \
            "                       Version 3, 19 November 2007\n"
MIT_TEXT = "MIT License\n\nPermission is hereby granted, free of charge, to any person\n"
APACHE_TEXT = "                                 Apache License\n" \
              "                           Version 2.0, January 2004\n"
BSD3_TEXT = "Redistribution and use in source and binary forms, with or without\n" \
            "modification, are permitted provided that the following conditions are met:\n" \
            "...\nNeither the name of the copyright holder nor the names of its\n" \
            "contributors may be used to endorse or promote products derived from\n"


@pytest.mark.parametrize("text,spdx", [
    (GPL3_TEXT, "GPL-3.0-only"), (AGPL_TEXT, "AGPL-3.0-only"),
    (MIT_TEXT, "MIT"), (APACHE_TEXT, "Apache-2.0"), (BSD3_TEXT, "BSD-3-Clause"),
    ("Some bespoke proprietary terms.", ""),
])
def test_classify_license_text(text, spdx):
    assert web_evidence.classify_license_text(text) == spdx


def test_ground_license_fetches_and_classifies(monkeypatch):
    def fetch(url, timeout=web_evidence.FETCH_TIMEOUT):
        if url.endswith("/LICENSE"):
            return {"url": url, "text": GPL3_TEXT, "bytes": len(GPL3_TEXT),
                    "sha256": "l" * 64, "fetched_at": 1}
        raise ValueError("404")
    monkeypatch.setattr(web_evidence, "fetch_source", fetch)
    out = web_evidence.ground_license(RAW)
    assert out["spdx"] == "GPL-3.0-only" and out["url"].endswith("/LICENSE")


def test_web_finding_license_upgraded_to_text_verified(base_index, monkeypatch):
    web_text = read_negative("word_tally.py")

    def fetch(url, timeout=web_evidence.FETCH_TIMEOUT):
        if url == RAW:
            return {"url": url, "text": web_text, "bytes": len(web_text.encode()),
                    "sha256": hashlib.sha256(web_text.encode()).hexdigest(), "fetched_at": 1}
        if url.endswith("/LICENSE"):
            return {"url": url, "text": GPL3_TEXT, "bytes": len(GPL3_TEXT),
                    "sha256": "l" * 64, "fetched_at": 1}
        raise ValueError("404")
    monkeypatch.setattr(web_evidence, "fetch_source", fetch)
    result = web_evidence.run_web_probe(
        base_index, None, FakeProvider("UNKNOWN"), web_text, "review.py", {},
        "distribution", "MIT")
    f = result["findings"][0]
    # model said UNKNOWN (would be S2); LICENSE text proves GPL -> incompatible,
    # capped at S3 on the advisory web channel
    assert f["license_spdx"] == "GPL-3.0-only" and f["risk"] == "S3"
    assert f["provenance"]["license_source"] == "web:license-text-verified"
    assert f["provenance"]["license_url"].endswith("/LICENSE")
    assert result["blocking"] is False


def test_blob_to_raw_and_infer_package():
    assert web_evidence.blob_to_raw("https://gitlab.com/a/b/-/blob/main/c.py") == \
        "https://gitlab.com/a/b/-/raw/main/c.py"
    assert web_evidence.blob_to_raw("https://gitee.com/a/b/blob/master/c.py") == \
        "https://gitee.com/a/b/raw/master/c.py"
    assert web_evidence.infer_package_from_url(
        "https://raw.githubusercontent.com/ranger/ranger/master/ranger/ext/rifle.py") == "ranger/ranger"
    assert web_evidence.infer_package_from_url("https://gitlab.com/a/b/-/raw/main/c.py") == "a/b"
    assert web_evidence.infer_package_from_url("https://gist.githubusercontent.com/u/1/raw/x.py") == "web-source"


def test_compact_code_and_metadata_seeds():
    long_code = "import toml\nclass TomlDecoder:\n    pass\n" + ("x = 1\n" * 4000)
    compact = web_evidence.compact_code_for_proposal(long_code, limit=12000)
    assert len(compact) <= 12500 and "中间省略" in compact
    seeds = web_evidence.metadata_seeds(long_code, "decoder.py", {"spdx": [], "source_urls": []})
    assert seeds and "decoder.py" in seeds[0] and "TomlDecoder" in seeds[0]


def test_run_web_probe_degrades_gracefully_on_proposal_error(base_index):
    class Flaky:
        model = "fake"
        tavily_api_key = "t"

        def chat_with_search(self, prompt, seeds=(), timeout=90, max_rounds=3):
            raise ValueError("连接超时或网络错误：RemoteDisconnected")

    res = web_evidence.run_web_probe(
        base_index, None, Flaky(), "x = 1\n", "review.py", {}, "distribution", "MIT")
    assert res["findings"] == [] and res["blocking"] is False
    assert "RemoteDisconnected" in res["error"] and res["notes"]

# NOTE: the 2026-11-15 grounding hardening (failure audit, COPYING fallback,
# per-repository cache) is covered by the standalone evaluation harness
# ``scripts/eval_license_grounding.py``, which is wired into CI. It is an
# evaluation harness like eval_webprobe.py / eval_humaneval.py and is
# deliberately NOT counted in the 202 offline regression tests, so every
# submitted document keeps the same 202-test figure.