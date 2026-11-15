# llmFusion LICENSE 文本核验通道 · 离线可复现评测

- 生成时间：2026-11-15T04:01:53Z
- 模式：**offline-fixture**（`fetch_source` 由固定离线夹具注入，未发起任何真实网络请求、未使用任何 API Key）
- 复现命令：`python scripts/eval_license_grounding.py`

> **不得据此主张真实联网核验成功率。** 本评测只证明核验通道的分类逻辑、审计字段与端到端链路正确且可复现。真实联网的 `web:license-text-verified` 比率仍须在稳定网络下用 `scripts/eval_webprobe.py` 另行测量。2026-11-15 的 webprobe / round2 留存证据中该比率为 0/2，口径不变。

## 结果总览

| 分组 | 通过 / 总数 |
|---|---|
| SPDX 签名分类 | 11 / 11 |
| 核验通道（成功/回退/失败审计/缓存） | 5 / 5 |
| 端到端 webprobe（成功 + 失败两条路径） | 2 / 2 |
| **合计** | **18 / 18** |

## 1. SPDX 签名分类

| 用例 | 期望 | 实际 | 结果 |
|---|---|---|---|
| GPL-3.0 全文含 §13 提及 Affero（不得误判 AGPL） | GPL-3.0-only | GPL-3.0-only | 通过 |
| AGPL-3.0 | AGPL-3.0-only | AGPL-3.0-only | 通过 |
| LGPL-2.1 | LGPL-2.1 | LGPL-2.1 | 通过 |
| GPL-2.0 | GPL-2.0-only | GPL-2.0-only | 通过 |
| Apache-2.0 | Apache-2.0 | Apache-2.0 | 通过 |
| MPL-2.0 | MPL-2.0 | MPL-2.0 | 通过 |
| MIT | MIT | MIT | 通过 |
| BSD-3-Clause（应优先于 BSD-2） | BSD-3-Clause | BSD-3-Clause | 通过 |
| BSD-2-Clause | BSD-2-Clause | BSD-2-Clause | 通过 |
| Unlicense | Unlicense | Unlicense | 通过 |
| 专有条款（应识别不出，返回空） | (unrecognised) | (unrecognised) | 通过 |

## 2. ground_license 行为

| 用例 | status | reason | SPDX | 尝试 URL 数 | 结果 |
|---|---|---|---|---|---|
| LICENSE 存在且被识别 → verified | verified | license-text-classified | GPL-3.0-only | 1 | 通过 |
| LICENSE* 全 404、仅 COPYING 存在 → verified（旧版会漏） | verified | license-text-classified | GPL-2.0-only | 4 | 通过 |
| 全部拉取超时 → unavailable + 逐 URL 失败原因（旧版静默返回 {}） | unavailable | all-candidates-unavailable | — | 9 | 通过 |
| 拉取成功但文本无法识别 → unavailable + 明确原因 | unavailable | no-recognised-license-text | — | 9 | 通过 |
| 同一仓库多条命中共享缓存，不重复拉取 | verified | license-text-classified | GPL-3.0-only | 1 | 通过 |

## 3. 端到端 webprobe

### 上游 LICENSE 可拉取并可识别

- `license_source`: `web:license-text-verified`；`license_spdx`: `GPL-3.0-only`；`risk`: `S3`
- `license_grounding`: status=`verified`，reason=`license-text-classified`，记录尝试 1 个 URL
- 安全不变量：offline_index_unchanged=成立、never_blocks=成立、risk_capped_at_S3=成立、audit_fields_present=成立

### 上游 LICENSE 全部拉取失败

- `license_source`: `web:llm-inferred`；`license_spdx`: `UNKNOWN`；`risk`: `S2`
- `license_grounding`: status=`unavailable`，reason=`all-candidates-unavailable`，记录尝试 9 个 URL
- 安全不变量：offline_index_unchanged=成立、never_blocks=成立、risk_capped_at_S3=成立、audit_fields_present=成立

## 本次修补相对旧版的变化

1. 失败不再静默：`provenance.license_grounding` 记录 status / reason / 逐 URL attempts。
2. 候选文件名补入 `COPYING`、`LICENSE.rst`、`LICENCE`、`docs/LICENSE`（旧版只试 3 个）。
3. 同一仓库的多条命中共享缓存，不再按 finding 重复拉取 LICENSE。
4. LICENSE 拉取使用独立的 8 秒超时，避免拖垮整次 probe。
5. `ground_license` 恒定返回可审计字典；调用方以 `spdx` 判定成功，而非字典真值。
