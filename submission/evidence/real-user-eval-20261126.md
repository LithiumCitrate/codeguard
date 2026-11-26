# CodeGuard 真实用户仓库端到端验证报告（2026-11-26）

- 生成时间：2026-11-26T04:43:53Z
- 评估对象：`LithiumCitrate` 与 `Aliceykr` 账号下的 **6 个真实公开仓库**（全量浅克隆，共扫描 **1,325 个源码文件 / 23.20 MB**）
- 工具版本：`codeguard` v0.6.0；索引指纹 `121bb5650b959fc2912e5285f57fe09d`（1,717 文档 / 127,156 片段 / 32 个开源包 / 11 种 SPDX，语料可读率 `1717/1717`）
- 扫描参数：`Scanner(index, model=model, usage='distribution')`，`target_license='MIT'`，`language=language_for(path)`
- 联网增强配置：OpenAI 兼容接口 `https://note3-prev-api.askdiandian.com/v1`，模型 `dots3-note-prev` + Tavily 检索（全程仅内存环境变量传参，已校验零密钥落盘）

---

## 一、离线全仓确定性审计（6 个真实仓库）

过滤规则：遍历 `.py` / `.js` / `.jsx` / `.mjs` / `.c` / `.h` / `.go` / `.rs`，跳过 `.git` / `node_modules` / `dist` / `build` / `__pycache__` / `*.min.js`、空文件及 `>200 KB` 文件。

| 仓库 | Commit | 扫描文件数 | 语言分布 | 耗时 (s) | p50 / p95 (ms) | 发现数 | 发现风险分布 (`S0/S1/S2/S3/S4`) | 文件最高风险 (`S0/S1/S2/S3/S4`) | 阻断文件 | 异常 |
|---|---|---|---|---|---|---|---|---|---|---|
| `LithiumCitrate/Mini-Bot` | `1031f4e15002` | 47 | py:43, js:4 | 32.424 | 370.1 / 2278.0 | 36 | 8 / 1 / 27 / 0 / 0 | 31 / 1 / 15 / 0 / 0 | **0** | 0 |
| `LithiumCitrate/AstrBot-Block-Editor` | `e71d504f18fb` | 15 | py:13, js:2 | 12.750 | 233.3 / 3885.0 | 9 | 7 / 0 / 2 / 0 / 0 | 13 / 0 / 2 / 0 / 0 | **0** | 0 |
| `LithiumCitrate/Voyage-Atelier` | `de333105d385` | 2 | js:2 | 2.910 | 1455.1 / 2743.1 | 0 | 0 / 0 / 0 / 0 / 0 | 2 / 0 / 0 / 0 / 0 | **0** | 0 |
| `Aliceykr/ImpedScope` | `d4ffb9414f93` | 1255 | c:1254, py:1 | 555.948 | 179.3 / 1872.8 | 361 | 192 / 2 / 167 / 0 / 0 | 1114 / 1 / 140 / 0 / 0 | **0** | 0 |
| `Aliceykr/kard` | `6e3c9af13d64` | 4 | js:4 | 5.074 | 415.8 / 3531.9 | 6 | 4 / 0 / 2 / 0 / 0 | 3 / 0 / 1 / 0 / 0 | **0** | 0 |
| `Aliceykr/ad9833_driver` | `060101d33e34` | 2 | c:2 | 0.151 | 75.7 / 105.9 | 0 | 0 / 0 / 0 / 0 / 0 | 2 / 0 / 0 / 0 / 0 | **0** | 0 |
| **合计** | — | **1,325** | c:1256, py:57, js:12 | **609.257** | — | **412** | **211 / 3 / 198 / 0 / 0** | **1165 / 2 / 158 / 0 / 0** | **0** | **0** |

> 注：`Mini-Bot` 另有 46 个源码文件未计入本次扩展名白名单（`.tsx` 18、`.ets` 15、`.ts` 10、`.java` 3）；`ImpedScope` 另有 45 个 CMSIS/器件大头文件因 `>200 KB` 被跳过。另外单独测试 `Mini-Bot` 的 28 个 `.ts`/`.tsx` 文件（`language_for` 映射为 `javascript`），耗时 23.46 s，产生 3 条跨语言 `S0` 巧合命中（匹配 Python 语料 `websockets`/`httpx`/`packaging`）。

### 1.1 S2/S3/S4 人工片段核查（TP vs FP）

- **S3/S4 阻断级误报**：**0 / 1,325**（佐证规则 `corroborates()` 兜底生效）。
- **S2 命中（共 198 条）人工核查结论**：**0 True Positive / 198 False Positive（100% 为结构/惯用法巧合，非真实第三方复制）**，主要模式如下：
  1. **C 宏常量表与 `#include` 串巧合（`ImpedScope` 167 条 S2，最高置信度 0.9998）**：
     - `Drivers/CMSIS/Core/Include/pmu_armv8.h:32-167` → `radare2/libr/anal/c/tcc.h:451-481`（`LGPL-3.0-only`，25 片段，`coverage=0.6098`，`confidence=0.9998`），实为 `#define ARM_PMU_* 0x0000` 与 `#define VT_* 0x0010` 在抽象/角色层同时归一为 `# define C z3`，全凭 `max_verbatim_run=2 < 10` 被佐证门槛拦截未误阻断。
     - `USE/measure.c:1-16` → `radare2/libr/anal/c/tcc.h:3-25`（`verb=12`），实为连续 `#include <float.h> #include <math.h> #include <string.h>` 头文件列举。
     - 其余多为 `CMSIS/DSP` 与 `git/apply.c`、`git/blame.c`、`radare2/arch_config.c` 间的 `for` 循环或矩阵索引惯用法。
  2. **跨语言误匹配（JS/C ↔ C/Go/Python）**：
     - `Aliceykr/kard/game.js:26`（JS 对象属性赋值 `g.phase=s.phase; ...`）命中 `radare2/libr/arch/arch_config.c:115-133`（C 结构体指针赋值 `ac->bits=c->bits; ...`），`prob=0.9175`、`wc=0.9791`、`conf=0.5984`、`verb=1`（`S2`）。原因：`normalize.py` 中 `.` 与 `->` 同映射为 `PUNCT`，且 `Scanner.verify_span` 未过滤不同语言的候选文档。
     - `ImpedScope` 中 C 文件交叉命中 `minio`（`.go`，`AGPL-3.0-only`，最高 `conf=0.5897`）、`paramiko`（`.py`，`LGPL-2.1`）与 `tqdm`（`.py`，`MPL-2.0`）。
  3. **Python `argparse` / 日志 / 异常样板（`Mini-Bot` 27 条 + `AstrBot-Block-Editor` 2 条）**：
     - `Mini-Bot/extension/cli.py`、`extension/server.py`、`extension/core/*.py` 集中命中 `glances`（`LGPL-3.0-only`，占 22/27 条）、`mercurial`（`GPL-2.0-or-later`）与 `paramiko`（`LGPL-2.1`），实为 `parser.add_argument(...)`、`try/except Exception as e: self.logger.error(...)`、`mkdir(parents=True, exist_ok=True)` 等通用写法（`verb=3–11`、`cov<=0.09`）。
- **语料外真实第三方代码（漏报基线）**：`ImpedScope` 内实际包含 **1,225 个真实第三方组件文件**（`Drivers/CMSIS` 977 个，Apache-2.0/MIT；`Drivers/STM32H7xx_HAL_Driver` 248 个，BSD-3-Clause）。因本地 32 包语料未收录 STM32 HAL/CMSIS，离线检出为 `0/1,225`。

---

## 二、Live LLM + Tavily 端到端验证（`dots3-note-prev`）

| 工作流 | 测试对象 | 状态 | 耗时 (ms) | Tavily 查询数 | 源码泄漏 | 关键观察 |
|---|---|---|---|---|---|---|
| 1. `list_models` | `note3-prev-api.askdiandian.com/v1` | 成功 | 234.6 | — | — | 返回 `["dots3-note-prev"]`，目标模型在列 |
| 2. `interpret_file_with_search` | `AstrBot-Block-Editor/gui/app.py` | 成功 | 21,553.0 | 1 | 0/1 | 准确识别 PyQt5+QWebEngineView；联网检索匹配主项目 `AstrBotDevs/AstrBot` (AGPL-3.0) 并提醒核实仓库归属；输出 749 字（超出 400 字上限） |
| 2. `interpret_file_with_search` | `ImpedScope/Core/Src/main.c` | 成功 | 23,012.9 | 1 | 0/1 | 准确识别 CubeMX STMicroelectronics 版权与 AS-IS 提示，检索 STMicroelectronics SLA0044 作佐证；输出 732 字 |
| 3. `run_web_probe` | `Mini-Bot/extension/core/manager.py` (Py) | 成功 | 26,693.3 | 3 | 0/3 | 3 轮元数据检索后诚实返回 `{"candidates": []}`；Tavily 直接返回 `raw.githubusercontent.com` 链接但被 `blob_to_raw` 跳过 |
| 3. `run_web_probe` | `Voyage-Atelier/script.js` (JS, 44 KB) | 成功 | 31,809.4 | 3 | 0/3 | 12KB 摘要正常触发；诚实返回 `{"candidates": []}`（未检出自仓） |
| 3. `run_web_probe` | `kard/p2p.js` (JS) | 成功 | 30,110.5 | 6 | 0/6 | `extract_license_markers` 把 `.accept(c)` 误判为 3 处版权声明注入提示词；模型猜中类似项目名但路径 404，`findings=0` |
| 3. `run_web_probe` | `ImpedScope/.../stm32h7xx_hal.c` (C, 44 KB) | **命中** | 156,393.2 | 3 | 0/3 | **核心边际收益案例**：离线 0 命中；模型提案 `main` 分支 404 后自动回退 `master` 拉取原文，精确验证 **138/138 片段、`conf=0.9996`、`verb=48`**；模型误猜 `MIT`，`ground_license` 拉取上游 `LICENSE.md` 后**确定性纠偏为 `BSD-3-Clause`**（`web:license-text-verified`）；另通过 `harvest_search_urls` 命中 `stm32h7xx_hal_rcc_ex.c`（`S0`，亦完成 `BSD-3-Clause` 核验） |
| 3. `run_web_probe` | `ad9833_driver/ad9833.c` (C) | 成功 | 29,346.3 | 3 | 0/3 | 检索到同芯片项目主页但无 raw 文件，诚实返回 `{"candidates": []}` |
| 4. `summarize_with_search` | `Mini-Bot` 整夹摘要（47 文件 / 32 命中） | 成功 | 29,291.5 | 3 | 0/3 | 输出 1,186 字（远超 200–400 字限制）；因摘要未标 `corroborated=False`，模型将 `S2` 巧合解读为"引用了 Mercurial GPL 代码、动态链接 Glances/Paramiko" |
| 4. `answer_question_with_search` | `"哪些文件需要优先复核？"` (`Mini-Bot`) | 成功 | 52,985.2 | 2 | 0/2 | `json.dumps(digest)[:8000]` 在第 8000 字符处腰斩 `config.py` 字段导致模型回复"置信度未完整显示"；将 Paramiko (LGPL-2.1) 误并入 LGPL-3.0-only；两次调用完全相同的 Tavily 查询词 |

- **JSON 解析与格式稳定性**：5 次 `run_web_probe` 中，`dots3-note-prev` **0 次出现 `<think>` 标签**，100% 输出 ```` ```json ... ``` ```` 代码块，`parse_candidates()` 全部一次解析成功（其中 `kard/p2p.js` 第 3 条候选为非 raw 仓库主页 URL，被 `validate_fetch_url` 正确拒绝）。
- **隐私与安全不变量**：全部 **25 次** Tavily 查询均不含任何源码原文行（`0/25` 泄漏）；5/5 次 `run_web_probe` 严格满足 `offline_unchanged=True`、`blocking=False`、`max_risk <= S3`、`https` 白名单与审计字段齐全；全局仅 0/5 出现自仓匹配（说明 Tavily 通用网页检索对中小冷门 GitHub 自仓文件覆盖有限）。

---

## 三、发现的缺陷、用户摩擦与 Round 2 优化建议（按影响排序）

1. **[高 · 准确率] 离线验证缺少语言兼容性过滤，导致跨语言高置信度误报**
   - 位置：`src/codeguard/adjudicate.py` (`Scanner.verify_span`)、`src/codeguard/normalize.py` (`_OP_MAP`)
   - 现象：`kard/game.js`（JS）因 `.` 与 `->` 均被归约为 `PUNCT`，以 `prob=0.9175 / wc=0.9791` 命中 `radare2/arch_config.c`（C，LGPL-3.0-only）；`ImpedScope`（C）命中 `minio`（Go，AGPL-3.0-only）和 `paramiko`/`tqdm`（Python）。
   - 建议：在 `verify_span` 或 `Index.probe` 中增加语言兼容性约束（如 `python`/`c`/`go`/`rust`/`javascript` 不跨族匹配，仅 `generic` 可兜底），并把 `.` 与 `->` 在 `_OP_MAP` 中区分开。
2. **[高 · 准确率/信噪比] 198/198 条 `S2` 均为误报，C 宏常量表、`#include` 列举与 Python `glances` 样板刷屏**
   - 位置：`src/codeguard/normalize.py`、`src/codeguard/license_intel.py:548`、`src/codeguard/adjudicate.py`
   - 现象：`#define X 0x...` 归一为 `# define C z3` 使 `pmu_armv8.h` 命中 `tcc.h` 达 `conf=0.9998 / cov=0.6098`（靠 `verb>=10` 才未误阻断）；3 行 `#include <...>` 即可刷出 `verb=12`；`risk_level("conditional", ...)` 不看 `confidence` 直接给 S3 再降 S2，导致 `Mini-Bot` 产生 27 条、全量 198 条低质 `S2` 告警。
   - 建议：对纯预处理 `#define`/`#include` 块及常量数组表降低权重或过滤；对极低覆盖且低逐字命中（如 `spans==1 and verb<6 and cov<0.05`）的 `conditional` 巧合降为 `S0/S1` 观察或过滤，避免淹没真实风险。
3. **[高 · AI 可靠性] `json.dumps(digest)[:8000]` 截断 JSON 与缺失 `corroborated` 字段诱发 AI 幻觉处置建议**
   - 位置：`src/codeguard/llm.py:504,512,523,550`、`src/codeguard/web.py:371-387`
   - 现象：`Mini-Bot` 摘要 JSON 长 15,086 字符，硬切片 `[:8000]` 导致半截 JSON 传入模型（模型直言"置信度未完整显示"且丢失后半部分命中）；`digest` 未透传 `corroborated` 与明确"低证据巧合"标记，模型把 `S2` 误述为"引用 Mercurial GPL / 动态链接 Glances"。
   - 建议：按 finding 条目结构化裁剪 `digest` 保持合法 JSON；在 `digest` 中显式包含 `corroborated` 和 `matched_spans` 并在提示词中约束：未达 `corroborated=True` 的 S2 项应表述为"待人工复核的疑似相似片段"，严禁断言为"已引用/已链接第三方库"。
4. **[中 · 确定性标记] `extract_license_markers` 正则 `(c)` 误伤普通函数参数调用**
   - 位置：`src/codeguard/llm.py:242,250-278`
   - 现象：`_COPYRIGHT` 无边界匹配 `(c)`，导致 `self._parse_config_item(c)`、`cardText(c)`、`accept(c)` 被当成版权声明并喂给大模型；`_VENDORED` 匹配注释里的 `"based on"`；第 256 行 `head` 变量计算后未使用且全文扫描代码体而非仅扫注释/文件头。
   - 建议：仅在注释或文件头区域提取版权/来源标记，且 `(c)` 要求搭配年份或 `copyright`/© 语义上下文（如 `(?:\(c\)|©)\s*(?:19|20)\d{2}`）。
5. **[中 · 工程规模与 CLI/Workbench 一致性] 大仓截断、缓存丢失与 CLI 覆盖输出**
   - 位置：`src/codeguard/web.py:37,321`、`src/codeguard/static/app.js:392,479`、`src/codeguard/cli.py:538`、`src/codeguard/report.py:424`
   - 现象：`ImpedScope`（1,255 文件 / 22.5 MB）远超工作台 `MAX_TREE_FILES=400` / `8 MB` 上限；`web.py:321` 在 `scan_tree` 循环内每文件重建 `Scanner`，每次丢弃 `CandidateReader` 缓存；`cli.py scan` 默认 `--ext="py"` 会漏掉 C/JS/Go/Rust；`report.py write_outputs` 仅用文件名主干落盘，遇到多个 `__init__.py` 会静默覆盖前份 SARIF/JSON。
   - 建议：`scan_tree` 循环外复用单个 `Scanner`；前端上传目录树先剔除 `.git`/`node_modules`/`build`/`dist` 再计数并支持分批或放宽纯代码上限；`write_outputs` 保留相对路径哈希或路径扁平化防覆盖。
6. **[中 · 联网溯源] `ground_license` 仓库别名缓存穿透与搜索结果 direct-raw URL 漏收**
   - 位置：`src/codeguard/web_evidence.py:208-216,303`
   - 现象：`stm32h7xx_hal.c` 一次 probe 中，模型提案 `stm32h7xx-hal-driver`（连字符）而搜索链接为 `stm32h7xx_hal_driver`（下划线），`ground_license` 因大小写/别名或分叉 URL 重复拉取 2 次 `LICENSE*`；`harvest_search_urls` 只调用 `blob_to_raw`，当 Tavily 直接返回 `raw.githubusercontent.com` 链接时会跳过；`stm32h7xx_hal.c` 单次 probe 耗时 156.4 s，需在 UI 明确进度提示。
   - 建议：`harvest_search_urls` 对已通过 `validate_fetch_url` 的直接 raw URL 一并收录；对多候选抓取与许可证核验加并发或严格总预算；`ground_license` 在重定向解析后按最终规范仓库根复用缓存。
7. **[低 · 许可规则与 LLM 护栏] `Apache-2.0` 义务措辞偏差与模型超长/重复检索**
   - 位置：`src/codeguard/license_intel.py:73,519`、`src/codeguard/llm.py:385,486`
   - 现象：`Apache-2.0` 与 `MulanPSL-2.0` 档案设 `source_offer=True`，使兼容义务输出"随分发提供对应源码（或书面要约）"（Apache-2.0 §4 并不强制随分发附带源码）；`dots3-note-prev` 回复 732–1,448 字未遵守 400 字约束，且单次追问偶发重复调用完全相同的检索词。
   - 建议：修正 `Apache-2.0` 的 `source_offer=False`；在 `chat_with_search` 工具循环内对同一标准化 `query` 做会话级去重缓存，避免浪费 Tavily 配额与延迟。

---

## 四、Round 2 优化实施与 Before / After 复测对比

针对上述 7 项发现完成全部代码修复并补齐单元测试（全量 `pytest` 通过 **231 / 231**）：

1. **跨语言候选过滤（`src/codeguard/adjudicate.py`）**：`Scanner.verify_span` 在 `language` 与 `doc.language` 均为已知语言（非 `generic`）且不相等时跳过候选。
2. **C/C++ 纯预处理/宏表抑制与单片段极弱巧合降级（`src/codeguard/adjudicate.py`）**：对 `language == 'c'` 的查询片段，剥离注释后若非空代码行 ≥75% 为预处理指令或宏常量表（含 `\` 续行）则跳过；对未达佐证且 `len(spans)==1`、`coverage<0.15`、`max_verbatim_run<6` 的孤立弱巧合降级为 `S0`。
3. **摘要结构化裁剪、佐证口径约束与检索去重（`src/codeguard/llm.py`、`src/codeguard/web.py`）**：新增 `_compact_digest(digest, max_chars=7500)` 按 `findings` 条目裁剪并记录 `findings_omitted`（杜绝 `[:8000]` 腰斩 JSON）；在 `scan` 与 `scan_tree` 的 `last_digest` 透传 `corroborated` 与 `matched_spans`，提示词严禁将 `corroborated=False` 表述为“引用/依赖/动态链接”；`chat_with_search()` 内按规范化检索词会话级去重缓存。
4. **`extract_license_markers` 精确范围修复（`src/codeguard/llm.py`）**：新增 `_comment_and_header_lines()` 仅扫描注释行与文件头前导文本，跳过 `accept(c)`/`cardText(c)` 等代码体调用，并要求 `(c)`/`©` 与 `copyright` 或 4 位年份（`19xx`/`20xx`）同现。
5. **工作台缓存复用、前端过滤与 `Apache-2.0` 档案修正（`src/codeguard/web.py`、`src/codeguard/static/app.js`、`src/codeguard/license_intel.py`）**：`scan_tree()` 在循环外复用单个 `Scanner`（保留 `CandidateReader` 缓存）；`app.js` 上传目录树时预剔除 `.git/`、`node_modules/`、`dist/`、`build/`、`__pycache__/` 与 `*.min.js`；修正 `Apache-2.0` `source_offer=False`。
6. **WebProbe 直连 raw URL 与小写仓库键缓存（`src/codeguard/web_evidence.py`）**：`harvest_search_urls()` 同时收录已通过 `validate_fetch_url()` 的直接 raw 地址；`ground_license()` 按 `root.lower()` 缓存避免大小写变体重复拉取 `LICENSE`。

### 4.1 6 个真实仓库 Before vs After 离线复测（1,325 文件）

| 仓库 | 文件数 | Before 发现 (`S0/S1/S2/S3/S4`) | After 发现 (`S0/S1/S2/S3/S4`) | Before 文件 S2 | After 文件 S2 | S2 误报变化 |
|---|---:|---|---|---:|---:|---|
| `LithiumCitrate/Mini-Bot` | 47 | 36 (`8/1/27/0/0`) | 36 (`18/1/17/0/0`) | 15 | 12 | `27 → 17`（**-37.0%**） |
| `LithiumCitrate/AstrBot-Block-Editor` | 15 | 9 (`7/0/2/0/0`) | 9 (`9/0/0/0/0`) | 2 | 0 | `2 → 0`（**-100%**） |
| `LithiumCitrate/Voyage-Atelier` | 2 | 0 (`0/0/0/0/0`) | 0 (`0/0/0/0/0`) | 0 | 0 | `0 → 0` |
| `Aliceykr/ImpedScope` | 1255 | 361 (`192/2/167/0/0`) | 244 (`189/2/53/0/0`) | 140 | 46 | `167 → 53`（**-68.3%**） |
| `Aliceykr/kard` | 4 | 6 (`4/0/2/0/0`) | 4 (`4/0/0/0/0`) | 1 | 0 | `2 → 0`（**-100%**） |
| `Aliceykr/ad9833_driver` | 2 | 0 (`0/0/0/0/0`) | 0 (`0/0/0/0/0`) | 0 | 0 | `0 → 0` |
| **合计** | **1,325** | **412 (`211/3/198/0/0`)** | **293 (`220/3/70/0/0`)** | **158** | **58** | **`198 → 70`（-64.6%）** |

- **跨语言误匹配清零**：跨语言命中（含 `kard/game.js → radare2/arch_config.c` 与 `ImpedScope` C↔Go/Py）由 **13 条 → 0 条（-100%）**。
- **C 宏表与 `#include` 刷屏清零**：`Drivers/CMSIS/Core/Include/pmu_armv8.h`（原 `conf=0.9998`, 25 spans）、`DAP.h`、`USE/measure.c`（`#include` 串 `verb=12`）及 STM32 HAL `.h` `#define` 常量表 `S2` 全部消除。
- **工作台 `scan_tree` 缓存复用实测（`Mini-Bot` 47 文件）**：复用单个 `Scanner` 耗时 **59.552 s**（含 `health()` 校验与模板渲染），对比修复前逐文件新建 `Scanner`（**263.510 s**）提速 **4.42×**；`last_digest` 原文 15,298 字符经 `_compact_digest(..., max_chars=7500)` 压缩为 **7,170 字符**完整合法 JSON（保留 14 条最高风险命中，`findings_omitted=18`）。

### 4.2 回归评测零退化验证

- **单元测试（`python -m pytest`）**：**231 / 231** 通过（新增 11 条专项单测覆盖全部 7 项修复）。
- **多语言基准（`scripts/eval_multilang.py`）**：**124 / 128（96.9%）**，C **100.0%** (32/32)、Go **87.5%** (28/32)、JS **100.0%** (32/32)、Rust **100.0%** (32/32)，干净与跨语言误阻断 **0 / 61**。
- **定量基线对比（`scripts/eval_baselines.py`，24 文件 × 6 变异 = 144 正例 + 9 负例）**：CodeGuard 召回 **95.8%（138/144）**、`F1 = 0.979`、`FPR = 0.0%（0/9）`。
- **全语料 8 变异基准（`codeguard benchmark --files 24 --chars 5000 --full-corpus --no-train`）**：总体召回 **97%**（`多层+IDF`，`多层无IDF` 为 **98%**）、负例误报 **0 / 9**、精确率 **1.00**。
- **HumanEval 外部干净负例（`scripts/eval_humaneval.py`，164 例）**：阻断级误报 **0 / 164（0.00%）**，`S2` 及以上 **0 / 164**（任意弱观察 2 例），单样本 `p50 = 38.9 ms / p95 = 326.6 ms`。
- **WebProbe 许可文本核验（`scripts/eval_license_grounding.py`）**：**18 / 18** 离线夹具用例全通过。
- **Live `dots3-note-prev` + Tavily 复核说明**：本次复核子进程运行时未注入外部 API 密钥环境变量（严禁密钥落盘），故 `_compact_digest`、逐轮 `web_search` 去重与 `corroborated=False` 口径约束已由本地回环桩测试全覆盖验证；带真实外部密钥的 `summarize_with_search` 端到端校验需在注入 `CODEGUARD_EVAL_API_KEY` / `CODEGUARD_EVAL_TAVILY_KEY` 的运行时执行。
