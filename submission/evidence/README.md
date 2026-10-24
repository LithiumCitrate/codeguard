# 佐证材料（可直接附在提交里）

| 文件 | 说明 |
|---|---|
| `feature_flags.provenance.json` | 出处证书实例：取 mercurial（GPL-2.0-or-later）`contrib/automation/automation.py` 的前 2 个顶层定义（57 行）做**全局标识符重命名**后，被 `codeguard scan` 判定 8/10 片段命中、置信度 0.994、覆盖率 0.80、风险 S4（incompatible）；含逐片段行号区间、最长逐字 token 命中（32）、四层精确 Jaccard 与 12 维特征 |
| `feature_flags.cdx.json` | 同一次扫描的 CycloneDX 1.6 SBOM，`components[].evidence.occurrences` 给出 `文件#行区间` —— 传统 SCA 看不见的内联复制 |
| `feature_flags.report.html` | 自包含离线报告（无外链、无外部资源），双击即可打开；含许可证义务清单与 AI 使用声明 |
| `web-demo.sarif.json` | 同一次网页扫描的 SARIF 2.1.0 文档，走 CLI 真实路径产出并用 OASIS 官方 Schema 校验通过（4 条规则 CG001–CG004、1 条 result）；校验命令 `python scripts/validate_sbom.py`，schema 放 `release/schema/`（不随作品分发） |
| `benchmark-20261020.json` | 收紧阻断佐证（逐字≥10、置信度≥0.75）后的重跑原始结果：99% 检出、阻断召回 100%、负例 0/9 |
| `benchmark-20261020.md` | 同一次重跑的完整表格；用于确认真实仓库修复没有牺牲变异召回 |
| `humaneval-20261020.json` | 外部干净负例原始结果：HumanEval 164 个独立实现，0 个阻断级误报，1 个文件出现非阻断候选；含每样本风险、耗时、片段数与数据源 SHA-256 |
| `humaneval-20261020.md` | 同一次外部评测的可读汇总（误阻断率 0/164、95% 单侧上限 1.81%、风险分布、失败样本） |
| `realworld-github-20261020.json` | 10 个真实 GitHub 项目 / 12 个扫描集合 / 447 文件的原始结果：320 条候选、0 条阻断、18 条 S2、50 条真实 vendoring 命中、每仓库 commit 与耗时 |
| `realworld-github-20261020.md` | 同一次真实仓库扫描的可读汇总，含回归案例：通用 argparse 样板曾误阻断 GPL，修正后降为 S2 |
| `model-leak-20261021.json` | **真实模型泄漏正例**原始结果：LiCoEval（ICSE 2025）公开的 47 条 GPT-4o 真实生成代码，在同一索引（4,187 个带许可原文 / 753 项目 / 67,041 片段）上的逐条检出、归因、真源排名、逐字命中、置信度与耗时；含 200 个真实文件的同索引对照 |
| `model-leak-20261021.md` | 同上可读汇总：出现任意命中 47/47；文件级归因 36/47（95% 单侧下限 64.2%）、项目级 39/47、top-1 21/47；copyleft 子集阻断 6/6（GPL-3.0-or-later→S4、MPL-2.0→S3）；对照 7/200 阻断逐条列出，经核查为跨仓库真实复制，不作误报率结论 |
| `realworld-github-20261024-v051.json` | v0.5.1 复测：25 个高星项目（pip/setuptools/pytest/sqlmap/mitmproxy/ansible/yt-dlp/black/mypy/rich/scrapy/celery/sphinx/httpie/localstack/streamlit/salt/datasets/openai-python/freqtrade/airflow/keras/pandas/numpy/aiohttp + 2 个 _vendor 集合）/ 1119 文件：首轮 11 条假阻断经佐证规则修复（任何阻断路径要求 ≥10 逐字 token）后 **0 阻断**、56 条真实 vendoring 命中保留、8 类变异阻断召回 100% |
| `realworld-github-20261024-fresh.json` | **独立复测（非回归集）**：5 个此前未测过的仓库 jinja/starlette/typer/pyinstaller（GPL-2.0-or-later）/gin（Go，走通用词法）/ 168 文件 / 263 条发现 / **0 阻断**；`eval_realworld.py --add NAME:OWNER/REPO:SPDX[:ROOT][:exts=go,c]` 可供第三方自选仓库复测 |
| `model-leak-20261021-标注表.md` | 47 条正例的双人标注**人读总表**：A 真实逐字复现 / B 惯用巧合 / C 待复核；只含摘要与指标，不含第三方源码 |
| `model-leak-20261021-标注表-标注人1.csv` / `-标注人2.csv` | 两份**独立盲标记录**（已完成）：邢志鹏、王宇卓各填 47 行，无空标签，B/C 均带理由；客观列由脚本预填，未改动 |
| `model-leak-20261021-复核.csv` | 3 条分歧的第三人复核记录（复核人：队长艾倏然，2026-10-25），含逐条理由 |
| `model-leak-20261021-标注说明.md` | 标注口径 A/B/C、60–90 分钟流程、跨项目副本/注释/短片段边界、许可与隐私要求；明确“不得把空值当 A、不得把论文标签冒充双标” |
| `model-leak-20261021-标注汇总.md` | `merge_annotations.py` 生成：一致 44/47（93.6%）、Cohen's κ=-0.0292（分布偏斜所致）、3 条分歧已复核、**最终独立确认 A 47/47**；含逐条记录与可写入报告的句子 |
| `model-elicit-20261021.json` | 自有语料诱发试点原始结果：6 条按任务提示由模型凭记忆生成的回答（提示词见 `scripts/elicitation_prompts.jsonl`） |
| `model-elicit-20261021.md` | 同上的阴性结论：6 条回答与自有 copyleft 语料 **0 片段命中**，因此这一组不构成正例；读数解释与扩大路径写在文末，标注表供采集完成后填写 |

> 不会用 CSV 的队友可用 `annotate.html`（`python scripts/make_annotation_kit.py` 生成，zip 在 `scratch/CodeGuard-annotation-kit.zip`）：
> 只点 A/B/C 并导出 CSV，导出格式与本目录 CSV 一致；队长仍可用 `merge_annotations.py` 交叉校验。
> 工具包含第三方原文，只队内传阅，不要上传、截图或转发 `annotate.html`。

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
python scripts/eval_model_leak.py                                   # 真实模型泄漏正例（LiCoEval，按 URL+SHA-256 获取）
python scripts/eval_model_elicitation.py                            # 自有语料诱发试点（回答放在 .codeguard/external/elicitation/responses）
python scripts/make_annotation_packet.py                            # 生成 47 条盲标对照包 + 两份空白 CSV（对照包含第三方原文，只写 .codeguard/）
python scripts/make_annotation_kit.py                               # 打包队友开箱即用的 annotate.html 工具包（zip 写到 scratch/）
python scripts/merge_annotations.py --allow-blank                   # 检查模板；两份 CSV 填满后去掉 --allow-blank 生成正式汇总
python scripts/validate_sbom.py                                     # CycloneDX 1.6 + SARIF 2.1.0 官方 Schema 校验（schema 放 release/schema）
sh scripts/record_demo.sh                                           # 录屏用一键流程
```

> `model-leak-*` 使用的是 **LiCoEval**（Xu/Gao/He/Zhou, ICSE 2025, arXiv:2408.02487，仓库
> `osslab-pku/LiCoEval`，AGPL-3.0-or-later，commit `cfa26b4e5f108cccb49209f08c36f65d0b3bb658`）：
> 它同时提供模型真实输出与该输出命中的开源原文及逐文件许可，因此正例不需要我们自己伪造。
> 数据集只在本地按 URL+SHA-256 取用，原文与模型输出都不写入仓库、不进入产品索引、不随作品分发；
> 证据文件里只有摘要（SHA-256）、命中指标与许可。评测索引由数据集自带的参考原文临时构成，
> 所以这组数字衡量的是**检出与归因**，不是覆盖率上限（协议与限制写在 md 末尾）。

> `humaneval-*` 是**外部评测**：它回答“独立实现会不会被误阻断”，与变异基准的“改写后能否抓到”
> 互补。HumanEval 数据集不随仓库分发；脚本按 URL + SHA-256 获取，结果中的 0/164 只能表述为
> “0 观测 + 95% 单侧上限 1.81%”，不能写成“零误报”。`realworld-*` 是真实仓库采样，
> 不是全仓审计；仓库只作本地评测，不随作品分发。

## 用户试用材料（`submission/`）

| 文件 | 说明 |
|---|---|
| `12-用户试用执行说明.md` | 30 分钟试用流程、准备清单、记录规范、报告写法与“不得代填”底线 |
| `12-用户试用反馈表-试用者1.md` / `-试用者2.md` | 两份由**非项目成员**本人填写的记录表：任务 1–9、卡点原话、S0–S4 理解、开放问题、签名/日期；团队只补观察记录 |
| `12-用户试用反馈汇总.md` | 两份原始表的汇总模板：完成数、耗时、主要卡点、是否愿意继续使用、可引用原话；填完后再写报告 §1/§5 |

> 试用反馈必须由试用者本人填写；团队可以记录观察和提示次数，但不能代填、诱导或改写原话。
> 若最终只有 1 人完成，报告写“1 人小规模试用”，不要写成 2 人；不要把课程/社团同学写成企业试点。
> 两份原始表、匿名化截图和计时记录是最低配套；只有汇总表而没有原始表，评委会追问证据链。
