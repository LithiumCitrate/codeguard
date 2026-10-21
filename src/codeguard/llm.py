"""Explanation layer: pluggable provider, deterministic by default.

The rules require an honest account of generative-AI use, so the design decision
is written into the code: the *default* provider is a deterministic template
renderer that works with no key, no network and no external service, and which
produces the same explanation for the same evidence every time. A
large-language-model provider is available behind an explicit opt-in, and when it
is used the disclosure string records which service was called.
"""

from __future__ import annotations

import json
import os
import urllib.request

from .license_intel import RISK_LABELS

DISCLOSURE = (
    "CodeGuard 默认使用确定性模板生成器产出合规说明，全程离线、无外部模型调用、"
    "结果可逐字节复现；仅当显式配置 CODEGUARD_LLM_BASE_URL 与 API Key 时才会调用"
    "第三方大模型接口，且调用情况会被写入报告的 ai_usage 字段以供审计。")


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

    _PROMPT = (
        "你是开源合规助手。仅依据给定证据撰写一段面向开发者的中文处置建议，"
        "不得新增证据之外的法律结论，不得声称这是法律意见。证据：{}")

    def describe(self, finding) -> str:
        payload = {"model": self.model,
                   "messages": [{"role": "user",
                                 "content": self._PROMPT.format(json.dumps(
                                     finding.as_dict(), ensure_ascii=False)[:6000])}],
                   "temperature": 0.2}
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + self.api_key})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:  # never fail a scan because prose failed
            return OfflineTemplateProvider().describe(finding) + \
                "\n（LLM 调用失败，已回退到离线模板：%s）" % type(exc).__name__


def get_provider(prefer: str = "auto"):
    if prefer in ("llm", "auto"):
        llm = OpenAICompatProvider.from_env()
        if llm is not None:
            return llm
        if prefer == "llm":
            raise SystemExit("未配置 CODEGUARD_LLM_BASE_URL/CODEGUARD_LLM_API_KEY")
    return OfflineTemplateProvider()
