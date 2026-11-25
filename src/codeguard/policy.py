"""Project-level compliance policy engine (--policy).

Loads a JSON policy file (e.g. ``.codeguard.json``) with strict schema and
type validation, applies allowlist waivers and license bans deterministically,
and preserves every finding with full audit metadata rather than silently
dropping matches.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass

from .license_intel import USAGE_MODES, graded_id

VALID_RISKS = ("S0", "S1", "S2", "S3", "S4")
_ALLOWED_KEYS = frozenset({
    "$schema", "project_license", "usage", "fail_on",
    "allow_packages", "deny_licenses",
})
_DEFAULT_WAIVE_REASON = "策略白名单豁免"


class PolicyError(ValueError):
    """Raised when a compliance policy file cannot be read or fails validation."""


@dataclass(frozen=True)
class AllowRule:
    package: str
    reason: str = _DEFAULT_WAIVE_REASON


@dataclass(frozen=True)
class Policy:
    path: str = ""
    sha256: str = ""
    project_license: str = ""
    usage: str = ""
    fail_on: tuple[str, ...] | None = None
    allow_packages: tuple[AllowRule, ...] = ()
    deny_licenses: tuple[str, ...] = ()


def _require_nonempty_str(value, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyError("策略字段 %s 必须是非空字符串" % field_name)
    return value.strip()


def _parse_allow_packages(raw) -> tuple[AllowRule, ...]:
    if not isinstance(raw, list):
        raise PolicyError("策略字段 allow_packages 必须是列表")
    rules = []
    for idx, item in enumerate(raw):
        if isinstance(item, str):
            pkg = _require_nonempty_str(item, "allow_packages[%d]" % idx)
            rules.append(AllowRule(pkg, _DEFAULT_WAIVE_REASON))
        elif isinstance(item, dict):
            unknown = set(item) - {"package", "reason"}
            if unknown:
                raise PolicyError("allow_packages[%d] 包含未知字段：%s"
                                  % (idx, ", ".join(sorted(unknown))))
            if "package" not in item:
                raise PolicyError("allow_packages[%d] 缺少 package 字段" % idx)
            pkg = _require_nonempty_str(item["package"],
                                        "allow_packages[%d].package" % idx)
            if "reason" in item:
                if not isinstance(item["reason"], str):
                    raise PolicyError("allow_packages[%d].reason 必须是字符串" % idx)
                reason = item["reason"].strip() or _DEFAULT_WAIVE_REASON
            else:
                reason = _DEFAULT_WAIVE_REASON
            rules.append(AllowRule(pkg, reason))
        else:
            raise PolicyError("allow_packages[%d] 必须是字符串或对象" % idx)
    return tuple(rules)


def _parse_deny_licenses(raw) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise PolicyError("策略字段 deny_licenses 必须是字符串列表")
    out = []
    for idx, item in enumerate(raw):
        out.append(_require_nonempty_str(item, "deny_licenses[%d]" % idx))
    return tuple(out)


def _parse_fail_on(raw) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise PolicyError("策略字段 fail_on 必须是风险等级列表")
    out = []
    seen = set()
    for idx, item in enumerate(raw):
        val = _require_nonempty_str(item, "fail_on[%d]" % idx)
        if val not in VALID_RISKS:
            raise PolicyError("fail_on[%d] 无效风险等级 %r，仅支持 %s"
                              % (idx, val, ", ".join(VALID_RISKS)))
        if val not in seen:
            seen.add(val)
            out.append(val)
    return tuple(out)


def load_policy(path: str) -> Policy:
    """Load and strictly validate a JSON compliance policy file."""
    if not isinstance(path, str) or not path.strip():
        raise PolicyError("策略文件路径不能为空")
    if not os.path.isfile(path):
        raise PolicyError("找不到策略文件：%s" % path)
    try:
        with open(path, "rb") as fh:
            raw_bytes = fh.read()
        sha = hashlib.sha256(raw_bytes).hexdigest()
        data = json.loads(raw_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyError("策略文件解析失败（%s）：%s" % (path, exc))
    if not isinstance(data, dict):
        raise PolicyError("策略文件顶层必须是 JSON 对象")

    unknown = set(data) - _ALLOWED_KEYS
    if unknown:
        raise PolicyError("策略文件包含未定义字段：%s" % ", ".join(sorted(unknown)))
    if "$schema" in data and not isinstance(data["$schema"], str):
        raise PolicyError("策略字段 $schema 必须是字符串")

    project_license = ""
    if "project_license" in data:
        project_license = _require_nonempty_str(data["project_license"], "project_license")

    usage = ""
    if "usage" in data:
        usage = _require_nonempty_str(data["usage"], "usage")
        if usage not in USAGE_MODES:
            raise PolicyError("策略字段 usage 无效：%r，可选值 %s"
                              % (usage, ", ".join(USAGE_MODES)))

    fail_on = None
    if "fail_on" in data:
        fail_on = _parse_fail_on(data["fail_on"])

    allow_packages = ()
    if "allow_packages" in data:
        allow_packages = _parse_allow_packages(data["allow_packages"])

    deny_licenses = ()
    if "deny_licenses" in data:
        deny_licenses = _parse_deny_licenses(data["deny_licenses"])

    return Policy(
        path=os.path.abspath(path).replace(os.sep, "/"),
        sha256=sha,
        project_license=project_license,
        usage=usage,
        fail_on=fail_on,
        allow_packages=allow_packages,
        deny_licenses=deny_licenses,
    )


def _license_keys(spdx: str) -> set[str]:
    keys = {spdx.strip().lower()}
    canon = graded_id(spdx.strip())
    if canon != "UNKNOWN" or spdx.strip().upper() == "UNKNOWN":
        keys.add(canon.lower())
    return keys


def apply_policy(scan_result, policy: Policy) -> dict:
    """Apply policy waivers and license denials without deleting any finding."""
    allow_map = {rule.package.lower(): rule for rule in policy.allow_packages}
    denied_keys = set()
    for lic in policy.deny_licenses:
        denied_keys |= _license_keys(lic)

    waived_items = []
    denied_items = []
    for finding in scan_result.findings:
        rule = allow_map.get(finding.package.lower())
        if rule is not None:
            prev_risk = finding.risk
            finding.risk = "S1"
            finding.policy_action = "waived"
            finding.policy_reason = rule.reason
            waived_items.append({
                "package": finding.package,
                "version": finding.version,
                "path": finding.path,
                "license_spdx": finding.license_spdx,
                "previous_risk": prev_risk,
                "risk": "S1",
                "reason": rule.reason,
            })
            scan_result.notes.append(
                "策略豁免：%s@%s（%s）风险由 %s 降级为 S1；理由：%s"
                % (finding.package, finding.version, finding.license_spdx,
                   prev_risk, rule.reason)
            )
            continue

        if denied_keys and finding.corroborated and (_license_keys(finding.license_spdx) & denied_keys):
            prev_risk = finding.risk
            finding.risk = "S4"
            finding.policy_action = "denied"
            reason = "命中策略禁止许可证 %s" % finding.license_spdx
            finding.policy_reason = reason
            denied_items.append({
                "package": finding.package,
                "version": finding.version,
                "path": finding.path,
                "license_spdx": finding.license_spdx,
                "previous_risk": prev_risk,
                "risk": "S4",
                "reason": reason,
            })
            scan_result.notes.append(
                "策略阻断：%s@%s（%s）命中禁止许可证，风险由 %s 调整为 S4；理由：%s"
                % (finding.package, finding.version, finding.license_spdx,
                   prev_risk, reason)
            )

    audit = {
        "policy_path": policy.path,
        "policy_sha256": policy.sha256,
        "project_license": policy.project_license or scan_result.target_license,
        "usage": policy.usage or scan_result.usage,
        "fail_on": list(policy.fail_on) if policy.fail_on is not None else [],
        "waived_count": len(waived_items),
        "denied_count": len(denied_items),
        "total_findings": len(scan_result.findings),
        "waived": waived_items,
        "denied": denied_items,
    }
    scan_result.policy_audit = audit
    return audit
