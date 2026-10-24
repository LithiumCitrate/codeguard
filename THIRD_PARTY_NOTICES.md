# 开源第三方资源使用清单（Third-Party Notices）

## 2026-10-11 应用包补充

源码仓库与 Windows 离线发布包的范围不同：离线应用包额外附带只读语料、原始上游源码发布包与对应许可文件。
这些资源保持原许可证，不能统称 Apache-2.0。`submission/evidence/corpus-integrity.json` 记录精确版本、来源 URL、原包 SHA-256 与许可文件位置。
程序运行不安装、不执行、不链接这些语料项目；上游原始源码包位于 `third-party-source`，供来源核查和对应源码获取。
2026-10-24 复核：语料已扩至 33 包 / 1717 文件（PyPI sdist 20 包 + GitHub 浅克隆 13 仓库，提交哈希记于语料清单 sdist_sha256 字段）；离线包内每个语料包目录均随附上游许可/声明文件（sync_corpus_licenses.py 保证，package_release.py 对缺证包拒绝打包）。下文“不再分发”描述仅适用于原源码仓库获取方式，离线包以上述说明为准。
Windows 包还包含 CPython 3.14.3（PSF 授权及其捆绑许可，见随包 PYTHON-LICENSE.txt）及 PyInstaller 6.22.3 启动器（GPL 加 bootloader exception，见 PYINSTALLER-COPYING.txt）。
PyInstaller、setuptools、packaging 等打包工具不作为应用运行依赖；其构建用途应在团队资源清单中如实记录。
网页、修复、文档与打包使用 Codex 辅助生成；团队需确认人工审核、验证和权利边界，不应把所有内容声称为独立手写。

逐项列出：资源名称、类型与版本来源、许可证、使用方式、关键义务与限制、自研边界、合规状态。

- 本仓库**不内置任何第三方源码**。语料包由 `codeguard corpus` 在使用者本机按需下载到
  `.codeguard/corpus/`（已被 `.gitignore` 排除），仅作为只读输入构建指纹索引。
- CodeGuard 自研代码与所有第三方资源的边界在每一处引用点都有注释说明（模块首段 docstring）。
- 随应用分发的第三方**资产**只有界面字体 Saira（OFL-1.1，见第 1 节表格），它与只读语料一起构成本作品的全部外部内容；检测算法不依赖任何第三方字形、图片或代码。

## 1. 自研与标准基础设施

| 资源名称 | 类型 / 版本来源 | 许可证 | 使用方式 | 关键义务与限制 | 自研边界 | 合规状态 |
|---|---|---|---|---|---|---|
| CodeGuard 全部源码 | 本仓库，`src/codeguard/*` | Apache-2.0 | 本项目原创实现并开源 | 需保留 LICENSE 与 NOTICE；含专利授权条款 | 全部为自研：归一化、指纹、LSH、CMS、验证、许可证推理、判定模型、CLI、报告 | 合规 |
| Python 标准库（`tokenize`、`hashlib`、`struct`、`zlib`、`argparse`、`urllib` 等） | 运行时依赖，Python ≥ 3.9 | PSF-2.0 / Python-2.0 | 仅作为运行库调用，未修改、未再分发其源码 | PSF 许可仅需保留版权声明；本项目不重新分发 CPython | 我们自研的是四层指纹、验证与打分逻辑；标准库只提供 tokenizer、哈希、压缩等原语 | 合规（内部使用与再分发脚本均满足） |
| SPDX License List | https://spdx.org/licenses/ ，快照 2026-10 存为 `src/codeguard/data/spdx_licenses.json` | CC0-1.0 | 数据文件随仓库分发，用于 SPDX 标识规范化与别名归一 | CC0 无义务（已放弃著作权），仍保留来源说明 | 自研部分为解析链与义务模型；SPDX 只提供标识与名称 | 合规 |
| Keep a Changelog / SemVer 约定 | 仅文档写作规范（未复制代码或数据） | 文本约定 | `CHANGELOG.md` 排版参考 | 无代码级义务 | 文档结构参考，内容全部自撰 | 合规 |
| Saira 可变字体（界面字体） | Saira Project Authors，随应用分发 `src/codeguard/static/fonts/Saira.ttf` | SIL OFL 1.1 | 仅作网页界面字体，经本机 `@font-face` 加载；不修改字形 | 保留版权声明与许可证（`static/fonts/Saira-OFL.txt` 同目录分发）；若修改字体文件须改用新名称 | 界面样式与页面实现为自研；字体只提供字形 | 合规 |

## 2. 语料库（只读输入，不在仓库中分发）

GitHub 克隆组（v0.5.0 起，`scripts/expand_corpus_github.py` 浅克隆，根目录许可文件随语料目录分发）：fastapi(MIT)、httpx(BSD-3)、requests(Apache-2.0)、flask(BSD-3)、pydantic(MIT)、django(BSD-3)、git(GPL-2.0-only)、nginx(BSD-2)、radare2(LGPL-3.0-only)、minio(AGPL-3.0-only)、cobra(Apache-2.0)、jquery(MIT)、html5ever(Apache-2.0/MIT 双许可)。

`codeguard corpus` 默认拉取以下 PyPI sdist；许可证由本项目解析链自动判定，"解析来源"列给出该
SPDX 标识是从哪个元数据字段得到的（PEP 639 表达式 / legacy license 字段 / trove 分类 / 源码头部）。
使用方式统一为：**下载 → 本地解析构建指纹索引 → 不入库、不再分发、不修改上游源码**。

| 资源名称 | 类型 / 版本来源 | 许可证（SPDX） | 解析来源 | 使用方式 | 关键义务与限制 | 自研边界 | 合规状态 |
|---|---|---|---|---|---|---|---|
| six | 1.17.0，PyPI sdist | MIT | license-field | 只读语料 | 保留版权声明与许可文本（若分发其代码） | 未复制其代码进本产品 | 合规 |
| iniconfig | 2.3.0 | MIT | pep639-expression | 只读语料 | 同上 | 同上 | 合规 |
| pyyaml | 6.0.3 | MIT | license-field | 只读语料 | 同上 | 同上 | 合规 |
| urllib3 | 2.8.0 | MIT | pep639-expression | 只读语料 | 同上 | 同上 | 合规 |
| fava | 1.30.16 | MIT | pep639-expression | 只读语料 | 同上 | 同上 | 合规 |
| requests | 2.34.2 | Apache-2.0 | license-field | 只读语料 | 保留声明与 NOTICE；本项目不分发其源码 | 同上 | 合规 |
| click | 8.5.0 | BSD-3-Clause | pep639-expression | 只读语料 | 禁止用其名义背书 | 同上 | 合规 |
| python-dotenv | 1.2.4 | BSD-3-Clause | license-field | 只读语料 | 同上 | 同上 | 合规 |
| snowballstemmer | 3.1.1 | BSD-3-Clause | license-field | 只读语料 | 同上 | 同上 | 合规 |
| mpmath | 1.4.1 | BSD-3-Clause | pep639-expression | 只读语料 | 同上 | 同上 | 合规 |
| websockets | 17.2 | BSD-3-Clause | pep639-expression | 只读语料 | 同上 | 同上 | 合规 |
| packaging | 26.3 | BSD-2-Clause | pep639-expression | 只读语料 | 保留声明 | 同上 | 合规 |
| tqdm | 4.70.1 | MPL-2.0 | license-field | 只读语料 | 文件级 copyleft：被修改文件须保持 MPL | 未修改任何文件 | 合规 |
| argparse | 1.4.0 | PSF-2.0 | license-field | 只读语料 | PSF 许可 | 同上 | 合规 |
| defusedxml | 0.7.1 | PSF-2.0 | trove-classifier | 只读语料 | PSF 许可 | 同上 | 合规 |
| legacy-cgi | 2.6.4 | PSF-2.0 | pep639-expression | 只读语料 | PSF 许可 | 同上 | 合规 |
| paramiko | 5.0.0 | LGPL-2.1 | pep639-expression | 只读语料（copyleft 检测用例） | LGPL 库本身需可替换/可重链接；本产品仅读取源码构建索引，不链接其代码 | 本产品与 paramiko 无链接关系，无义务触发 | 合规 |
| glances | 4.5.7 | LGPL-3.0-only | pep639-expression | 只读语料（copyleft 检测用例） | 同上 | 同上 | 合规 |
| pylint | 4.1.2 | GPL-2.0-or-later | pep639-expression | 只读语料（copyleft 检测用例） | 若内联其代码则组合作品须整体 GPL；本产品未复制任何片段 | 自研实现，未参考其源码结构 | 合规 |
| mercurial | 7.2.4 | GPL-2.0-or-later | pep639-expression | 只读语料（copyleft 检测用例） | 同上 | 同上 | 合规 |

> 说明：把 GPL/LGPL/MPL 项目**作为检测目标语料**与**把它们的代码引入本产品**是两件完全不同的事。
> 前者只构成运行时读取与分析，不产生 copyleft 传染；本产品源码保持 Apache-2.0，且没有任何模块
> 由上述 copyleft 源码派生。这也是 CodeGuard 自身必须能自证清白的地方——`codeguard scan .`
> 扫自己，结果见 `docs/TUTORIAL.md`。

## 3. 未使用清单（避免评审误解）

- 未使用任何机器学习框架（NumPy / scikit-learn / PyTorch 均未引入）：逻辑回归、AUC、分组留出为自研标准库实现。
- 未将任何外部代码相似度数据集用作训练或索引语料：变异用例由 `mutations.py` 生成，索引负例为 `data/negatives/` 自研代码。
- 未调用任何大模型 API 作为默认路径：`llm.py` 的外部适配层需显式环境变量才生效。

## 4. 外部评测数据与输出规范（不随仓库分发）

| 资源 | 版本/来源 | 许可证 | 使用方式 | 义务/边界 |
|---|---|---|---|---|
| OpenAI HumanEval | canonical solutions，URL + SHA-256 固定（`b796127e...06979ef`） | MIT | `scripts/eval_humaneval.py` 仅作外部干净负例评测；缓存于 `.codeguard/external/`（gitignored），不进入索引、不随仓库或应用包分发 | 保留 MIT 版权与许可；结果不得表述为真实模型输出；0/164 只可写成“0 观测 + 单侧上限 1.81%” |
| 真实 GitHub 项目（10 个） | requests/flask/fastapi/httpx/poetry/pip/setuptools/pytest/sqlmap/mitmproxy，浅克隆并记录 commit | 各仓库 LICENSE（Apache-2.0 / MIT / BSD-3-Clause / GPL-2.0-or-later） | `scripts/eval_realworld.py` 仅本地只读扫描；仓库留在 `.codeguard/github/`（gitignored），不进入索引、不随仓库或应用包分发 | 保留 commit 与许可记录；证据只存路径/发现，不存源码全文 |
| SARIF 2.1.0 | OASIS 开放规范，https://json.schemastore.org/sarif-2.1.0.json | OASIS 开放规范 | 按其公开 JSON 字段输出 `*.sarif`，供 GitHub Code Scanning / IDE 消费 | 未复制规范正文或 schema 文件；`report.to_sarif()` 为自研实现 |
