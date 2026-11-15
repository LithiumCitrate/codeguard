# llmFusion LICENSE 文本核验通道 · 真实网络触发用例

- 生成时间：2026-11-15T06:33:22Z
- 模式：**hybrid-real-network-grounding**（混合模式）
- 复现命令：`python scripts/eval_license_grounding_realnetwork.py`

> **口径边界（务必先读）**：本用例**提案环节为离线确定性夹具**（未使用 Tavily / 大模型密钥、未发出检索查询、未上传用户源码），但 **上游 LICENSE 原文由真实公网拉取**，经 `fetch_source` → `classify_license_text` → `ground_license` 走完出厂代码路径。它证明「给定正确候选地址时，核验通道能在真实网络触发并留下可核验证据」，**不改写** `webprobe-eval-20261115.json` 与 `llmfusion-round2-realprojects.json` 中真实联网评测 `license_verified_rate 0/2` 的历史口径，也不构成联网核验成功率结论。完整真实联网（含 LLM 提案）的成功率仍须自配密钥、在稳定网络下用 `scripts/eval_webprobe.py` 测量。

## 一、结果

| 项 | 值 |
|---|---|
| 端到端 `license_source` | `web:license-text-verified` |
| 核验状态 / 原因 | `verified` / `license-text-classified` |
| 上游 LICENSE URL | `https://raw.githubusercontent.com/pallets/itsdangerous/main/LICENSE.txt` |
| 上游 LICENSE SHA-256 | `63af09891b6be8ad1a4252ed43af0f4efba7fc948e228367bed7f3c5ae0b09d7` |
| 确定性 SPDX 识别 | `BSD-3-Clause` |
| 命中风险 / 是否阻断 | `S1` / `False` |
| 本次耗时 | 4599 ms |
| 判定 | **PASS：核验通道真实触发** |

## 二、逐 URL 网络轨迹（真实请求）

| URL | 结果 | 字节 | SHA-256 | 耗时 |
|---|---|---|---|---|
| `https://raw.githubusercontent.com/pallets/itsdangerous/main/LICENSE` | real-network-failed | — | `拉取失败：HTTP 404（https:` | 0.91 s |
| `https://raw.githubusercontent.com/pallets/itsdangerous/main/LICENSE` | real-network-failed | — | `拉取失败：HTTP 404（https:` | 0.91 s |
| `https://raw.githubusercontent.com/pallets/itsdangerous/main/LICENSE` | real-network-failed | — | `拉取失败：HTTP 404（https:` | 0.64 s |
| `https://raw.githubusercontent.com/pallets/itsdangerous/main/LICENSE.txt` | real-network-200 | 1475 | `63af09891b6be8ad1a42` | 0.86 s |

## 三、安全不变量

| 不变量 | 成立 |
|---|---|
| `offline_index_unchanged` | 是 |
| `never_blocks` | 是 |
| `risk_capped_at_S3` | 是 |
| `audit_fields_present` | 是 |
| `real_network_license_fetched` | 是 |

## 四、与已有证据的关系

- `license-grounding-eval-20261115.*`（18/18，offline-fixture）：证明分类逻辑、失败可审计、端到端链路正确且完全可复现，**不代表联网成功率**。
- `webprobe-eval-20261115.*` / `llmfusion-round1/2-*`：真实联网评测，成功检出均为 `web:llm-inferred`，`license_verified_rate 0/2`；**本文件不修改该结论**。
- 本文件（hybrid-real-network-grounding）：补上一次**真实网络原文拉取**并成功升级为 `web:license-text-verified` 的用例，把「通道已实现」推进到「通道在真实原文上可核验」。

三者口径不同，引用时必须分别标注，不得合并成一个成功率。

## 五、局限

- 仅 1 个上游仓库（itsdangerous，LICENSE.txt → BSD-3-Clause），样本量为 1，不推断总体成功率。
- 网络经本机代理，其它候选 URL 在本次试验中出现 502 / 超时，均已记录在轨迹中并按失败回退处理。
- 提案环节仍是夹具，因此本用例不能支撑「AI 联网提案有效」的结论；该结论仍以 round2 的比率口径为准。
