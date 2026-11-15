# 联网溯源边际收益评测（需与 round2 合并阅读）

- 生成时间：2026-11-15T01:17:10Z；每例试验数：2；安全不变量：held on all 4 trials
- 问题：离线引擎只能 attest 已 shipped 语料；本评测度量联网通道对**语料外**复制的边际检出。
- 样本量小、4 例中有 2 例跳过，**本文件不足以单独支撑"AI 必要性"结论**；配合
  `llmfusion-round2-realprojects.json`（5 次试验/例）才能得到完整比率口径。

| 项目（语料外） | 目标许可证假设 | 离线检出上游 | 联网检出 | 许可证文本核验 | 最高风险 | 置信度 |
|---|---|---|---|---|---|---|
| ranger | LicenseRef-Proprietary | 0/2 | 1/2 | 0/2 | S3 | 0.997 |
| itsdangerous | MIT | 0/2 | 1/2 | 0/2 | S1 | 0.995 |
| toml | MIT | — | 跳过（查询拉取失败） | — | — | — |
| synapse | LicenseRef-Proprietary | — | 跳过（查询拉取失败） | — | — | — |

> "目标许可证假设"是评测时设定的目标侧最坏情形（ranger 实际为 GPL-3.0、itsdangerous 为
> BSD-3-Clause），**不是**上游项目的许可证；不要据此读出上游许可结论。

## 解读

- 离线检出上游为 0 而联网检出 >0 的行，即 AI 通道带来的**边际收益**：这些来源不在本地语料内，规则/指纹原理上无法检出，联网溯源把它们纳入同一套确定性验证。本表只有 ranger、itsdangerous 两行出现该收益，且各为 1/2。
- 联网命中仅作补充提示（封顶 S3、不阻断）；许可证优先用上游 LICENSE 文本确定性核验（web:license-text-verified），失败回退模型推断（web:llm-inferred）。**本轮该核验通道未触发成功**：`license_verified_rate` 为 0/2、0/2，两次成功检出试验的 `license_source` 均为 `web:llm-inferred`，因此不得据本文件宣称"许可证已由 LICENSE 原文核验确认"。

## 局限（如实披露）

- 候选上游由大模型推断，召回受提案质量与网络可用性影响，故以多次试验的比率报告，不承诺单次必中；toml、synapse 两例因查询拉取失败被跳过，不构成 0 检出的有效观测。
- 拉取仅限公开 https raw 白名单、限额限时、防跳转；任何拉取原文仍须通过精确验证才成为发现，不引入误报。
- 本通道不修改语料、索引与离线结论；每次试验前后离线判定逐字节一致。
- 与 `llmfusion-round2-realprojects.json` 合并后的完整口径：4 个语料外项目离线检出上游 0 例；联网 ranger 5/5、itsdangerous 5/5 稳定检出，toml 0/5、synapse 1/5 未稳定检出；ranger 有 3/5 次 `top.package` 记为 `web-source/UNKNOWN`（按拉取 URL 归属上游）。不宣称 4 例全部 0.99+ 命中。
