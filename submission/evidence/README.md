# 佐证材料（可直接附在提交里）

> **口径分区（请先读）**：本目录同时保留**当前口径**与**历史口径**证据，避免把两代数字读成两个结论。
> - 当前口径（2026-11-25 优化复测）：`benchmark-20261125.*`、`benchmark-fullcorpus-20261125.*`、`humaneval-20261125.*` → 8 类变异 **98%**（`partial` 79%→88%）、全语料 **97.9%**（+IDF 97.4%）、`--fp-study 200` 误阻断 **0/200**、HumanEval **0/164**（p50 26.4 ms）、离线回归 **208 项**。
> - 2026-11-15 复测基线：`benchmark-20261115.*`、`benchmark-fullcorpus-20261115.*` → 优化前 97% 检出（`partial` 79%）、离线回归 202 项。
> - 历史口径（2026-10-20/24）：`benchmark-20261020.*`、`realworld-github-20261020.*` 等 → 当时的 99% 检出、447 文件扫描等，仅作版本迭代对照，**不作为当前效果结论**。
> - 联网层：`webprobe-eval-20261125.*` 为 2026-11-25 修补后 6 项目真网评测（**11/12 检出、11/11 `web:license-text-verified`**）；`webprobe-eval-20261115.*`、`llmfusion-round1/2-*.json` 为修补前真实联网基线；`license-grounding-eval-20261125.*` 为**离线夹具**评测，两者不可混用（见文末口径说明）。

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

## llmFusion 增量证据（本包新增，main 包没有）

> 离线核心未改动，上文 41 个离线证据仍然有效；以下 8 个文件证明**可选联网层**的边际收益与安全边界。

| 文件 | 说明 |
|---|---|
| `webprobe-eval-20261115.json` / `.md` | **边际收益评测**：对语料外真实 GitHub 文件做 2 次试验/例，每次"离线基线→联网溯源→离线复核"。硬断言离线判定前后逐字节一致、联网不阻断、封顶 S3、审计字段齐全、宽松许可不过度定级。表格如实给出：ranger 1/2、itsdangerous 1/2 检出，toml、synapse 因查询拉取失败跳过，`license_verified_rate` 均为 0/2；单点拉取失败记为跳过不中断。注意本评测样本量小且有 2 例跳过，**不足以单独支撑"AI 必要性"结论**，需与 round2 合并阅读 |
| `llmfusion-round1-realgithub.json` | 第一轮真实 GitHub 用例：minio(AGPL 原文复制→S4 阻断)、git(GPL 改名→S4)、itsdangerous(语料外→不阻断)、pip(vendored urllib3→S1 署名)；含联网深挖与联网追问的检索轨迹 |
| `llmfusion-round2-realprojects.json` | 第二轮真实**浅克隆**项目（ranger/itsdangerous/toml/synapse，非内置 demo），5 次试验/例：离线检出上游均为 0；联网检出 ranger 5/5、itsdangerous 5/5（itsdangerous 0.995；ranger 4/5 次 0.997、1 次 0.3805，48 逐字为主），**toml 0/5、synapse 1/5 未稳定检出**；ranger 有 3/5 次 `top.package` 记为 `web-source/UNKNOWN`（按拉取 URL 归属上游，非模型给出的包名）。20 次试验安全不变量全部成立；密钥零泄漏。本文件记录中**没有** `web:license-text-verified` 成功样本 |
| `eval_llmfusion_round1.py` / `eval_llmfusion_round2.py` | 上述两轮的可复现脚本（密钥经环境变量传入，不写盘）；round2 为多试验比率口径 |
| `workbench-webprobe.png` | 工作台"联网溯源"卡片截图：语料外命中、上游原文 sha256、许可证文本核验/模型推断标注、检索轨迹（风格与 main 一致） |
| `workbench-deeptrace.png` | 逐命中"联网深挖"卡片截图：检索轨迹与来源链接 |
| `license-grounding-eval-20261115.json` / `.md` | **核验通道离线可复现评测（2026-11-15 新增）**：`mode=offline-fixture`，无需网络/密钥。11 个 SPDX 签名分类 + 5 个 `ground_license` 行为（LICENSE 成功、仅 COPYING 存在、全部拉取失败、文本无法识别、同仓库缓存复用）+ 2 条端到端 webprobe 路径，共 **18/18 通过**。用于证明修补后的核验通道逻辑、失败审计与端到端链路可复现；**不代表真实联网核验成功率** |
| `eval_license_grounding.py` | 上述评测的可复现脚本（`python 佐证材料/eval_license_grounding.py`），纯标准库、离线、无密钥 |

复现联网层评测（需环境变量 `CODEGUARD_LLM_BASE_URL/API_KEY/MODEL` + `CODEGUARD_TAVILY_API_KEY`）：

```bash
python scripts/eval_webprobe.py --trials 3        # 仓库内固化评测 -> submission/evidence/webprobe-eval-<date>.{json,md}
python 佐证材料/eval_llmfusion_round2.py           # 多试验真实克隆项目基准（需先 git clone 对应仓库）
```

复现核验通道（**无需网络、无需任何密钥**，评委可直接跑）：

```bash
python scripts/eval_license_grounding.py
# 或直接用提交包内脚本：python 佐证材料/eval_license_grounding.py --out-dir /tmp/cg-eval
```

> 联网溯源只增加召回、不引入误报：拉取原文仍须通过与本地语料相同的精确验证才成为发现；
> 命中仅作补充提示（封顶 S3、不阻断），许可证优先用上游 LICENSE 文本确定性核验
> （`web:license-text-verified`），失败回退模型推断（`web:llm-inferred`）并提示人工确认。
>
> **口径说明（2026-11-15 修订）**：上述核验通道已在 `web_evidence.py` 实现，但在本目录留存的
> 全部评测 JSON 中**从未触发成功**——`web:license-text-verified` 字样 0 次出现；webprobe 轮成功检出
> 试验的 `license_source` 均为 `web:llm-inferred`（round2 JSON 未记录该字段）。因此本包只主张"通道已实现、失败可回退并标注"，
> **不主张**"许可证已由 LICENSE 原文核验确认"。同理，联网召回按多次试验比率如实报告
> （ranger/itsdangerous 稳定，toml/synapse 不稳定），不写成 4 例全部 0.99+ 命中。
> 架构、安全保证与局限见仓库 `docs/WEBPROBE.md`。
>
> **2026-11-15 修补（不改变上述 0/2 口径）**：事后核查确认两个上游 LICENSE 文件均存在、
> 分类逻辑与 URL 拼接均正确，0/2 的根因是旧版 `ground_license` 任何失败都静默返回 `{}`，
> 且每条 finding 重复拉取同一 LICENSE、候选文件名只试 3 个、复用 20 秒完整超时。
> 已修补为：失败也返回可审计字典并把 `status`/`reason`/逐 URL `attempts` 写入
> `provenance.license_grounding`；候选文件名扩至 9 个（含 `COPYING`）；一次 probe 内按仓库共享缓存；
> LICENSE 拉取独立 8 秒超时。新增离线夹具评测 `license-grounding-eval-20261115.*`（18/18）验证通道逻辑。
> **该评测为 offline-fixture，不能换算成真实联网 `license_verified_rate`；真实联网仍为 0/2，
> 需在稳定网络下重跑 `eval_webprobe.py` 才能更新。** patched 版本会把每次失败原因写入证据，
> 使下一次补跑可定位、可归因。


---

## 2026-11-15 补充证据（③ / ④）

本批证据为半决赛复评中「③ AI 必要性缺少量化对照」与「④ κ 负值引发标注可信度疑问」两项的修复，
全部由仓库脚本从原始证据离线重算，未改动任何原始标签或评测结果。

| 证据 | 内容 | 复现脚本 |
|---|---|---|
| `judge-ablation-20261115.json` / `.md` / `eval_judge_curve.png` | 规则回退 vs 12 维逻辑回归的配对级 PR 与阈值曲线；20,159 个候选对、与基准同种子同语料、使用出厂模型 | `scripts/eval_judge_curve.py --root <repo>` |
| `annotation-agreement-20261115.json` / `.md` | 47 条双人盲标 2×2 混淆矩阵、κ 悖论解释、PABAK 0.8723 / Gwet's AC1 0.9320、2000 次 bootstrap CI | `scripts/eval_annotation_agreement.py` |

**③ 口径边界（必须随数字一起引用）**：单位是（片段, 候选原文）**配对**，不是文件。
规则回退 AUC 0.9628、模型 0.9617，**模型并未提高排序上限**；差异在工作点——
生产阈值 0.55 下规则回退 P/R/F1 = 0.9778 / 0.6545 / 0.7841，模型 = 0.9529 / 0.8696 / 0.9093。
如实说明：规则回退把阈值手工下调到 0.25 亦可达最佳 F1 0.9263（模型 0.9145 @0.45），
因此 AI 的价值是「可学习、可校准的组合器把工作点固定在出厂阈值」，不是「更高检出率」。
文件级检出在两种打分下同为 97%，门禁由佐证规则兜底。

**④ 口径边界**：AC1 / PABAK 只衡量**评分者间信度**，不衡量标签是否正确；
正确性仍由逐字命中、覆盖率与第三人复核支撑。κ = -0.0292 属高一致率 / 低 κ 悖论
（47 条为预筛正例，A 类边际 0.968，Cohen 期望一致率 0.938 > 实际 0.936），该系数在此不适用，
不再单独引用。

**llmFusion 额外证据**：

| 证据 | 内容 | 复现脚本 |
|---|---|---|
| `license-grounding-realnetwork-20261115.json` / `.md` | 混合模式真实网络核验：提案为离线夹具，上游 LICENSE 原文走真实公网；真实拉取 `pallets/itsdangerous/main/LICENSE.txt`（SHA-256 已留存），确定性识别 BSD-3-Clause，`run_web_probe` 端到端触发 `web:license-text-verified`，安全不变量全成立 | `scripts/eval_license_grounding_realnetwork.py` |

> 该用例样本量为 1，**不改写** `webprobe-eval-20261115.json` 与 `llmfusion-round2-realprojects.json`
> 中真实联网 `license_verified_rate 0/2` 的历史口径，也不代表完整联网 webprobe 的成功率。
> 与 18/18 的纯离线夹具评测 `license-grounding-eval-20261115.*` 三者口径不同，不得合并成一个成功率。
