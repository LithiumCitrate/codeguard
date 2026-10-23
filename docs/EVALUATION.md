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

## 6. 真实 GitHub 项目扫描（2026-10-24，25 高星项目）

HumanEval 是算法题解，仍不等于真实仓库。为了看"真实工程代码会不会被误阻断"，选了
**25 个高星公开项目**（pip、setuptools、pytest、sqlmap、mitmproxy、ansible、yt-dlp、black、
mypy、rich、scrapy、celery、sphinx、httpie、localstack、streamlit、salt、datasets、
openai-python、freqtrade、airflow、keras、pandas、numpy、aiohttp），加上 pip/setuptools 的
`_vendor` 目录，共 27 个扫描集合：

| 指标 | 结果 |
|---|---|
| 采样/成功扫描 | 1119 / 1119 个生产文件 |
| 候选发现 | 2098（S0 1590 / S1 59 / S2 417 / S3 0 / S4 0，修复后复测） |
| 阻断级发现 | **0**（修复后复测） |
| 真实 vendoring 命中 | **56**（pip-vendor 30、setuptools-vendor 26） |
| 单文件耗时 p50 / p95 | 约 40 / 1400 ms |

方法：每个仓库按相对路径的 SHA-256 排序取前 N 个 900 B–90 KB 的 `.py` 文件，排除
tests/docs/examples；目标许可证取仓库 LICENSE，使用方式 `distribution`；vendor 目录只在
`*-vendor` 集合中显式扫描。仓库以浅克隆放在 `.codeguard/github/`（gitignored），
不进入索引、不随作品分发；证据只保留 commit、路径、许可证与发现，不保存仓库源码。
与 0.5.0 语料重复的仓库（requests/flask/fastapi/httpx/django/pydantic 等）从无关清单中排除。

**两轮真实扫描各暴露并修复了一个真实缺陷**：

1. 2026-10-20（10 项目/447 文件）：setuptools 的 vendored wheel CLI 与 mercurial CLI 共享
   argparse 样板（6 片段/22% 覆盖/5 token 逐字/置信度 0.671）误触 GPL 阻断 → 结构分支要求
   逐字 ≥10 token。
2. 2026-10-24（25 项目/1119 文件，v0.5.0 语料）：首次运行出现 **11 条假阻断**（import 名单、
   argparse 链、0x 常量表、paramiko 小文件片段、re-export 名单、惯用 mixin），全部经由
   "置信度 ≥0.75 即可阻断"通道——语料扩充重训后模型分数漂移，该通道失去防线 →
   **任何阻断路径都要求 ≥10 个逐字 token**，长逐字通道另要求源覆盖率 ≥10%。
   11 条 (spans, coverage, verbatim, confidence) 四元组固化为回归测试；修复后变异基准
   8 类阻断召回保持 100%，真实扫描 0 阻断。

**边界**：这是仓库采样，不是全仓审计或用户试用；vendoring 命中是"真实复制"而非违规结论；
真实模型泄漏正例仍需单独收集。复现：`python scripts/eval_realworld.py`，原始结果见
`submission/evidence/realworld-github-20261024-v051.*`（2026-10-20 口径保留作历史）。
