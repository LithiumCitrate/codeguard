# 外部评测：独立实现干净负例

变异基准回答的是“已知来源的代码被改写后还能不能抓到”。它回答不了另一个同样重要的问题：
**一段没有从语料库复制而来的代码，会不会被误判为污染？** 本页说明后者的评测方法、
结果和边界。原始数据见 `submission/evidence/humaneval-20261020.json` 与同名 Markdown。

## 1. 为什么要单独测干净样本

合规门禁的两种错误代价不同：漏报会让带义务的代码进入产品；误阻断会让开发者绕过工具、
不再信任门禁。只用变异正例训练和评估，无法给出误阻断证据。项目因此增加了一个
**独立实现干净负例集**，并用产品原路径（含模型、阈值和佐证规则）扫描。

## 2. 数据集与许可

| 项 | 值 |
|---|---|
| 数据集 | OpenAI HumanEval canonical solutions |
| 用途 | 仅作为干净负例扫描；**不进入索引、不随仓库分发** |
| 样本数 | 164 |
| 许可 | MIT |
| 数据 SHA-256 | `b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef` |
| 获取方式 | `python scripts/eval_humaneval.py`（按 URL + SHA-256 校验） |

HumanEval 的 canonical solution 是独立编写的 Python 函数，不是本项目语料的变异体，
也不是某个大模型的输出。用它测“误阻断”是合理的；它**不能**替代真实模型泄漏样本，
报告和答辩中不应把它写成“真实 AI 生成代码”。

## 3. 复现

```bash
# 需要已有语料与索引（约 585 文档 / 36k 片段）
codeguard corpus && codeguard index
python scripts/eval_humaneval.py
```

脚本会下载/校验数据集，生成临时 JSONL 清单，调用 `codeguard eval`，并把汇总写到
`submission/evidence/humaneval-YYYYMMDD.{json,md}`。数据集缓存在 `.codeguard/external/`，
该目录已被 `.gitignore` 排除。

也可以评测自己的清单：

```bash
codeguard eval --manifest my-samples.jsonl --out .codeguard/eval
```

清单每行一个 JSON 对象：

```json
{"id":"clean-1","label":"clean","language":"python","license":"LicenseRef-Proprietary","code":"def f():\n    return 1\n"}
{"id":"copy-1","label":"copied","path":"samples/copy.py","source_package":"requests","source_path":"requests/sessions.py"}
```

- `clean`：出现 `--fail-on` 等级（默认 S3/S4）的发现即记为误阻断；
- `copied`：指定 `source_package` / `source_path` 时统计归因率、阻断率与 top-1 来源正确率；
- 未指定来源的 `copied` 样本只统计阻断。

## 4. 结果（2026-10-20）

设置：目标许可证按最坏的 `LicenseRef-Proprietary` 假设，使用方式 `distribution`，
默认判定阈值与佐证规则。

| 指标 | 结果 |
|---|---|
| 干净样本 | 164 |
| 阻断级误报（S3/S4） | **0 / 164（0.00%）** |
| 误阻断率 95% 单侧 Clopper-Pearson 上限 | **1.81%** |
| 出现任意来源候选 | 1 / 164 |
| 出现 S2 及以上 | 0 / 164 |
| 片段总数 / 命中片段 | 320 / 3 |
| 单样本耗时 p50 / p95 / max | 约 20 / 170 / 340 ms |

唯一出现候选的是 `HumanEval/81`（GPA→字母等级的长 `if/elif` 链），命中
`snowballstemmer` 的两个词干处理文件。该样本与来源在“连续条件分支 + 字符串常量”
这一通用形状上相似，但语义无关；风险被定为 S1/S0（来源 BSD-3-Clause，进入
proprietary 目标仍属兼容），没有阻断。这个案例说明：
**相似 ≠ 复制，更 ≠ 许可冲突；门禁把“观察”和“阻断”分开是必要的。**

## 5. 统计解释与局限

- 0/164 不是“零误报”的证明。单侧 95% 上限 1.81% 的含义是：若真实误阻断率高于 1.81%，
  在 164 个独立样本中观察到 0 次的概率不超过 5%。报告应写“0 观测 + 上限”，不能写“0 误报”。
- 样本是 HumanEval 的独立实现，主要覆盖短函数、算法题和 Python；不代表真实仓库、
  长文件、JavaScript/TypeScript、生成式模型的完整输出分布。
- 目标许可证固定为 proprietary 是最坏假设；换成其他目标许可证，风险等级会变化。
- 语料只有 20 个包 / 585 个索引文件；未收录的来源无法被归因。
- 本评测不含真实模型泄漏正例；正例方向仍由受控变异基准覆盖。下一阶段应补充真实模型
  输出、人工双标注和跨项目留出。

## 6. 真实 GitHub 项目扫描（2026-10-20）

HumanEval 是算法题解，仍不等于真实仓库。为了看“真实工程代码会不会被误阻断”，又选了
10 个许可证多样的公开项目（requests、flask、fastapi、httpx、poetry、pip、setuptools、
pytest、sqlmap、mitmproxy），加上 pip/setuptools 的 `_vendor` 目录，共 12 个扫描集合：

| 指标 | 结果 |
|---|---|
| 采样/成功扫描 | 447 / 447 个生产文件 |
| 候选发现 | 320（S0 259 / S1 43 / S2 18 / S3 0 / S4 0） |
| 阻断级发现 | **0** |
| 真实 vendoring 命中 | **50**（pip-vendor 26、setuptools-vendor 24） |
| 单文件耗时 p50 / p95 / max | 182 / 1090 / 3717 ms |

方法：每个仓库按相对路径的 SHA-256 排序取前 N 个 900 B–90 KB 的 `.py` 文件，排除
tests/docs/examples；目标许可证取仓库 LICENSE，使用方式 `distribution`；vendor 目录只在
`*-vendor` 集合中显式扫描。仓库以浅克隆放在 `.codeguard/github/`（gitignored），
不进入索引、不随作品分发；证据只保留 commit、路径、许可证与发现，不保存仓库源码。

真实扫描暴露并修复了一个有效问题：setuptools 的 vendored wheel CLI 与 mercurial CLI
共享 argparse 样板，旧规则得到 6 片段、22% 覆盖率、5 token 逐字命中、置信度 0.671，
却触发了 GPL 误阻断。现在结构分支要求逐字 ≥10 token，置信度门槛提高到 0.75；
该案例降为 S2 复核，变异基准仍为 99% 检出、阻断召回 100%。

**边界**：这是仓库采样，不是全仓审计或用户试用；vendoring 命中是“真实复制”而非违规结论；
真实模型泄漏正例仍需单独收集。复现：`python scripts/eval_realworld.py`，原始结果见
`submission/evidence/realworld-github-20261020.json`。

## 7. 与变异基准的关系

| 评测 | 回答的问题 | 数据来源 | 主要指标 |
|---|---|---|---|
| 变异基准 | 改写后的已知来源还能不能抓到 | 自研确定性变异器 | 检出率、AUC/F1、阻断召回 |
| 外部干净负例 | 独立实现会不会被误阻断 | HumanEval（MIT） | 误阻断率 + 单侧上限 |
| 真实模型泄漏正例 | 模型真的复现了别人的代码，能不能检出并归因 | LiCoEval（ICSE 2025，AGPL-3.0-or-later） | 命中率、归因层级、copyleft 子集阻断 |

两者不能互相替代。对外材料应同时给出两侧结果，并明确数据来源、样本量和适用范围。

## 四点五、自扫口径（本产品扫自己）

`codeguard scan src/codeguard --license Apache-2.0` 退出码 **0**：28 个源文件、6 处命中
（5×S0、1×S2、0 阻断）。唯一的 S2 是 `license_intel.py` 与 mercurial
`contrib/packaging/hgpackaging/pyoxidizer.py`（GPL-2.0-or-later）在许可证表达式解析上的
结构相似，置信度 0.4335，低于阻断门槛，按流程转人工复核。披露它是因为“自扫 0 阻断”
容易被读成“自扫全绿”——本产品对自己的代码也会给出需要人看的提示。

## 五、真实模型泄漏正例（LiCoEval, ICSE 2025）

变异基准回答“改写过的来源还能不能抓到”，HumanEval 回答“独立实现会不会被误阻断”，
两者都没有回答 **“真实模型输出里是不是有别人的代码”**。这一侧不能由我们自己伪造，
所以改用第三方公开数据：LiCoEval（Xu/Gao/He/Zhou, ICSE 2025, arXiv:2408.02487）
发布了 GPT-4o 的真实生成代码、与之 striking-similar 的开源原文、逐文件许可证与
论文自身的相似度分数。仓库 `osslab-pku/LiCoEval` 为 AGPL-3.0-or-later，
commit `cfa26b4e5f108cccb49209f08c36f65d0b3bb658`。

```bash
python scripts/eval_model_leak.py            # 按 URL+SHA-256 取数，本地评测，不随作品分发
```

方法要点：

1. 把数据集自带的 **4,187 个带许可原文全部建成同一个评测索引**（753 个项目 / 67,041 片段），
   正例的真实原文只是其中一个文档 —— 归因必须在几千个干扰项里命中它；
2. 逐条扫描 **47 条 GPT-4o 真实输出**，目标许可证 MIT、使用方式 distribution
   （即“开发者把这段代码贴进自己的 MIT 项目并发布”）；
3. 归因分三层：文件级（预期项目+路径）、项目级（同项目不同窗口）、同摘要等效来源
   （同一段代码被别的项目复制走）；
4. 同索引对照：随机抽 200 个真实原文（排除其自身项目）扫描，看会不会阻断。

结果（`submission/evidence/model-leak-20261021.*`）：

| 指标 | 数值 |
|---|---|
| 出现任意命中 | 47 / 47 |
| 文件级归因 | 36 / 47（95% 单侧下限 64.2%） |
| 项目级归因 | 39 / 47（下限 71.4%） |
| top-1 / 真源进 top-3 | 21 / 47 ｜ 33 / 47 |
| copyleft 子集阻断 | 6 / 6（GPL-3.0-or-later→S4，MPL-2.0→S3） |
| 逐字命中 ≥20 token | 46 / 47（48 token 为窗口上限） |
| 单样本延迟 p50 / p95 / max | 97.4 / 363.8 / 1149.6 ms |
| 同索引 200 真实文件对照 | 阻断 7 条，逐条为跨仓库真实复制，不作误报率 |

必须这样引用，也只能这样引用：

- 41 条原文是 Apache-2.0/BSD-3-Clause/MIT，对 MIT 目标不产生许可证冲突，
  所以“阻断 6/47”只对这 6 条 copyleft 子集有意义，子集阻断是 6/6；
- 被检原文一定在索引内（构造性条件），因此这组数字衡量**检出与归因**，不衡量覆盖率上限；
- 8 条命中的是同一段上游代码的其它复制仓库（如 `tensorflow_models` 与
  `balancap_SSD-Tensorflow`），是否认定更强来源要人工标注，不能先替检测器记功；
- 被评模型与提示词由第三方论文固定，我们无法审计其训练数据；
- 数据集只在本地按 URL+SHA-256 使用，原文与模型输出都不写入仓库、不进入产品索引、
  不随作品分发；证据文件里只有摘要、指标与许可证。

自有语料上的诱发试点（`scripts/eval_model_elicitation.py`，6 条凭记忆生成的回答）
**没有任何片段命中**，如实记为阴性：既不能读成“模型不会泄漏”，也不能读成“检测器失效”。
把它变成正例需要可披露型号的公开对话模型与更多提示，采集协议与提示词已入库
（`scripts/elicitation_prompts.jsonl` + 标注表），由团队在提交前补齐。
