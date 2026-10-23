"""Explanation layer: pluggable provider, deterministic by default.

The rules require an honest account of generative-AI use, so the design decision
is written into the code: the *default* provider is a deterministic template
renderer that works with no key, no network and no external service, and which
produces the same explanation for the same evidence every time. A
large-language-model provider is available behind an explicit opt-in, and when it
is used the disclosure string records which service was called.

v0.4.0 adds workspace-persisted settings (workbench "first run" setup), model
listing over the OpenAI-compatible ``/models`` endpoint, and four interpretation
tasks (file reading, scan summary, grounded Q&A, licence plain-language notes).
Every task degrades to a deterministic offline result, and the API key is only
ever written to the local workspace directory, never returned to the browser and
never embedded in reports.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from .license_intel import RISK_LABELS

DISCLOSURE = (
    "CodeGuard 默认使用确定性模板生成器产出合规说明，全程离线、无外部模型调用、"
    "结果可逐字节复现；仅当显式配置大模型接口（环境变量 CODEGUARD_LLM_BASE_URL/"
    "CODEGUARD_LLM_API_KEY，或工作台首次运行时的本机配置，密钥仅保存在本机）时才会调用"
    "第三方大模型，且仅用于生成解读文字，风险结论始终由确定性算法给出；调用情况会被"
    "写入报告的 ai_usage 字段以供审计。")

# ---------------------------------------------------------------- settings I/O

SETTINGS_NAME = "llm_config.json"
_KEY_LIMIT = 500


def validate_base_url(raw) -> str:
    if not isinstance(raw, str):
        raise ValueError("Base URL 必须是字符串")
    url = raw.strip().rstrip("/")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
    if len(url) > 500 or not re.match(r"^https?://[A-Za-z0-9.\-:_\[\]]+", url):
        raise ValueError("Base URL 格式无效")
    return url


def mask_key(key: str) -> str:
    if len(key) <= 10:
        return "*" * len(key)
    return key[:5] + "*" * 6 + key[-4:]


def load_llm_settings(root) -> dict | None:
    path = os.path.join(str(root), SETTINGS_NAME)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    base, key, model = data.get("base_url", ""), data.get("api_key", ""), data.get("model", "")
    if not isinstance(base, str) or not isinstance(key, str) or not isinstance(model, str):
        return None
    if not base or not key or not model:
        return None
    return {"base_url": base, "api_key": key, "model": model}


def save_llm_settings(root, base_url, api_key, model) -> dict:
    base = validate_base_url(base_url)
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("API Key 不能为空")
    api_key = api_key.strip()
    if len(api_key) > _KEY_LIMIT:
        raise ValueError("API Key 过长")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("请先选择模型")
    model = model.strip()
    if len(model) > 200:
        raise ValueError("模型名过长")
    payload = {"base_url": base, "api_key": api_key, "model": model}
    path = os.path.join(str(root), SETTINGS_NAME)
    # 同目录先写临时文件再原子替换，避免并发写坏配置；权限尽力收紧到仅属主可读。
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    return payload


def clear_llm_settings(root) -> bool:
    path = os.path.join(str(root), SETTINGS_NAME)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def provider_from_settings(root):
    """Workspace settings first (workbench), then the environment (CLI)."""
    data = load_llm_settings(root)
    if data:
        return OpenAICompatProvider(data["base_url"], data["api_key"], data["model"])
    return OpenAICompatProvider.from_env()


def _http_json(request, timeout):
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        if exc.code in (401, 403):
            detail = "（API Key 无效或无权限）"
        raise ValueError("接口返回 HTTP %d%s" % (exc.code, detail)) from exc
    except urllib.error.URLError as exc:
        raise ValueError("无法连接接口地址：%s" % exc.reason) from exc
    except (TimeoutError, OSError) as exc:
        raise ValueError("连接超时或网络错误：%s" % exc) from exc
    except ValueError:
        raise ValueError("接口返回的不是有效 JSON")


def list_models(base_url, api_key, timeout: int = 20) -> list:
    """Fetch the OpenAI-compatible /models listing; never stores anything."""
    base = validate_base_url(base_url)
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("API Key 不能为空")
    request = urllib.request.Request(base + "/models",
                                     headers={"Authorization": "Bearer " + api_key.strip()})
    data = _http_json(request, timeout)
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("接口未返回模型列表（data 字段缺失）")
    models = sorted({str(item.get("id")) for item in items
                     if isinstance(item, dict) and item.get("id")})
    if not models:
        raise ValueError("模型列表为空")
    return models


# ------------------------------------------------- deterministic licence markers

_LICENSE_WORDS = re.compile(
    r"\b(GPL-[0-9.]+(?:-only|-or-later)?|AGPL-[0-9.]+(?:-only|-or-later)?|LGPL-[0-9.]+"
    r"|Apache-[0-9.]+|MIT(?:/X11)?|BSD-[234]-Clause|MPL-[0-9.]+|CDDL|EPL-[0-9.]+|Unlicense|CC0-[0-9.]+)\b")
_COPYRIGHT = re.compile(r"(copyright|\(c\)|©|版权所有|著作权)", re.IGNORECASE)
_VENDORED = re.compile(r"(vendored|copied from|adapted from|based on|ported from|"
                       r"taken from|modified from|复制自|改编自|摘自|来源[::]|参考[::])",
                       re.IGNORECASE)
_SOURCE_URL = re.compile(r"https?://(?:[\w.-]+\.)?(?:github\.com|gitlab\.com|bitbucket\.org|"
                         r"pypi\.org|gitee\.com|apache\.org|gnu\.org)/\S+")


def extract_license_markers(code: str) -> dict:
    """Deterministic, offline signal extraction that complements fingerprint search.

    Fingerprints answer "which corpus document does this resemble"; markers
    answer "what does the file itself declare". Same input, same output.
    """
    head = "\n".join(code.splitlines()[:60])
    spdx = sorted(set(re.findall(r"SPDX-License-Identifier:\s*([^\r\n*]+)", code)))
    licenses = sorted(set(_LICENSE_WORDS.findall(code)))[:12]
    copyright_lines = [line.strip()[:160] for line in code.splitlines()
                       if _COPYRIGHT.search(line)][:8]
    vendored = [line.strip()[:160] for line in code.splitlines()
                if _VENDORED.search(line)][:8]
    urls = sorted(set(_SOURCE_URL.findall(code)))[:8]
    lines = []
    if spdx:
        lines.append("文件内声明了 SPDX 许可证标识：" + "、".join(spdx))
    if licenses:
        lines.append("出现许可证名称：" + "、".join(licenses))
    if copyright_lines:
        lines.append("包含版权声明行 %d 处，例如：%s" % (len(copyright_lines), copyright_lines[0]))
    if vendored:
        lines.append("注释中出现来源/改写提示 %d 处，例如：%s" % (len(vendored), vendored[0]))
    if urls:
        lines.append("包含源码仓库链接：" + "、".join(urls[:3]))
    if not lines:
        lines.append("未在注释或声明中发现显式许可证标记；这不代表没有第三方来源，请结合指纹审查结果判断。")
    return {"spdx": spdx, "licenses": licenses, "copyright_lines": copyright_lines,
            "vendored_hints": vendored, "source_urls": urls, "summary": "\n".join(lines)}



class OfflineTemplateProvider:
    name = "offline-template"
    external = False

    def describe(self, finding) -> str:
        v = finding.verdict
        lines = []
        lines.append("目标 %s 中 %d 个代码片段命中语料库来源 %s@%s 的 %s（第 %d-%d 行），"
                     "单片段最长逐字连续命中 %d 个代码 token。"
                     % (finding.target, len(finding.spans), finding.package,
                        finding.version, finding.path, finding.matched_query_lines[0],
                        finding.matched_query_lines[1], finding.max_verbatim_run))
        lines.append("许可证判定：%s → 目标 %s 的使用方式为 %s，结论 %s。"
                     % (finding.license_spdx, v.target_spdx, v.usage, v.status))
        for reason in v.conflicts:
            lines.append("冲突依据：" + reason)
        for note in v.notes:
            lines.append("说明：" + note)
        if v.obligations:
            lines.append("需履行的义务：" + "；".join(v.obligations))
        lines.append("风险等级 %s（%s）。" % (finding.risk, RISK_LABELS[finding.risk]))
        lines.append("处置建议：" + self._advice(finding))
        return "\n".join(lines)

    @staticmethod
    def _advice(finding) -> str:
        status = finding.verdict.status
        if status == "incompatible":
            return ("停止以当前方式集成该代码；改为 (1) 用自研实现替换，(2) 寻找同等功能的"
                    "宽松许可替代实现，或 (3) 将本项目整体改为满足 %s 条款的许可证并公开源码。"
                    % finding.license_spdx)
        if status == "conditional":
            return ("可以合并，但必须履行条件义务：保留声明、标注修改、为受 copyleft 覆盖的文件"
                    "提供源码形式，并在 LICENSE/NOTICE 中登记该来源。")
        if status == "unknown":
            return "来源许可证未能确定：先补齐 SPDX 标识或联系上游确认，禁止在未确认前合并。"
        return "保留版权声明与许可证文本即可合并，建议在 NOTICE 中登记来源与版本。"


class OpenAICompatProvider:
    """Opt-in LLM writer; only rewrites the prose, never the evidence."""

    name = "openai-compatible"
    external = True

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @classmethod
    def from_env(cls):
        base = os.environ.get("CODEGUARD_LLM_BASE_URL", "")
        key = os.environ.get("CODEGUARD_LLM_API_KEY", "")
        if not base or not key:
            return None
        return cls(base, key, os.environ.get("CODEGUARD_LLM_MODEL", "gpt-4o-mini"))

    def chat(self, prompt: str, temperature: float = 0.2, timeout: int | None = None) -> str:
        payload = {"model": self.model,
                   "messages": [{"role": "user", "content": prompt}],
                   "temperature": temperature}
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + self.api_key})
        data = _http_json(req, timeout or self.timeout)
        try:
            return str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("接口响应缺少 choices 内容") from exc

    _PROMPT = (
        "你是开源合规助手。仅依据给定证据撰写一段面向开发者的中文处置建议，"
        "不得新增证据之外的法律结论，不得声称这是法律意见。证据：{}")

    def describe(self, finding) -> str:
        try:
            return self.chat(self._PROMPT.format(json.dumps(
                finding.as_dict(), ensure_ascii=False)[:6000]))
        except Exception as exc:  # never fail a scan because prose failed
            return OfflineTemplateProvider().describe(finding) + \
                "\n（LLM 调用失败，已回退到离线模板：%s）" % exc

    # -------------------------------------------------- v0.4 interpretation tasks

    _GUARD = ("要求：只依据给定材料回答，不得编造证据或行号；风险与许可结论以"
              "CodeGuard 确定性引擎给出的为准，你只做解读；不得提供法律意见；"
              "用简体中文，输出不超过 400 字，分点陈述。")

    def interpret_file(self, code: str, name: str, markers: dict) -> str:
        prompt = (
            "你是代码审查助手。开发者上传了一个源码文件，请帮忙解读：\n"
            "1) 这个文件大致做什么（模块职责、关键函数/入口）；\n"
            "2) 与开源许可证相关的外观信号（版权头、SPDX 标识、来源注释、仓库链接）及其含义；\n"
            "3) 建议人工进一步核查什么。\n"
            "文件名：%s\n文件内确定性提取的标记（可信）：\n%s\n源代码：\n%s\n%s"
            % (name, json.dumps(markers, ensure_ascii=False)[:2000],
               code[:60000], self._GUARD))
        return self.chat(prompt, timeout=60)

    def summarize_scan(self, digest: dict) -> str:
        prompt = (
            "你是开源合规助手。以下是一次代码来源审查的结构化结果摘要，"
            "请面向开发者写一份 200 字左右的执行摘要：整体风险、最重要的 1-3 个命中、"
            "下一步动作。不得新增摘要之外的事实。\n摘要数据：\n%s\n%s"
            % (json.dumps(digest, ensure_ascii=False)[:8000], self._GUARD))
        return self.chat(prompt, timeout=60)

    def answer_question(self, question: str, digest: dict) -> str:
        prompt = (
            "你是开源合规助手。开发者就刚才的审查结果提问，请只依据审查摘要回答；"
            "若摘要中没有答案，明确说当前证据不足以回答，并建议在语料或人工层面如何补证。\n"
            "审查摘要：\n%s\n问题：%s\n%s"
            % (json.dumps(digest, ensure_ascii=False)[:8000], question, self._GUARD))
        return self.chat(prompt, timeout=60)

    def explain_licence(self, analysis: dict) -> str:
        prompt = (
            "你是开源许可证科普助手。以下是确定性规则引擎对一组许可证组合的推理结果，"
            "请用通俗语言向不熟悉开源许可的开发者解释：为什么是这个结论、义务清单意味着"
            "每天要做什么、最常见的踩坑点。规则引擎的结论不可更改。\n推理结果：\n%s\n%s"
            % (json.dumps(analysis, ensure_ascii=False)[:4000], self._GUARD))
        return self.chat(prompt, timeout=60)


def get_provider(prefer: str = "auto"):
    if prefer in ("llm", "auto"):
        llm = OpenAICompatProvider.from_env()
        if llm is not None:
            return llm
        if prefer == "llm":
            raise SystemExit("未配置 CODEGUARD_LLM_BASE_URL/CODEGUARD_LLM_API_KEY")
    return OfflineTemplateProvider()
