# CodeGuard 使用教程

本教程里的每一段输出都是在一次真实运行中截取的（Python 3.14，仅标准库，
索引为 20 个开源包 / 585 文件 / 36193 片段）。命令按顺序执行即可复现。

---

## 0. 准备

```bash
cd codeguard
pip install .                     # 零第三方依赖；不联网也能装
```

不想安装也可以直接用源码目录：

```bash
PYTHONPATH=src python -m codeguard doctor
```

数据目录默认是 `./.codeguard`，也可用 `--workspace` 或环境变量 `CODEGUARD_HOME` 指定。
所有产物（语料、索引、模型、报告）都写在这里，`doctor` 会打印实际路径。

## 1. 建立知识底座：`codeguard corpus`

```bash
codeguard corpus                  # 默认 19 个许可证多样的包，每包最多 70 个文件
```

- 逐个包解析 `METADATA` / `PKG-INFO` → PEP 639 `license_expression` → `license` 字段
  → trove 分类符 → 源码头部注释，解析不到就记为 `UNKNOWN`（**绝不默认放行**）；
- 每个文件记录 SPDX id、解析来源（`license_resolved_from`）、行数、token 数、SHA-256；
- 结果写入 `.codeguard/corpus/corpus.json`，随后可离线反复重建索引。

## 2. 建索引：`codeguard index`

```bash
codeguard index                   # window=48 stride=24
```

实测：585 文档 / 36193 片段，用时 80–116 s（冷缓存首次较慢），索引文件 8.9 MB（约 328 B/片段），加载 0.57 s。

索引里**只有哈希、行号与草图字节**，没有源码原文。第二阶段的精确验证需要原文时，
按 `corpus_root + path` 从本地语料目录回读——语料不进仓库，索引进 CI 也不需要泄露源码。

```bash
codeguard doctor
```

```
codeguard 0.2.0 · Python 3.14.3
工作目录：D:/code/lanying/codeguard/.codeguard
索引：documents=585 chunks=36193 packages=20 buckets=771597
许可证：Apache-2.0, BSD-2-Clause, BSD-3-Clause, GPL-2.0-or-later, LGPL-2.1, LGPL-3.0-only, MIT, MPL-2.0, PSF-2.0
参数：window=48 stride=24 layers=('role', 'abs', 'edge')
模型：已加载
AI 使用：CodeGuard 默认使用确定性模板生成器产出合规说明，全程离线、无外部模型调用、结果可逐字节复现；……
```

## 3. 训练判定模型并复现实验：`codeguard benchmark`

```bash
codeguard benchmark --files 24    # 消融 + 变异基准 + 训练，约 40 s
```

产出 `.codeguard/benchmark-<date>/benchmark.md`、`benchmark.json` 与 `.codeguard/model.json`。
仓库里已提交一份结果快照：[BENCHMARK.md](BENCHMARK.md)。
没有模型时 `scan`/`gate` 自动退化为规则打分（`adjudicate.Scanner.probability`），
功能不缺失，只是阈值语义换成可解释的加权规则。

## 4. 扫描一个"AI 改写过的文件"：`codeguard scan`

从本地语料取 mercurial（GPL-2.0-or-later）的两个顶层定义（57 行）做一次**全局标识符重命名**，
冒充"AI 重新写了一遍"。样本写在 `.codeguard/` 内（已 gitignore）——语料派生片段绝不进仓库：

```bash
python scripts/make_demo_sample.py
codeguard scan .codeguard/demo/feature_flags.py --license MIT --usage distribution
```

```
.codeguard/demo/feature_flags.py: 片段 8/10 命中，来源 1 个
   [S4] GPL-2.0-or-later mercurial          conf=0.99 cov=0.80 automation.py
   -> .codeguard/demo/reports/feature_flags.provenance.json
   -> .codeguard/demo/reports/feature_flags.cdx.json
   -> .codeguard/demo/reports/feature_flags.report.html

合计命中来源 1 个
```

三种产物各有用途：

| 文件 | 面向 | 内容 |
|---|---|---|
| `*.provenance.json` | 机器 / 归档 | `codeguard.provenance/v1`：逐片段 query/source 行号、概率、最长逐字 token 命中、四层精确 Jaccard、12 维特征、许可证判定全文 |
| `*.cdx.json` | 供应链工具 | CycloneDX 1.6 SBOM，`components[].evidence.occurrences` 带行号，可直接被 Dependency-Track 一类工具消费 |
| `*.report.html` | 人 / 法务 | 自包含单文件，无任何外链与外部资源，离线双击即开 |

出处证书里的关键字节选（已格式化）：

```json
{"source": {"package": "mercurial", "version": "7.2.4",
            "path": "mercurial-7.2.4/contrib/automation/automation.py",
            "license_spdx": "GPL-2.0-or-later", "license_resolved_from": "pep639-expression"},
 "confidence": 0.994, "span_coverage": 0.8, "risk": "S4",
 "verdict": {"status": "incompatible",
             "conflicts": ["目标许可证 MIT 的 copyleft 强度低于 GPL-2.0-or-later 所要求的 GPL-2.0-or-later；来源代码许可证 GPL-2.0-or-later 的传染性范围为整件作品。"]},
 "evidence": [{"query_lines": [1, 13], "source_lines": [10, 39],
               "probability": 0.8795, "verbatim_token_run": 32,
               "weighted_containment": 0.5014,
               "exact_layer_jaccard": {"role": 0.3529, "abs": 0.0481, "edge": 0.5556, "lit": 0.2540},
               "lsh_band_hits": 1}]}
```

`abs` 层只有 0.0481 而 `role` 层 0.3529、`edge` 层 0.5556，正是"改名"的指纹特征：
抽象层按出现顺序别名化，改名会打乱别名编号；角色层把标识符归约为 局部/内置/关键字、
关系边只认结构位置，改名后依然对齐。
最终判定由四层 Together + IDF 加权包含度 + 逐字连续命中共同支撑，任何单层都不足以下结论。

## 5. CI 门禁：`codeguard gate`

`gate` 读 stdin 或 `--diff`（路径 / `-` / 内联文本都行），只看新增行，退出码即结论：

| 退出码 | 含义 |
|---|---|
| 0 | 没有命中，或只有提示级（S0–S2）发现 |
| 1 | 出现 `--fail-on` 列出的阻断级（默认 S3,S4） |
| 2 | 用法/环境错误（索引缺失、无待检查文件等） |

一键演示（用本地语料现造一个"AI 重写了 copyleft 实现"的 PR diff）：

```bash
python scripts/demo_gate.py --package paramiko --mutation compound --license LicenseRef-Proprietary
```

```
演示：把 paramiko-5.0.0/_winapi.py 的实现改写后并入许可证为 LicenseRef-Proprietary 的项目
变异：compound（seed=2026），原始 65 行 → 提交 118 行

CodeGuard 合规门禁 · 目标 myapp/helpers.py · 项目许可证 LicenseRef-Proprietary
 [x] S3        LGPL-2.1           conf=0.66  来源 paramiko@5.0.0:_winapi.py

共 1 条来源，其中阻断级 1 条；报告：.codeguard/reports
门禁失败：请替换实现、改用兼容许可证，或按 copyleft 条款公开源码。

退出码 1（0 放行 / 1 阻断 / 2 环境或用法错误）
```

接入方式见 `.github/workflows/codeguard-gate.yml` 与 `hooks/pre-commit`。

## 6. 只做许可证推理：`codeguard licenses`

```bash
codeguard licenses AGPL-3.0-only GPL-3.0-only --usage network_service
```

```
来源 AGPL-3.0-only (arg) -> 目标 GPL-3.0-only (arg) 使用方式 network_service
结论：conditional
  义务：整件组合作品必须整体按 AGPL-3.0-only 条款授权并开放对应源码
  义务：保留版权/许可声明
  义务：对修改过的文件作出显著说明
  义务：随分发提供对应源码（或书面要约）
  义务：AGPL §13：为通过网络与本程序交互的用户提供获取对应源码的途径（修改后的版本同样受约束）
  说明：AGPL 要求更严：合并作品须整体按 AGPL-3.0-only 授权
  风险：S3 高风险：需按 copyleft 条款开源或替换
```

退出码：`incompatible` 为 1，其它为 0，方便在脚本里串联。

## 7. 常用调参

| 参数 | 默认 | 什么时候调 |
|---|---|---|
| `--window/--stride` | 48 / 24 | 语料很大时缩小窗口可省内存；stride 越小越不容易漏掉错位复制 |
| `--min-span-prob` | 0.55 | 越高越严格（漏报增多、误报减少），benchmark 里就是这个阈值下的召回 |
| `--top-verify` | 4 | 每个片段最多精确验证的候选数，直接影响耗时 |
| `--threshold` | 0.5 | 保留参数，配合 `--min-span-prob` 使用 |
| `--usage` | scan=`inline_copy` / gate=`distribution` | 决定义务是否触发：`internal_use` 下 copyleft 不发作 |
| `--fail-on` | `S3,S4` | 只想告警不改红：设成 `S4` |
| `--explain` | `auto` | `offline` 强制模板；`llm` 需配 `CODEGUARD_LLM_BASE_URL`/`_API_KEY`/`_MODEL`，失败自动回退模板 |
| `--corroborate-coverage` / `--corroborate-verbatim` / `--corroborate-confidence` | 0.15 / 20 / 0.75 | 阻断门槛（见下），设 0 等于关闭佐证要求 |
| `--allow-partial-corpus` | 关闭 | 语料原文不全时仍继续，并把"覆盖面受限"写进报告 |

### 门禁的两道保险

1. **语料可读性检查**。第二阶段的精确验证要回读语料原文；原文丢失时每个候选都得 0 分，
   "未发现命中"就成了**假通过**。所以 `scan`/`gate` 启动时先查 `corpus_health()`：
   原文全部缺失直接退出码 2，部分缺失也中止并提示，除非显式加 `--allow-partial-corpus`
   ——此时警告会写进报告的 `notes`，JSON/HTML 均可审计。
2. **阻断需要佐证**。"许可证冲突 + 单个孤立片段"不等于阻断。只有满足
   「≥2 片段、覆盖率 ≥0.15 且逐字命中 ≥10 token」或「逐字命中 ≥20 token」或「整体置信度 ≥0.75」之一才评
   S3/S4，否则降为 S2 提示并在报告里说明降级原因。在 200 个真实语料文件的跨包抽查中，
   这条规则把误阻断从 3.5% 降到 0%，而"重命名+格式化+注释+死代码"的真实改写仍以
   0.66 置信度被阻断。`codeguard benchmark --files 24 --fp-study 200` 复现"0%"；
   对照组（同一批文件、关闭佐证要求）用 `python scripts/false_block_control.py --sample 200`
   复现"3.5%"。

## 8. 外部评测与 SARIF

外部评测用 JSONL 清单，每行一个样本：

```bash
codeguard eval --manifest samples.jsonl --out .codeguard/eval
```

`clean` 样本统计误阻断，`copied` 样本统计归因与 top-1 来源；汇总会给出
单侧 Clopper-Pearson 上限、风险分布与耗时分位。仓库自带的 HumanEval 证据复现命令：

```bash
python scripts/eval_humaneval.py
```

SARIF 2.1.0 可直接交给 GitHub Code Scanning：

```bash
codeguard scan src/ --license Apache-2.0 --usage distribution --format sarif
codeguard gate --diff pr.diff --license Apache-2.0 --usage distribution \
  --sarif .codeguard/reports/pr.sarif
```

规则映射与 CI 缓存注意事项见 [INTEGRATIONS.md](INTEGRATIONS.md)，外部评测的方法与边界见
[EVALUATION.md](EVALUATION.md)。0/164 只能写成“0 观测 + 单侧 95% 上限 1.81%”。

## 9. 排查

- **"尚未建立索引"**：先 `codeguard corpus && codeguard index`（退出码 2）。
- **扫描很慢**：`--top-verify 2`，或把语料换成 `--packages` 精简清单。
- **想确认为什么某个片段被判/不判**：看 `*.provenance.json` 里该片段的 `features`
  与 `exact_layer_jaccard`，再对照 `codeguard model --show` 的特征权重——判定是 12 维
  线性模型，可以手算复核，不存在黑箱。
- **误报**：优先检查目标项目许可证解析是否落到 `UNKNOWN`（会保守判 `unknown` 而非放行）。
