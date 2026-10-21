# HumanEval 独立实现干净负例（164 例）

- 样本：164（clean 164 / copied 0）
- 生成时间：2026-10-20T09:43:56Z
- 判定阈值：fail_on=S3,S4，min_span_prob=0.55
- 数据集：OpenAI HumanEval canonical solutions, master branch snapshot（MIT；SHA-256 `b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef`）
- 来源：https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz

## 汇总

| 指标 | 数值 |
|---|---|
| 干净样本阻断级误报 | 0 / 164（0.00%） |
| 干净样本误阻断率 95% 单侧上限 | 1.81% |
| 干净样本出现任意命中 | 1 / 164 |
| 干净样本出现 S2 及以上 | 0 / 164 |
| 片段总数 / 命中片段 | 320 / 3 |
| 单样本耗时 p50 / p95 / max | 19.9 / 164.0 / 329.3 ms |

## 风险分布（命中条数）

| S0 | S1 | S2 | S3 | S4 |
|---|---|---|---|---|
| 1 | 1 | 0 | 0 | 0 |

## 未通过样本

无。

## 说明

- 本评测只覆盖清单中的样本与当前语料；未出现的语言、项目或生成方式不受此结果保证。
- 干净样本 0/164 出现阻断级误报；单侧 95% Clopper-Pearson 上限 1.81%。
