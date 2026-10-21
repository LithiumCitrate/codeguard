"""SPDX metadata resolution and licence-obligation reasoning.

Two problems are solved here.

1. *Metadata is messy.* PyPI and source headers rarely carry a clean SPDX id
   (``license=None`` plus a free-text field or a trove classifier is normal), so
   a documented resolution chain maps whatever the manifest offers onto a
   canonical SPDX id and records **how** it was decided.

2. *Compatibility is not a lookup table.* Each licence is described as a set of
   obligations, a copyleft scope and a trigger condition. A verdict is then
   computed as an obligation-satisfaction test for the declared usage mode, so a
   new licence only needs a profile, not a new row in an ever-growing matrix.

Output is an engineering signal, not legal advice; the tool says so.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SPDX_FILE = os.path.join(DATA_DIR, "spdx_licenses.json")

USAGE_MODES = ("internal_use", "unmodified_internal", "inline_copy",
               "static_link", "dynamic_link", "tool_interface", "network_service",
               "distribution")

# copyleft scopes
NONE, FILE, MODULE, LIBRARY, PROGRAM = "none", "file", "module", "library", "program"


@dataclass(frozen=True)
class LicenseProfile:
    spdx: str
    name: str
    family: str            # permissive | weak | strong | network | public_domain | unknown
    scope: str
    notice: bool = False
    source_offer: bool = False
    same_license: str = ""
    weaker_ok: bool = False
    network_trigger: bool = False
    patent_grant: bool = False
    state_changes: bool = False
    no_relicense: bool = False
    relink: bool = False
    osi_approved: bool = True
    clauses: tuple = ()

    def as_dict(self) -> dict:
        d = asdict(self)
        d["clauses"] = list(self.clauses)
        return d


P = LicenseProfile

PROFILES = {x.spdx: x for x in [
    P("MIT", "MIT License", "permissive", NONE, notice=True,
      clauses=("§1 copyright notice and permission notice must be included in all copies",)),
    P("BSD-2-Clause", "BSD 2-Clause", "permissive", NONE, notice=True,
      clauses=("Redistributions must retain copyright notice and conditions list",)),
    P("BSD-3-Clause", "BSD 3-Clause", "permissive", NONE, notice=True,
      clauses=("Endorsement clause must be preserved; notice retained in redistribution",)),
    P("BSD-4-Clause", "BSD 4-Clause (deprecated)", "permissive", NONE, notice=True,
      osi_approved=False,
      clauses=("Advertising clause makes it incompatible with most copyleft licences",)),
    P("Apache-2.0", "Apache License 2.0", "permissive", NONE, notice=True,
      source_offer=True, patent_grant=True, state_changes=True,
      clauses=("[2] grant of copyright + patent licence",
               "[3] must retain NOTICE and state changes",
               "[4] derivatives may be licensed under different terms",
               "[6]/[7] patent termination; additional restrictions not granted")),
    P("ISC", "ISC License", "permissive", NONE, notice=True),
    P("Zlib", "zlib License", "permissive", NONE, notice=True,
      clauses=("Altered versions must be plainly marked as such")),
    P("PSF-2.0", "Python Software Foundation License", "permissive", NONE, notice=True),
    P("Artistic-2.0", "Artistic License 2.0", "permissive", NONE, notice=True),
    P("PostgreSQL", "PostgreSQL License", "permissive", NONE, notice=True),
    P("MulanPSL-2.0", "木兰宽松许可证 第2版", "permissive", NONE, notice=True,
      source_offer=True, patent_grant=True,
      clauses=("第3条 著作权许可与专利许可", "第4条  distribution: 保留许可声明与源码提供方式",
               "第5条 采用其他许可分发时必须明确告知并使用本许可证的许可条件")),
    P("WTFPL", "Do What The F*ck You Want To Public License", "permissive", NONE,
      clauses=("No conditions beyond the grant itself")),
    P("Unlicense", "The Unlicense (public domain dedication)", "public_domain", NONE),
    P("CC0-1.0", "Creative Commons Zero v1.0 Universal", "public_domain", NONE),
    P("MPL-2.0", "Mozilla Public License 2.0", "weak", MODULE, notice=True,
      source_offer=True, no_relicense=True,
      clauses=("§3.2 file-level copyleft: modified MPL files stay MPL",
               "§3.2 larger work may use other licences, MPL files must stay MPL",
               "§3.3 source code form of MPL files must be made available")),
    P("LGPL-2.1", "GNU Lesser General Public License 2.1", "weak", LIBRARY,
      notice=True, source_offer=True, relink=True, weaker_ok=True,
      clauses=("§6 combined work: permit relinking/replacement of the library",
               "§4/§6 library source and licence copy must accompany distribution")),
    P("LGPL-3.0", "GNU Lesser General Public License 3.0", "weak", LIBRARY,
      notice=True, source_offer=True, relink=True, weaker_ok=True,
      clauses=("§4 combined work: convey under LGPL-3.0 terms with relinking permitted")),
    P("EPL-2.0", "Eclipse Public License 2.0", "weak", MODULE, notice=True,
      source_offer=True, no_relicense=True,
      clauses=("§2 secondary licences may not add restrictions; contributions stay EPL")),
    P("GPL-2.0-only", "GNU General Public License v2.0 only", "strong", PROGRAM,
      notice=True, source_offer=True, same_license="GPL-2.0-only", no_relicense=True,
      clauses=("§2 derivative work must be licensed as a whole to recipients under GPL-2.0",
               "§3 corresponding source must be provided",
               "§6 no further restrictions may be imposed")),
    P("GPL-2.0-or-later", "GNU General Public License v2.0 or later", "strong", PROGRAM,
      notice=True, source_offer=True, same_license="GPL-2.0-or-later", weaker_ok=True),
    P("GPL-3.0-only", "GNU General Public License v3.0 only", "strong", PROGRAM,
      notice=True, source_offer=True, state_changes=True, same_license="GPL-3.0-only",
      clauses=("§5 convey source under the same licence as a whole",
               "§5 additional restrictions are limited to those enumerated")),
    P("GPL-3.0-or-later", "GNU General Public License v3.0 or later", "strong", PROGRAM,
      notice=True, source_offer=True, state_changes=True, same_license="GPL-3.0-or-later",
      weaker_ok=True),
    P("AGPL-3.0-only", "GNU Affero General Public License v3.0 only", "network", PROGRAM,
      notice=True, source_offer=True, state_changes=True, same_license="AGPL-3.0-only",
      network_trigger=True,
      clauses=("§13 network interaction triggers source availability (no distribution needed)",
               "§13 combined work must be licensed as a whole under AGPL-3.0")),
    P("AGPL-3.0-or-later", "GNU Affero General Public License v3.0 or later", "network",
      PROGRAM, notice=True, source_offer=True, state_changes=True,
      same_license="AGPL-3.0-or-later", network_trigger=True, weaker_ok=True,
      clauses=("§13 remote network service triggers corresponding source")),
    P("EUPL-1.2", "European Union Public License 1.2", "strong", PROGRAM, notice=True,
      source_offer=True, same_license="EUPL-1.2", weaker_ok=True),
    P("OFL-1.1", "SIL Open Font License 1.1", "weak", FILE, notice=True, no_relicense=True,
      clauses=("Reserved font names; the font itself cannot be sold alone")),
    P("GPL-1.0", "GNU General Public License v1.0", "strong", PROGRAM, notice=True,
      source_offer=True, same_license="GPL-1.0", osi_approved=False),
    # SPDX LicenseRef-* is the documented way to name a licence outside the list;
    # it lets a closed-source target participate in the reasoning instead of
    # collapsing to UNKNOWN.
    P("LicenseRef-Proprietary", "Proprietary / closed source (LicenseRef)",
      "proprietary", NONE, notice=True, osi_approved=False,
      clauses=("不分发源码；无法满足任何 copyleft 的源码提供义务",)),
    P("LicenseRef-Internal", "Internal unreleased deployment (LicenseRef)",
      "internal", NONE, notice=True, osi_approved=False),
    P("UNKNOWN", "Unknown / unresolved", "unknown", NONE, osi_approved=False),
]}

# Explicit pairwise conflicts that a pure obligation check would miss, because
# they arise from clause interaction rather than missing obligations.
CONFLICTS = {
    ("Apache-2.0", "GPL-2.0-only"): (
        "incompatible",
        "Apache-2.0 的专利终止条款(§6)构成 GPLv2 §6 “不得施加额外限制” 所禁止的额外限制，"
        "OSI/FSF 均判定 Apache-2.0 与 GPL-2.0-only 不兼容。"),
    ("Apache-2.0", "GPL-2.0-or-later"): (
        "incompatible",
        "当上游选择 GPL-2.0-only 时同上；若上游声明 -or-later 并按 §2.1 升级到 GPL-3.0 则可行。"),
    ("GPL-2.0-only", "GPL-3.0-only"): (
        "incompatible",
        "GPL-2.0-only 与 GPL-3.0-only 互不可升级，合并作品无法用同一许可证整体授权。"),
    ("BSD-4-Clause", "GPL-2.0-only"): (
        "incompatible",
        "BSD-4-Clause 的广告条款属于 GPLv2 §6 禁止的额外限制。"),
    ("LGPL-3.0", "GPL-2.0-only"): (
        "incompatible",
        "LGPL-3.0 指向 GPL-3.0 条款，无法与仅 GPL-2.0 的组合作品合并。"),
}

_ALIAS = [
    (r"^mit(\s+license)?$|^mit/x11|^the mit license", "MIT"),
    # short forms that dominate real metadata; ordered so that the more specific
    # family (AGPL, then LGPL, then GPL) wins, and "or later" before "only"
    (r"^(gnu[\s\-]*)?(agpl|affero)", "AGPL-3.0-only"),
    (r"^(gnu[\s\-]*)?lgpl[\s\-]*v?2(\.1)?", "LGPL-2.1"),
    (r"^(gnu[\s\-]*)?lgpl[\s\-]*v?3", "LGPL-3.0"),
    (r"^(gnu[\s\-]*)?gpl[\s\-]*v?2(\.0)?([\s\-]*(or[\s\-]*later|\+|以后))", "GPL-2.0-or-later"),
    (r"^(gnu[\s\-]*)?gpl[\s\-]*v?3(\.0)?([\s\-]*(or[\s\-]*later|\+|以后))", "GPL-3.0-or-later"),
    (r"^(gnu[\s\-]*)?gpl[\s\-]*v?2(\.0)?$", "GPL-2.0-only"),
    (r"^(gnu[\s\-]*)?gpl[\s\-]*v?3(\.0)?$", "GPL-3.0-only"),
    (r"^proprietary$|^commercial$|closed[\s\-]*source|^license\-ref\-proprietary",
     "LicenseRef-Proprietary"),
    (r"apache[\s\-]*(software[\s\-]*)?licen[cs]e?[\s\-]*2(\.0)?", "Apache-2.0"),
    (r"^apache[\s\-]*2(\.0)?$", "Apache-2.0"),
    (r"^bsd[\s\-]*2[\s\-]*clause", "BSD-2-Clause"),
    (r"^bsd[\s\-]*(new[\s\-]|3[\s\-]|clause)?|^bsd[\s\-]*licen[cs]e", "BSD-3-Clause"),
    (r"^gnu general public license[\s\-]*v?2(\.0)?[\s\-]*(only)?$", "GPL-2.0-only"),
    (r"gnu general public license[\s\-]*v?3(\.0)?", "GPL-3.0-only"),
    (r"gnu affero[\s\-]*(general[\s\-]*)?public[\s\-]*license[\s\-]*v?3", "AGPL-3.0-only"),
    (r"gnu[\s\-]*lesser[\s\-]*general[\s\-]*public[\s\-]*license[\s\-]*v?3", "LGPL-3.0"),
    (r"gnu[\s\-]*(lesser|library)[\s\-]*general[\s\-]*public[\s\-]*license[\s\-]*v?2", "LGPL-2.1"),
    (r"mozilla public license[\s\-]*2", "MPL-2.0"),
    (r"eclipse public license[\s\-]*2", "EPL-2.0"),
    (r"python software foundation", "PSF-2.0"),
    (r"isc licen[cs]e", "ISC"),
    (r"the unlicense|unlicense", "Unlicense"),
    (r"cc0[\s\-]*(1\.0|universal)?", "CC0-1.0"),
    (r"zlib/libpng|zlib licen[cs]e", "Zlib"),
    (r"mulanpsl|木兰宽松", "MulanPSL-2.0"),
    (r"artistic licen[cs]e[\s\-]*2", "Artistic-2.0"),
    (r"postgresql licen[cs]e", "PostgreSQL"),
    (r"european union public license", "EUPL-1.2"),
    (r"sil open font license", "OFL-1.1"),
]
_CLASSIFIER_RE = re.compile(r"License :: OSI Approved :: (.+)$", re.M)
_TROVE_MAP = {
    "MIT License": "MIT",
    "Apache Software License": "Apache-2.0",
    "BSD License": "BSD-3-Clause",
    "ISC License (ISCL)": "ISC",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "GNU General Public License v3 or later (GPLv3+)": "GPL-3.0-or-later",
    "GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "GNU General Public License v2 (GPLv2)": "GPL-2.0-only",
    "GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL-3.0",
    "GNU Lesser General Public License v2.1 or later (LGPLv2.1+)": "LGPL-2.1",
    "GNU Affero General Public License v3": "AGPL-3.0-only",
    "Python Software Foundation License": "PSF-2.0",
    "Intel BSD License": "BSD-3-Clause",
    "Eclipse Public License 1.0 (EPL-1.0)": "EPL-2.0",
    "Zope 2 License": "ZPL-2.1",
}


def load_spdx(path: str = SPDX_FILE) -> dict:
    """Return SPDX id -> {name, isOsiApproved, isDeprecated}; empty if not fetched."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    out = {}
    for item in data.get("licenses", []):
        out[item["licenseId"]] = {"name": item.get("name", ""),
                                  "osi": bool(item.get("isOsiApproved", False)),
                                  "deprecated": bool(item.get("isDeprecatedLicenseId", False))}
    return out


_CANON = {"GPL-2.0": "GPL-2.0-only", "GPL-3.0": "GPL-3.0-only",
          "AGPL-3.0": "AGPL-3.0-only"}


def resolve_spdx(candidates, spdx_index: dict | None = None) -> tuple:
    """Run the resolution chain over ``[(value, origin), ...]``.

    Returns ``(spdx_id, origin)`` and never guesses silently: an unresolved
    string stays UNKNOWN so that the pipeline refuses to auto-pass it.
    """
    index = spdx_index if spdx_index is not None else load_spdx()
    if isinstance(candidates, str):
        candidates = [(candidates, "literal")]
    for value, origin in candidates:
        if not value:
            continue
        text = str(value).strip()
        if text in _CANON:
            return _CANON[text], origin
        if text in PROFILES and text != "UNKNOWN":
            return text, origin
        if index and text in index:
            return _CANON.get(text, text), origin
        low = text.lower().replace("(c)", "").strip()
        for pattern, spdx in _ALIAS:
            if re.search(pattern, low):
                return spdx, origin
        stripped = re.sub(r"\s+(licen[cs]e|license)$", "", low).strip()
        if stripped in PROFILES:
            return stripped.upper() if stripped.isascii() else stripped, origin
        for classifier, spdx in _TROVE_MAP.items():
            if classifier.lower() in low:
                return spdx, origin
    return "UNKNOWN", "unresolved"


def profile_for(spdx: str) -> LicenseProfile:
    return PROFILES.get(spdx, PROFILES["UNKNOWN"])


def normalize_expression(expr: str, spdx_index: dict | None = None) -> tuple:
    """Handle the tiny AND/OR subset that shows up in Python project metadata."""
    if not expr:
        return "UNKNOWN", "empty"
    cleaned = expr.strip()
    # only the uppercase SPDX operators split an expression: free-text fields
    # say "GPL v2 or later", and splitting that would silently change the id
    parts = [p.strip("() ") for p in re.split(r"\s+(?:AND|OR)\s+", cleaned)]
    if len(parts) > 1:
        resolved = [resolve_spdx([(p, "expression:%s" % p)], spdx_index)
                    for p in parts]
        strong = [r for r in resolved if profile_for(r[0]).family in ("strong", "network")]
        if strong:
            order = {"network": 3, "strong": 2, "weak": 1, "permissive": 0,
                     "public_domain": -1, "unknown": 0}
            pick = max((s for s in strong),
                       key=lambda r: order[profile_for(r[0]).family])
            return pick[0], "expression:%s" % cleaned
        worst = max((r for r in resolved),
                    key=lambda r: len(r[0]))
        return worst[0], "expression:%s" % cleaned
    return resolve_spdx([(cleaned, "expression:%s" % cleaned)], spdx_index)


@dataclass
class Verdict:
    source_spdx: str
    target_spdx: str
    usage: str
    status: str            # compatible | conditional | incompatible | unknown
    obligations: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _triggers(profile: LicenseProfile, usage: str) -> bool:
    if usage in ("internal_use", "unmodified_internal"):
        return False
    if profile.network_trigger and usage in ("network_service", "distribution",
                                             "inline_copy", "static_link"):
        return True
    if usage in ("distribution", "inline_copy", "static_link", "dynamic_link",
                 "tool_interface", "network_service"):
        return True
    return False


def _family_rank(spdx: str, family: str) -> tuple:
    """(family rank, major version, allows_later) for licence comparison."""
    order = {"public_domain": 0, "permissive": 1, "internal": 1,
             "proprietary": 1, "weak": 2, "strong": 3, "network": 4, "unknown": 0}
    m = re.match(r"(?:AGPL|GPL|LGPL)-(\d+\.\d+)-(only|or-later)", spdx)
    if m:
        return order.get(family, 0), float(m.group(1)), m.group(2) == "or-later"
    m = re.match(r"(?:AGPL|GPL|LGPL)-(\d+\.\d+)", spdx)
    if m:
        return order.get(family, 0), float(m.group(1)), False
    return order.get(family, 0), 0.0, False


def required_license(src: LicenseProfile) -> str:
    """The licence a combined/derivative work must be conveyed under."""
    return src.same_license or src.spdx


def compare(req: str, tgt: LicenseProfile) -> tuple:
    """Return ("ok"|"upgrade"|"fail", explanation) for conveying under ``tgt``."""
    src_rank, src_ver, src_later = _family_rank(req, profile_for(req).family)
    tgt_rank, tgt_ver, tgt_later = _family_rank(tgt.spdx, tgt.family)
    if tgt.spdx == req:
        return "ok", ""
    if src_rank <= 1:
        return "ok", ""
    fam = lambda x: re.match(r"(AGPL|GPL|LGPL)", x or "")
    a, b = fam(req), fam(tgt.spdx)
    if a and b:
        if a.group(1) == b.group(1):
            if tgt_ver + (0.5 if tgt_later else 0) >= src_ver:
                if tgt_ver >= src_ver:
                    return "ok", "" if not tgt_later else "可按 %s 条款 conveyed" % req
                return "fail", "版本不足"
            return "fail", "%s 无法降级满足 %s" % (tgt.spdx, req)
        if a.group(1) == "GPL" and b.group(1) == "AGPL":
            if src_ver > 2.5:
                return "upgrade", "并入 AGPL 代码后整体须按 %s 授权" % tgt.spdx
            return "fail", "GPLv2 家族无法升级到 AGPL-3.0 条款"
        if a.group(1) == "AGPL":
            return "upgrade", "AGPL 要求更严：合并作品须整体按 %s 授权" % req
        if a.group(1) == "LGPL":
            return "upgrade", "LGPL §4 允许升级为 GPL 条款整体分发"
        # GPL -> LGPL downgrade
        return "fail", "GPL 代码不能以 LGPL 库条款合并分发"
    if tgt_rank < src_rank and tgt.family != "weak":
        return "fail", "目标许可证 %s 的 copyleft 强度低于 %s 所要求的 %s" % (
            tgt.spdx, req, req)
    if tgt.family == "weak":
        return "fail", "%s 属于文件/库级 copyleft，无法满足 %s 的整体授权要求" % (
            tgt.spdx, req)
    return "fail", "目标许可证 %s 无法满足 %s 的整体授权要求" % (tgt.spdx, req)


def analyze(source_spdx: str, target_spdx: str, usage: str = "inline_copy",
            modified: bool = True) -> Verdict:
    src = profile_for(source_spdx)
    tgt = profile_for(target_spdx)
    v = Verdict(source_spdx, target_spdx, usage, "compatible")

    if src.family == "unknown" or tgt.family == "unknown":
        v.status = "unknown"
        v.notes.append("许可证未能解析为 SPDX id，结论需人工确认（不默认放行）。")
        return v
    if not _triggers(src, usage):
        v.notes.append("使用方式未触发该许可证的实质条件（仅内部使用/未分发）。")
        if src.notice:
            v.obligations.append("保留版权声明与许可证文本")
        return v

    # Clause-interaction cases are decided explicitly: they do not follow from a
    # missing obligation but from two clauses that cannot both be satisfied.
    pair = CONFLICTS.get((source_spdx, target_spdx))
    if pair:
        status, reason = pair
        if status == "incompatible":
            v.conflicts.append(reason)
            v.status = "incompatible"
        else:
            v.notes.append(reason)
            v.status = "conditional"
    elif src.family in ("strong", "network"):
        req = required_license(src)
        outcome, detail = compare(req, tgt)
        if outcome == "fail":
            v.conflicts.append(detail + "；来源代码许可证 %s 的传染性范围为整件作品。" % source_spdx)
            v.status = "incompatible"
        elif outcome == "upgrade":
            v.notes.append(detail)
            v.obligations.append("整件组合作品必须整体按 %s 条款授权并开放对应源码" % req)
            v.status = "conditional"
        elif src.network_trigger and usage == "network_service" \
                and not tgt.network_trigger:
            v.conflicts.append("AGPL §13 对远程网络服务生效：即便不分发，也必须向用户提供"
                               "与服务交互版本的对应源码，目标许可证 %s 不含该条款。" % target_spdx)
            v.status = "incompatible"
    elif src.scope == LIBRARY:
        v.status = "conditional"
        if usage == "static_link":
            v.obligations.append("静态链接时须以可重新链接的形式提供目标文件或提供等价机制（LGPL §6）")
        else:
            v.obligations.append("允许用户替换或重新链接该库（动态链接/数据表外置）")
        v.obligations.append("随分发提供库的源码形式与许可证文本")
    elif src.scope == MODULE:
        v.status = "conditional"
        v.notes.append("文件级 copyleft：被修改的文件必须保持 %s，项目其余文件可采用其它许可证。"
                       % source_spdx)
        v.obligations.append("为 %s 文件提供源码形式并保留许可证" % source_spdx)
    elif src.scope == FILE:
        v.status = "conditional"
        v.obligations.append("该文件本身不得改用其它许可证分发")

    if src.notice:
        v.obligations.append("保留版权/许可声明%s"
                             % ("及 NOTICE 文件" if src.patent_grant else ""))
    if src.state_changes:
        v.obligations.append("对修改过的文件作出显著说明")
    if src.source_offer:
        v.obligations.append("随分发提供对应源码（或书面要约）")
    # §13 binds the operator even when nothing is distributed, so the same-licence
    # AGPL case must not read as a plain "compatible" pass.
    if src.network_trigger and usage == "network_service":
        v.obligations.append("AGPL §13：为通过网络与本程序交互的用户提供获取对应源码的途径"
                             "（修改后的版本同样受约束）")
        if v.status == "compatible":
            v.status = "conditional"
            v.notes.append("同许可证整体授权成立，但 §13 的网络源码提供义务独立于分发条件，"
                           "内部部署不豁免，故降级为 conditional。")
    if usage == "network_service" and not src.network_trigger \
            and src.family in ("permissive", "weak"):
        v.notes.append("宽松/弱 copyleft 许可证在网络服务场景下不要求公开服务端源码。")
    return v


def risk_level(status: str, confidence: float, usage: str) -> str:
    """Grade the finding.

    Confidence enters on purpose: a licence conflict that only a 0.5-probability
    span supports is a *review* item, not a build break. Without this the gate
    would block on a structural coincidence between two unrelated projects.
    """
    published = usage in ("distribution", "network_service")
    if status == "incompatible":
        if confidence < 0.55:
            return "S2"
        return "S4" if published and confidence >= 0.75 else "S3"
    if status == "conditional":
        return "S3" if published else "S2"
    if status == "unknown":
        return "S2"
    return "S1" if confidence >= 0.8 else "S0"


RISK_LABELS = {
    "S0": "无风险：未检出复用或许可证无实质条件",
    "S1": "低风险：满足声明保留即可",
    "S2": "需确认：条件式合规或许可证信息缺失",
    "S3": "高风险：需按 copyleft 条款开源或替换",
    "S4": "严重：分发/网络服务与许可证条款直接冲突",
}
