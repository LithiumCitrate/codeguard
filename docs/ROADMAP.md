# Roadmap

每条计划都带可核验的验收判据；没有判据的条目不进路线图。

## v0.2（已交付，2026-10-20）

- 外部评测命令 `codeguard eval`：JSONL 清单、干净/复制分组、误阻断率、
  单侧 Clopper-Pearson 上限、耗时分位；
- HumanEval 164 个独立实现：0 阻断，95% 单侧上限 1.81%；
- 10 个真实 GitHub 项目 / 447 个生产文件：0 阻断、50 条真实 vendoring；
  据此修复 argparse 样板误阻断与行号映射缺陷；
- SARIF 2.1.0：`scan --format sarif` / `gate --sarif`，GitHub Code Scanning；
- 107 个离线测试；技术报告、PPT、网页版、证据同步更新；真实模型泄漏正例已用外部公开数据集 LiCoEval 完成检出与归因评测。

证据：`submission/evidence/humaneval-20261020.*`、
`submission/evidence/realworld-github-20261020.*`、`docs/EVALUATION.md`、
`docs/INTEGRATIONS.md`。

## v0.3

- 增量索引：追加/剔除文档不重建；
- `partial`（只截取部分定义）检出改善：重叠窗口 + 边界回溯。

验收：192 个变异用例检出 ≥99.5%；索引更新 <5 s；回归测试全绿。

## v0.4（多语言语法感知与离线基准 · 已交付，2026-11-25）

- C / Go / JavaScript / Rust 语法感知词法、角色与定义边归一化（`normalize.py`），复用四层视图与检索层；
- 离线多语言基准 `scripts/eval_multilang.py`（32 份真实语料 × 4 变异 + 61 负例）：文件级 **96.9%**（124/128）、同包级 **100%**（C/JS/Rust 均 100%，Go 文件级 87.5% / 同包级 100%）、**0 误阻断**（`submission/evidence/multilang-eval-20261125.*`）。
- 跨语言移植（同一算法 Python→Go）仍明确标为非目标。

## v0.5（项目级合规策略 `--policy` · 核心已交付，2026-11-25）

- 项目级合规策略文件 `--policy`（`src/codeguard/policy.py`）：支持 `project_license`、`usage`、`fail_on`、`allow_packages`（豁免降级 S1 留痕，不删发现）与 `deny_licenses`（佐证后升 S4 阻断），审计轨迹写入 JSON/HTML/SARIF，回归测试全绿（216 项）；
- 后续持续完善：许可证义务档案升级为逐条条款引用、增量索引。

## 社区与维护

- 许可证义务档案做成可共享数据集；
- 向 SBOM 生态提交“内联证据字段”的用例说明；
- 每季度更新 SPDX 快照与语料清单；
- CI 常跑测试、自扫描与 SARIF 上传，保持退出码契约不破坏。

## 明确不做

- 不把 CodeGuard 包装成法律意见或侵权判定；
- 不引入运行期第三方依赖、GPU 或 API Key；
- 不把未经验证的真实模型样本、用户反馈或企业部署写成已完成事实。
