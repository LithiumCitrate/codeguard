# 佐证材料（可直接附在提交里）

| 文件 | 说明 |
|---|---|
| `feature_flags.provenance.json` | 出处证书实例：取 mercurial（GPL-2.0-or-later）`contrib/automation/automation.py` 的前 2 个顶层定义（57 行）做**全局标识符重命名**后，被 `codeguard scan` 判定 8/10 片段命中、置信度 0.994、覆盖率 0.80、风险 S4（incompatible）；含逐片段行号区间、最长逐字 token 命中（32）、四层精确 Jaccard 与 12 维特征 |
| `feature_flags.cdx.json` | 同一次扫描的 CycloneDX 1.6 SBOM，`components[].evidence.occurrences` 给出 `文件#行区间` —— 传统 SCA 看不见的内联复制 |
| `feature_flags.report.html` | 自包含离线报告（无外链、无外部资源），双击即可打开；含许可证义务清单与 AI 使用声明 |
| `benchmark-20261020.json` | 收紧阻断佐证（逐字≥10、置信度≥0.75）后的重跑原始结果：99% 检出、阻断召回 100%、负例 0/9 |
| `benchmark-20261020.md` | 同一次重跑的完整表格；用于确认真实仓库修复没有牺牲变异召回 |
| `humaneval-20261020.json` | 外部干净负例原始结果：HumanEval 164 个独立实现，0 个阻断级误报，1 个文件出现非阻断候选；含每样本风险、耗时、片段数与数据源 SHA-256 |
| `humaneval-20261020.md` | 同一次外部评测的可读汇总（误阻断率 0/164、95% 单侧上限 1.81%、风险分布、失败样本） |
| `realworld-github-20261020.json` | 10 个真实 GitHub 项目 / 12 个扫描集合 / 447 文件的原始结果：320 条候选、0 条阻断、18 条 S2、50 条真实 vendoring 命中、每仓库 commit 与耗时 |
| `realworld-github-20261020.md` | 同一次真实仓库扫描的可读汇总，含回归案例：通用 argparse 样板曾误阻断 GPL，修正后降为 S2 |

复现这三份产物（顺序即命令）：

```bash
codeguard corpus && codeguard index
codeguard benchmark --files 24 --fp-study 200 --out .codeguard/benchmark-20261020
python scripts/make_demo_sample.py                   # -> .codeguard/demo/feature_flags.py
codeguard scan .codeguard/demo/feature_flags.py --license MIT --usage distribution
python scripts/demo_gate.py --package paramiko --mutation compound   # 退出码 1
python scripts/false_block_control.py --sample 200                  # 对照组 3.5%
python scripts/eval_humaneval.py                                    # 外部干净负例（下载并校验 MIT 数据集）
python scripts/eval_realworld.py                                    # 真实 GitHub 项目（浅克隆，不随仓库分发）
sh scripts/record_demo.sh                                           # 录屏用一键流程
```

> `humaneval-*` 是**外部评测**：它回答“独立实现会不会被误阻断”，与变异基准的“改写后能否抓到”
> 互补。HumanEval 数据集不随仓库分发；脚本按 URL + SHA-256 获取，结果中的 0/164 只能表述为
> “0 观测 + 95% 单侧上限 1.81%”，不能写成“零误报”。`realworld-*` 是真实仓库采样，
> 不是全仓审计；仓库只作本地评测，不随作品分发。
