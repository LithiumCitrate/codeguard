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

## v0.4

- Java / JavaScript / C normalizer，复用四层视图与检索层；
- 每语言至少 10 个包的语料与等价变异基准。

验收：每语言 8 类变异检出率、负例误阻断率与 Python 基线同表报告；
跨语言移植仍明确标为非目标。

## v0.5

- 项目级合规策略文件 `--policy`；
- 许可证义务档案升级为逐条条款引用。

验收：义务判定用例 ≥60 组；策略文件可解释、可审计、可回滚。

## 社区与维护

- 许可证义务档案做成可共享数据集；
- 向 SBOM 生态提交“内联证据字段”的用例说明；
- 每季度更新 SPDX 快照与语料清单；
- CI 常跑测试、自扫描与 SARIF 上传，保持退出码契约不破坏。

## 明确不做

- 不把 CodeGuard 包装成法律意见或侵权判定；
- 不引入运行期第三方依赖、GPU 或 API Key；
- 不把未经验证的真实模型样本、用户反馈或企业部署写成已完成事实。
