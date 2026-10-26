# CodeGuard · AI 生成代码的开源许可证污染溯源与合规门禁

> 大模型会把训练语料里的开源代码"背"出来。CodeGuard 负责回答三个问题：**这段代码来自哪个项目、哪个许可证、它能不能进入我们的产品**。
>
> 纯标准库实现，零第三方依赖，不需要 GPU、不需要 API Key，一条命令复现全部实验数据。

---

## 1. 它解决什么问题

| 场景 | 过去 | 用 CodeGuard |
|---|---|---|
| AI 补全"顺手"复制了 GPL 项目的实现，团队不知情 | 发布后被权利人主张，被迫回滚或开源全部代码 | CI 门禁在 PR 阶段阻断（退出码 1） |
| 依赖清单（SBOM）只记录包名，不记录"复制进源码的片段" | 许可证扫描器看不见内联复制 | 输出 CycloneDX `evidence.occurrences` + 行号 |
| 需要向法务解释"凭什么说这是抄的" | 截图 + 主观判断 | 逐片段证据链：多层相似度、IDF 加权覆盖率、最长逐字命中 token 数 |
| Copyleft 义务到底触发没有 | 靠人记忆 | SPDX 义务模型给出 compatible / conditional / incompatible + 义务清单 |

## 2. 三十秒上手

```bash
pip install .                      # 运行期零第三方依赖（构建 wheel 需要 setuptools，pip 会自动取）

codeguard corpus                   # 下载许可证多样的真实开源包作为知识底座
                                   # 版本按 src/codeguard/data/corpus_pins.json 锁定，保证语料可复现
PYTHONPATH=src python scripts/expand_corpus_github.py
                                   # 可选：再浅克隆 13 个 GitHub 仓库（C/Go/JS/Rust，
                                   # GPL-2.0/AGPL-3.0/LGPL-3.0/BSD/Apache/MIT/MPL）扩充到 1717 文件
codeguard index                    # 构建指纹索引（只存哈希与行号定位，不存源码）
codeguard benchmark --files 24     # 复现变异基准 + 消融实验，并训练判定模型
codeguard scan src/                # 扫描目录，输出 JSON / CycloneDX / 离线 HTML / SARIF
codeguard gate --diff pr.diff      # CI 门禁：阻断级风险返回 1；--sarif 供 Code Scanning
codeguard licenses GPL-3.0-only MIT --usage distribution   # 纯许可证推理
codeguard eval --manifest samples.jsonl --out .codeguard/eval  # 外部干净/复制样本评测
codeguard doctor                   # 自检：索引规模、参数、模型与 AI 使用声明

sh scripts/reproduce.sh            # 一条命令复现上面全部步骤 + 测试 + 门禁自检
python scripts/eval_humaneval.py   # 外部干净负例：下载并按 SHA-256 校验 HumanEval，生成证据
python scripts/eval_realworld.py   # 真实 GitHub 项目扫描（本地克隆，不随仓库分发）
```

未安装时可用 `PYTHONPATH=src python -m codeguard …` 等价调用。逐步讲解与真实输出见
[docs/TUTORIAL.md](docs/TUTORIAL.md)，算法与取舍见 [docs/DESIGN.md](docs/DESIGN.md)，
实验表格见 [docs/BENCHMARK.md](docs/BENCHMARK.md)。

## 3. 技术路线

```
                 ┌──────────── 第一阶段：检索（毫秒级，高召回）────────────┐
源码 → 语法无关归一化 → 四层不变性指纹 → MinHash + b-bit 压缩 → 分带 LSH
                 └──────────── 第二阶段：验证（只对候选执行）────────────┘
候选片段 → 回读语料原文 → 精确 Jaccard / IDF 加权包含度 / 最长逐字 token 命中
                 → 逻辑回归判定（或规则回退）→ 片段聚合 → SPDX 义务推理 → 风险分级
```

四层指纹各自抵消一类"洗代码"手法：

| 层 | 视图 | 对什么不变 |
|---|---|---|
| L1 字面 | 代码 token 序列 | 空白、注释、格式化 |
| L2 抽象 | 窗口内局部别名 + 字量分桶 | 变量重命名、常量微调 |
| L3 角色 | 标识符归约为 局部/内置/关键字 | 跨文件批量改名 |
| L4 结构边 | 调用/参数/绑定关系集合 | 语句与顶层定义重排 |

关键设计取舍（为什么别名表按窗口建立、为什么 b-bit 要校正、为什么 §13 独立于分发）
写在 [docs/DESIGN.md](docs/DESIGN.md) 与各模块首段 docstring 里。

## 4. 实测效果（`codeguard benchmark --files 24`）

**当前口径**：语料由 20 个 PyPI 包（585 文件）扩充为 **32 个来源 / 1717 个文件 / 138928 片段 / 11 种 SPDX**
（新增 13 个浅克隆的 GitHub 仓库：fastapi、django、git、nginx、minio、jquery 等，覆盖 C/Go/JS/Rust；
复现见 `scripts/expand_corpus_github.py`）。语料：24 个真实开源文件 / 18 个包 / 9 种 SPDX；192 个变异用例 + 9 个全新实现负例。

| 方法 | 检出率（文件级） | 误匹配来源/例 | 负例误报 |
|---|---|---|---|
| 整文件 SHA-256 | 12% | 0.00 | 0/9 |
| 归一化整文件哈希 | 28% | 0.00 | 0/9 |
| 归一化滑窗哈希（MOSS 式基线） | 53% | 0.00 | 0/9 |
| 仅字面层 L1 | 86% | 0.03 | 0/9 |
| 仅抽象层 L2 | 96% | 0.05 | 0/9 |
| 仅角色层 L3 | 97% | 0.02 | 0/9 |
| 仅结构边层 L4 | 97% | 0.09 | 0/9 |
| 多层，无 IDF | 97% | 0.02 | 0/9 |
| 多层 + IDF（规则打分） | 97% | 0.02 | 0/9 |
| **多层 + IDF + 判定模型（本产品）** | **97%**（8 类变异中 7 类 100%，仅截取部分定义 79%） | 0.02 | **0/9** |

判定模型（12 维特征逻辑回归，按来源文件分组留出 11 个文件）：留出集 **AUC 0.892 / precision 1.000 / recall 0.722 / F1 0.839**。
语料扩大 3.8 倍后跨包样板候选对显著变难，留出指标较 20 包时代（AUC 0.983 / F1 0.976）如实回落；
检索与验证层不受影响——文件级检出 97%、误匹配 0.02、负例 0/9，且门禁决策由佐证规则兜底而非模型置信度单独决定。
完整表格（含逐变异衰减曲线与特征权重）见 [docs/BENCHMARK.md](docs/BENCHMARK.md)。

门禁决策质量（`--fp-study 200`）：检出的变异用例中 **100%** 满足阻断佐证条件（阻断召回 = 检出率），而在 200 个互不相关的真实语料文件上跨包抽查的 **误阻断率 0%**（同批数据在没有佐证要求时为 3.5%）。

外部干净负例在扩语料后复测：HumanEval 164 个独立实现 **0/164 阻断（95% 单侧上限 1.81%）**，任意命中仅 2，扫描 p50 37.4 ms。

工程指标：1717 文档 / 138928 片段索引 34.4 MB（约 243 B/片段），buckets 2.94 M；50 k 字符真实文件扫描秒级。

### 4.1 外部干净负例（2026-10-20）

变异基准只覆盖“已知来源被改写”。为测误阻断，项目用 **HumanEval 164 个独立实现**作为
干净负例，走产品原路径（目标许可证按最坏的 `LicenseRef-Proprietary` 假设）：

| 指标 | 结果 |
|---|---|
| 阻断级误报（S3/S4） | **0 / 164（0.00%）** |
| 误阻断率 95% 单侧 Clopper-Pearson 上限 | **1.81%** |
| 出现任意来源候选 | 1 / 164（S1/S0，未阻断） |
| 片段总数 / 命中片段 | 320 / 3 |
| 单样本耗时 p50 / p95 | 约 20 / 170 ms |

唯一候选是 HumanEval/81 的长 `if/elif` 链命中 `snowballstemmer` 的词干处理文件：
形状相似但语义无关，风险 S1，未阻断。**0/164 只能写成“0 观测 + 上限”，不能写成“零误报”。**
HumanEval 是独立编写的算法实现，不是真实模型输出；真实模型泄漏正例已由 LiCoEval（ICSE 2025）
47 条 GPT-4o 真实输出补齐：47/47 命中、copyleft 子集阻断 6/6，并经双人独立标注与队长复核
（一致 44/47，最终确认 A 47/47），见 `submission/evidence/model-leak-20261021-标注汇总.md`。
方法与复现见 [docs/EVALUATION.md](docs/EVALUATION.md)，原始结果见
`submission/evidence/humaneval-20261020.json`。

### 4.2 真实高星项目扫描（2026-10-24，25 项目 / 1119 文件）

与变异基准互补的第三只眼：**25 个高星 GitHub 项目**（pip、setuptools、pytest、sqlmap、mitmproxy、
ansible、yt-dlp、black、mypy、rich、scrapy、celery、sphinx、httpie、localstack、streamlit、salt、
datasets、openai-python、freqtrade、airflow、keras、pandas、numpy、aiohttp，共 27 个扫描集合）
按各自真实许可证走产品原路径，确定性采样 **1119 个生产文件**：

| 指标 | 结果 |
|---|---|
| 采样/成功扫描 | 1119 / 1119 |
| 发现（S0–S2） | 2098（全部转人工复核提示） |
| 阻断级发现（S3/S4） | **0**（修复后复测） |
| 真实 vendoring 命中 | **56**（pip-vendor 30 + setuptools-vendor 26，含 1191 行 urllib3 匹配 conf 0.9954 正确评级 S1） |
| 单文件耗时 p50 / p95 | 约 40 / 1400 ms |

**这轮扫描发现并修复了产品的一个真实缺陷**：首次运行产生 **11 条假阻断**（pip/_vendor 的
import 名单、sqlmap 的 argparse 链、mitmproxy 的 0x 常量表、ansible/localstack/freqtrade 命中的
paramiko 小文件片段、pandas 的 re-export 名单、localstack 的惯用 mixin）——全部经由佐证规则的
"置信度≥0.75 即可阻断"通道：语料扩充后模型重训使分数漂移，该通道失去防线作用。修复
（`corroborates()`）：**任何阻断路径都要求 ≥10 个逐字 token**，长逐字通道另要求源覆盖率 ≥10%。
修复后变异基准 8 类阻断召回保持 100%，真实扫描 0 阻断；11 条误报的
(spans, coverage, verbatim, confidence) 四元组全部固化为回归测试（`tests/test_pipeline_cli.py`）。
2026-10-20 首轮 447 文件口径（10 项目、0 阻断、50 vendoring、argparse 样板误阻断修复）保留作历史对照。
方法见 [docs/EVALUATION.md](docs/EVALUATION.md)，原始结果见
`submission/evidence/realworld-github-20261024-v051.*`。真实仓库只作本地评测，不随仓库分发。

## 5. 开源与复用

- 许可证：**Apache-2.0**（含 `NOTICE`），自研代码与第三方资源边界见 `THIRD_PARTY_NOTICES.md`。
- 输出格式对接开放标准：**SARIF 2.1.0**（GitHub Code Scanning / IDE）、**CycloneDX 1.6** SBOM
  （`evidence.occurrences` / `identity`）与 `codeguard.provenance/v1` 出处证书，可被现有供应链工具直接消费。
- 数据集不外包：变异器、负例（`src/codeguard/data/negatives/`）、评测脚本随仓库发布；HumanEval 按 URL + SHA-256 获取，真实 GitHub 项目本地浅克隆，两者都不随仓库分发。
- 可作为 GitHub Action / pre-commit 钩子接入（`.github/workflows/codeguard-gate.yml`、`hooks/pre-commit`），
  PR diff 门禁与全仓扫描都可上传 SARIF，见 [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)。
- 维护与安全：验收判据见 [docs/ROADMAP.md](docs/ROADMAP.md)，漏洞报告范围见 [SECURITY.md](SECURITY.md)。

## 6. AI 使用声明

系统的**判定与检索完全由确定性算法与自训练轻量模型完成，可离线复现**。自然语言处置建议默认由内置离线模板生成；仅当显式配置大模型（命令行用环境变量 `CODEGUARD_LLM_BASE_URL` / `CODEGUARD_LLM_API_KEY` / `CODEGUARD_LLM_MODEL`，工作台在首次运行的设置对话框里保存到本机 `.codeguard/llm_config.json`，密钥不返回浏览器、不写入任何导出物）时才会调用外部大模型，调用失败自动回退到离线模板。工作台的大模型还可用于文件解读、审查执行摘要、基于证据摘要的追问与许可证通俗解释——每次调用均为用户主动触发并标注模型名。任何模式下，**风险等级与合规结论都不由大模型决定**，AI 只做证据的"翻译官"。该声明同时写入每份报告的"AI 使用声明"区块。

本仓库部分代码与文档在开发过程中使用了 AI 编码助手，由团队成员逐模块审核、复现后合入；参与环节与审核记录见技术报告第四节。

## 7. 目录结构

```
src/codeguard/
  normalize.py     语法无关归一化 + 四层视图（含回退迷你词法器）
  fingerprint.py   n-gram shingle 与多层草图
  minhash.py       Mersenne 素数置换 MinHash + b-bit + 分带
  cms.py           Count-Min 频率草图（IDF 权重的存储基础）
  index.py         索引构建/持久化/LSH 检索（CGIDX2 紧凑格式）
  evidence.py      第二阶段精确验证：Jaccard、IDF 包含度、最长逐字命中
  adjudicate.py    检索→验证→打分→聚合→风险分级
  evaluate.py      外部 JSONL 评测：干净误阻断、复制归因、单侧上限
  license_intel.py SPDX 解析链与许可证义务模型
  score.py         零依赖逻辑回归、AUC、阈值选择、分组留出
  benchmark.py     变异基准、消融实验、模型训练
  mutations.py     8 类确定性洗代码变异
  corpus.py        从 PyPI/源包构建带许可证标注的语料
  llm.py           离线模板撰写 + 可选外部大模型适配层（配置持久化、模型列表、解读/摘要/追问/许可解释四类提示词）
  report.py        出处证书 / CycloneDX / 自包含 HTML / SARIF 2.1.0
  cli.py           corpus index scan gate licenses model benchmark eval doctor
  data/negatives/  9 个自研"干净实现"（基准负例 + 测试 fixture）
tools/build_corpus.py   语料下载的实验性前作
scripts/           reproduce.sh（一键复现）· demo_gate.py（门禁演示）· make_demo_sample.py（演示样本）
                   false_block_control.py（误阻断对照组实验，佐证规则的证据）
                   eval_humaneval.py（外部干净负例，URL + SHA-256 校验）
                   eval_realworld.py（真实 GitHub 项目扫描，本地克隆）
tests/             130 个用例，全部离线跑在 fixture 上
docs/              TUTORIAL.md  DESIGN.md  BENCHMARK.md  EVALUATION.md  INTEGRATIONS.md  ROADMAP.md
SECURITY.md        漏洞报告范围与响应流程
submission/evidence/  基准、HumanEval、真实仓库、SBOM/Provenance 与截图佐证数据
hooks/pre-commit · .github/workflows/codeguard-gate.yml
```

## 8. 开发

```bash
python -m pytest                 # 130 个用例，全部离线跑在自带 fixture 上，无需语料/网络
python -m codeguard doctor
sh scripts/reproduce.sh --offline  # 复用本地语料，重跑索引 + 基准 + 测试 + 门禁自检
```

开发与验证环境：CPython 3.14（Windows 11）本地全量运行，CI（`.github/workflows/codeguard-gate.yml`）
在 CPython 3.12 / ubuntu 上跑同一套测试与门禁，并把 SARIF 上传到 GitHub Code Scanning。
代码只用标准库，无 C 扩展、无运行期数据文件下载。

参与方式见 `CONTRIBUTING.md`。

## 9. 免责

CodeGuard 提供的是**工程性风险提示，不构成法律意见**。它输出的是相似来源候选，不能证明某个模型的训练来源，也不能自动裁定侵权。许可证判定基于 SPDX 标识与义务模型的保守推理；无法解析的许可证一律标记为 `unknown` 而非默认放行。
