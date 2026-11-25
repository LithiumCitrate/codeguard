# 联网溯源（Web Provenance Probe）· 可选补充通道

> 离线引擎回答"这段代码与**本地语料**里的哪些原文相似"。联网溯源回答一个离线引擎
> 原理上回答不了的问题："这段代码是否复制了**语料之外**的开源项目？"
> 它把大模型从"解读翻译官"升级为"候选来源提出者"，但**判定权始终在确定性引擎**。

本通道完全可选：不配置大模型 / Tavily 时不存在任何联网行为，离线功能逐字节不变。

---

## 1. 为什么需要它（AI 必要性）

受控变异基准里"多层+IDF+判定模型"与"多层+IDF+规则"的文件级检出同为 97%——判定模型
的边际收益不明显，这是答辩最可能被追问的一点（见 `submission/11-国奖差距自审.md`）。
联网溯源给出一个**规则/语料原理上做不到**的边际收益：

- 本地语料只覆盖 32 个来源 / 1717 文件。语料外的项目（如 ranger、itsdangerous、toml）
  无论怎么改指纹、调模型，离线引擎都**检不出**——它没有这些原文。
- 联网溯源让大模型联网推断候选上游、拉取公开 raw 原文，再交给**同一套**确定性管线验证。
  在 2026-11-25 复测的 6 个语料外真实项目（`ranger`、`itsdangerous`、`toml`、`synapse`、`aiohttp`、`markupsafe`，每例 2 次试验、离线检出均为 0）中，联网通道累计命中 **11/12 次**（前 5 个稳定 2/2、`synapse` 1/2），且 **11/11（100%）** 完成了上游 LICENSE 原文确定性核验（`web:license-text-verified`）。这是"AI 扩展了能力边界"的一组**有明确边界的**可验证证据，而非"AI 复述了规则已经能做的事"；完整比率与历史基线对比见第 5 节。

## 2. 架构：AI 提案，确定性验证

```
待审查代码
   │  ① 大模型 + Tavily 检索（查询词仅公开元数据：项目名/API 名/功能关键词，严禁逐字源码）
   ▼
候选上游 raw URL（JSON）＋ 检索轨迹
   │  ② 确定性候选补全：代码注释仓库链接、检索结果中的源码链接 → blob→raw 转换
   ▼
白名单拉取（https raw；≤200KB；超时；防跳转出白名单；404 时 master/main/develop 回退）
   │  ③ 临时内存索引（共享生产 Count-Min sketch，IDF 语义不变）
   ▼
复用离线管线：LSH 检索 → 回读原文精确验证 → 判定模型 → SPDX 义务推演 → 佐证门槛
   │  ④ 命中后拉取上游 LICENSE 原文做确定性 SPDX 签名核验（失败回退模型推断）
   ▼
补充提示（web_sourced；封顶 S3、不阻断；附 url/sha256/fetched_at/许可证核验来源）
```

关键设计：**拉取到的原文不被信任**。它和本地语料原文走完全相同的精确验证
（Jaccard / IDF 加权包含度 / 最长逐字 token），只有证据足够才成为发现。因此联网通道
只增加召回，不引入"模型说抄了就算抄了"的误报路径。

## 3. 安全与合规保证

| 保证 | 实现 |
|---|---|
| 不上传用户源码到检索 | 查询词仅公开元数据；源码只发往用户自配的大模型接口（与解读层同口径） |
| 拉取面收敛 | 仅 `raw.githubusercontent.com` / `gist.githubusercontent.com` / GitLab `/-/raw/` / Gitee `/raw/`；https；≤200KB；超时；重定向逐跳校验不出白名单 |
| 不污染离线 | 临时索引 + 临时目录，用完即删；共享只读生产 CMS；语料/索引/`last_digest` 均不写 |
| 不越权阻断 | 联网命中 `blocking=False`，风险封顶 S3；许可证未经核验时按 unknown→S2 复核 |
| 许可证可核验（已实测验证） | 命中后拉上游 LICENSE 做确定性签名匹配，标注 `web:license-text-verified`；失败回退 `web:llm-inferred` 并提示人工确认。**2026-11-25 真实联网复测中已端到端触发 11/11（100% 检出命中均由 LICENSE 原文核验）**；早期 2026-11-15 基线曾为 0/2 |
| 核验失败可解释（2026-11-15 修补） | 无论成功失败，`provenance.license_grounding` 都记录 `status` / `reason` / `cache_hit` / 逐 URL `attempts`，不再静默返回空字典 |
| 可审计 | 每条发现附 `provenance{url, sha256, fetched_at, license_source, license_url, license_sha256, license_grounding}`；检索轨迹逐条留痕 |
| 密钥不外泄 | 仅存本机 gitignored `.codeguard/llm_config.json`；不返回浏览器、不写入导出 |

## 4. 复现

```bash
# A. 核验通道的离线可复现验证：无需网络、无需任何密钥
python scripts/eval_license_grounding.py
# 输出 submission/evidence/license-grounding-eval-<date>.{json,md}
# 注意：mode=offline-fixture，只证明通道逻辑/审计/端到端链路，不代表真实联网成功率

# B. 真实联网边际收益评测（需要稳定网络）
# 需要环境变量：CODEGUARD_LLM_BASE_URL / CODEGUARD_LLM_API_KEY / CODEGUARD_LLM_MODEL
#              CODEGUARD_TAVILY_API_KEY
python scripts/eval_webprobe.py --trials 3
# 输出 submission/evidence/webprobe-eval-<date>.{json,md}
```

评测对每个语料外真实 GitHub 文件做 N 次试验，每次：离线扫描(基线) → 联网溯源 →
离线扫描(复核)，**硬断言**离线判定前后逐字节一致、联网不阻断、不超 S3、审计字段齐全、
宽松许可不过度定级、命中原文来自白名单并通过精确验证。检出以比率报告（LLM 提案非确定性）。
注意上游归属按**拉取 URL** 判定：`top.package` 可能是 `web-source/UNKNOWN`，不等于模型报出的包名。

## 5. 实测（2026-11-25 修补后复测 + 2026-11-15 历史基线）

### 5.0 2026-11-25 真实联网复测（6 个语料外项目 × 2 次试验 = 12 次）

经过 `llm.py` 瞬断重试、`propose_upstream` 12KB 结构摘要与非逐字元数据种子、GitHub/GitLab/Gitee 包名推导与优雅降级优化后，使用 `scripts/eval_webprobe.py --trials 2 --date 20261125` 实测（模型 `dots3-note-prev` + Tavily；证据见 `submission/evidence/webprobe-eval-20261125.{json,md}`）：

| 项目（语料外） | 实际许可证 | 离线检出上游 | 联网检出 | LICENSE 文本核验 | 最高风险 | 最高置信度 |
|---|---|---|---|---|---|---|
| ranger | GPL-3.0-only | 0/2 | **2/2** | **2/2** | S3 | 0.997 |
| itsdangerous | BSD-3-Clause | 0/2 | **2/2** | **2/2** | S1 | 0.995 |
| toml | MIT | 0/2 | **2/2** | **2/2** | S1 | 0.994 |
| synapse | Apache-2.0 | 0/2 | **1/2** | **1/2** | S1 | 0.992 |
| aiohttp | Apache-2.0 | 0/2 | **2/2** | **2/2** | S1 | 0.998 |
| markupsafe | BSD-3-Clause | 0/2 | **2/2** | **2/2** | S1 | 0.999 |

- **安全不变量**：12 次试验离线结论前后逐字节一致、联网 0 阻断、风险封顶 S3、宽松许可（itsdangerous/toml/synapse/aiohttp/markupsafe）均未误报高风险、审计字段（`url`/`sha256`/`fetched_at`/`license_grounding`）全部齐全、密钥零泄漏。
- **核验率跃升**：11 次成功联网检出中，**11/11（100%）** 均通过上游 LICENSE 原文确定性核验标注为 `web:license-text-verified`（不再停留于 `web:llm-inferred`）。
- **边界保持**：`synapse` 为 1/2（另一次提案未命中，优雅降级未报错），`toml` 有 1 次命中同仓库 `encoder.py`（置信度 0.369 / S0），1 次命中 `decoder.py`（0.994 / S1），如实按多次试验比率报告，不写成 100% 必中。

### 历史基线（2026-11-15 留存证据，修补前）

两轮独立评测，均按多次试验比率报告（LLM 提案非确定性）。原始记录随本仓库
`submission/evidence/` 与比赛提交材料《佐证材料》提供：`webprobe-eval-20261115.{json,md}`、
`llmfusion-round2-realprojects.json`。

| 项目（语料外） | round2 联网检出（5 次/例） | webprobe 联网检出（2 次/例） | 离线检出上游 | 成功试验置信度 |
|---|---|---|---|---|
| ranger | 5/5 | 1/2 | 0 | 4/5 次 0.997（48 逐字）；1 次 0.3805（4 逐字，top 为 web-source/UNKNOWN） |
| itsdangerous | 5/5 | 1/2 | 0 | 0.995（48 逐字 token） |
| toml | 0/5 | 跳过（查询拉取失败） | 0 | — |
| synapse | 1/5 | 跳过（查询拉取失败） | 0 | 0.992（单次） |

- 两轮安全不变量分别在 20 次 / 4 次试验全部成立；密钥零泄漏。
- ranger 在 round2 有 3/5 次 `top.package` 记为 `web-source/UNKNOWN`（已在 2026-11-25 版通过 `infer_package_from_url()` 修复）。
- 修补前 `webprobe-eval-20261115` 轮 `license_verified_rate` 为 0/2，修补后已在上述 2026-11-25 复测中提升至 11/11。

### 5.1 为什么 0/2：根因诊断与 2026-11-15 修补

事后核查排除了"逻辑写错"这一类原因：两个上游 LICENSE 文件
（`ranger/master/LICENSE`、`pallets/itsdangerous/main/LICENSE.txt`）都存在，
`classify_license_text` 对 GPL-3.0 与 BSD-3-Clause 的标题/条款签名均能正确分类，
`ground_license` 的 URL 拼接也正确。真实失败是**运行时的可观测性与健壮性缺陷**：

| 旧版问题 | 后果 |
|---|---|
| 任何失败一律 `return {}`，不记录原因 | 证据里只剩 `web:llm-inferred`，无法区分"通道没实现""网络超时""文本识别不了"，评委无法核验 |
| 每条 finding 各拉一次同一仓库的 LICENSE（最多 3 次），无缓存 | probe 本身已耗时 30–170 秒，叠加重复请求后 20 秒超时频发 |
| 候选文件名只试 `LICENSE`/`LICENSE.txt`/`LICENSE.md` | `COPYING`（常见于 GPL 项目）、`LICENSE.rst`、`LICENCE`、`docs/LICENSE` 全部漏掉 |
| LICENSE 拉取复用 20 秒完整超时 | 一次核验最坏可额外占用 60 秒 |

本次修补（`src/codeguard/web_evidence.py`）：失败也返回可审计字典、
`provenance.license_grounding` 记录 status / reason / 逐 URL attempts、
同仓库一次 probe 内共享缓存、候选文件名扩到 9 个、LICENSE 拉取独立 8 秒超时。
新增 `scripts/eval_license_grounding.py` 以固定离线夹具跑通
11 个 SPDX 分类用例 + 5 个核验行为用例 + 2 条端到端路径，共 **18/18 通过**，
证据见 `license-grounding-eval-20261115.{json,md}`。

> **口径边界（务必保持）**：该评测 `mode=offline-fixture`，`fetch_source` 由夹具注入，
> 未发起真实网络请求、未使用密钥。它证明的是"通道逻辑正确、可复现、失败可解释"，
> **不能**换算成真实联网的 `license_verified_rate`。真实联网成功率仍是 **0/2**，
> 需要在稳定网络下重跑 `eval_webprobe.py` 才能更新； patched 版本的失败原因会写进
> `license_grounding`，使下一次补跑可定位、可归因。

## 6. 局限（如实披露）

- 召回受大模型提案质量与网络可用性影响，单次不保证必中；以多次试验比率报告。
- 仅覆盖可公开 raw 拉取的项目；私有/需鉴权/非白名单 host 不在范围内。
- 联网命中是**工程补充提示**，不是法律结论；阻断决策仍只由离线门禁做出。
- 多语言走通用词法回退（与工作台一致），精度未单独量化。

## 7. 竞品对比（定位差异，非贬低）

| 能力 | CodeGuard（含联网溯源） | ScanCode / FOSSA / Black Duck 等许可证扫描器 | 直接问通用大模型 |
|---|---|---|---|
| 内联复制片段级溯源（行号+逐字证据） | ✅ 四层指纹+精确验证 | ⚠️ 多以包/文件级声明与片段匹配为主 | ❌ 无证据链 |
| 语料外来源召回 | ✅ 联网溯源（AI 提案+确定性验证） | ⚠️ 依赖其知识库覆盖 | ⚠️ 可能幻觉、无验证 |
| 抗改名/重排/灌注释 | ✅ 角色层+结构边层 | ⚠️ 视实现 | ❌ |
| 离线可复现 / 零依赖 | ✅ 纯标准库 | ❌ 多为商业/重依赖 | ❌ 需联网 |
| 许可证义务推演（SPDX+使用方式） | ✅ 规则引擎 | ✅ 部分 | ⚠️ 不稳定 |
| CI 门禁 / SARIF / CycloneDX | ✅ | ✅ 部分 | ❌ |
| 结论可审计、AI 不越权 | ✅ 判定确定性、AI 仅提案/解读 | ✅ 规则 | ❌ 模型即结论 |
| AI 生成代码溯源定位 | ✅ 设计目标 | ⚠️ 非主打 | ⚠️ |

差异点：传统扫描器强在**已知依赖/声明**的合规清点；CodeGuard 强在**内联复制的片段级
证据链**与**语料外召回**，且把 AI 放在"提案/解读"而非"判定"位置，兼顾召回与可审计。


---

## 真实网络 LICENSE 核验用例（2026-11-15 补充）

复现：`python scripts/eval_license_grounding_realnetwork.py`；证据
`submission/evidence/license-grounding-realnetwork-20261115.{json,md}`。

混合模式：上游提案保持离线确定性夹具（无密钥、无检索查询、不上传源码），
上游 LICENSE 原文通过出厂 `fetch_source` 从**真实公网**拉取。
`pallets/itsdangerous/main/LICENSE.txt` 返回 200（BSD-3-Clause，URL 与 SHA-256 留存），
`ground_license` 确定性分类为 verified，`run_web_probe` 把该发现的 provenance 从
`web:llm-inferred` 升级为 `web:license-text-verified`；不阻断、封顶 S3、离线索引不变、
审计字段齐全等安全不变量全部成立。

**边界**：样本量 1，提案环节仍为夹具。它把「通道已实现」推进到「在真实原文上可核验」，
但**不改写** `webprobe-eval-20261115.json` 的 `license_verified_rate 0/2`，
也不与 18/18 的纯离线夹具评测合并成成功率。完整真实联网（含 LLM 提案）的成功率
仍须自配密钥、稳定网络下用 `scripts/eval_webprobe.py` 测量。
