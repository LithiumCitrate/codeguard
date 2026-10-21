# CodeGuard 工作台使用说明

## Windows 软件包

解压 CodeGuard-Windows-x64.zip，进入 CodeGuard 文件夹，双击 CodeGuard.exe。
程序自带 Python 运行环境，自动选择空闲端口并打开默认浏览器；无需安装 Python、配置 API Key 或连接互联网。
保留命令行窗口即可持续使用，关闭窗口结束服务。需要重新访问时，复制窗口显示的本机网址。
不要将 EXE 单独移走；_internal、.codeguard、third-party-source 与许可文件应随整个文件夹保留。
本次在 Windows 11 x64 / CPython 3.14.3 验证；其他系统尚未验证。

## 源码运行

需要 Python 3.9 以上；在项目目录双击“启动工作台.cmd”，或执行 `python launch.py`。
也可安装后执行 `codeguard-web --workspace .codeguard`。
本地网页服务仅监听 127.0.0.1；不是公网托管站点。

干净源码包不包含下载语料。首次运行先执行 `python scripts/restore_corpus.py`（需要联网，固定到本次评测的原包与文件哈希），再执行 `pip install .`、`codeguard index`、`codeguard benchmark --files 24`。
已有Windows包中的原始发布包可通过 `--archive-dir` 传给恢复脚本，免去再次下载；不会安装或执行这些上游源码。

## 界面

工作台是一屏控制台，三个分区用地址栏深链接区分：`#review`（审查）、`#license`（许可推演）、`#about`（方法与边界）。
审查页顶部的分级环 S0–S4 读的是**最近一次真实审查**的最高风险与置信度，三条刻度分别是最长逐字命中、覆盖率与命中片段比例；
左侧「语料」「本次审查」与右侧「引擎」「导出」四个字段面板全部来自 `/api/health` 与本次扫描结果，没有任何占位数字。
审查完成后导出按钮才出现，导出内容与页面证据同源。右上角可切换深浅主题（记住选择），界面字体 Saira 随包分发、离线加载。

## 建议演示流程（约 4 分钟）

1. 展示索引规模和本地运行方式，解释为何需要检查内联代码来源。
2. 点击“变量改名”，说明来源已知、变异受控；目标设 MIT、使用方式设“对外分发”。点击扫描。
3. 查看来源、风险、覆盖率和最长逐字 token；展开证据对照，解释多层指纹如何识别改写。
4. 导出出处证书与 CycloneDX SBOM；说明可供 CI 与供应链工具消费。
5. 切换“内部使用”重新扫描，说明使用方式如何影响工程判断。
6. 选择“独立实现”，观察当前语料范围内的结果；强调没有命中不能证明普遍安全。
7. 切换“许可证推演”，尝试 GPL-3.0-only 到 MIT、对外分发，查看冲突与义务。
8. 展示“方法与边界”，说明轻量模型、开源复用与限制；AI 使用披露在 README、技术报告与导出的出处证书里（`ai_usage` 字段）。

## 隐私和限制

输入代码不执行、不上传、不持久保存；分析结果由浏览器手动导出。
运行时网页强制使用离线模板，不调用环境变量配置的大模型服务。
支持导入单个源文件（不超过 200 KB）或粘贴代码，优先使用 Python。其他语言的准确性未充分评估。
多文件目录审查与 CI 门禁继续通过命令行执行。
语料缺失或与索引记录的 SHA-256 不一致时拒绝扫描，避免把“没法检查”误展示成“没有风险”。
来源候选和许可证义务均需人工核查；模型评分不是校准概率，产品不提供法律裁定。

## 开放范围

应用代码使用 Apache-2.0；上游语料保持各自授权。
发布包附 third-party-source 原始源码发布包、语料内 LICENSE/COPYING/NOTICE、资源哈希清单。
应用不安装、不执行、不链接第三方语料包。下载脚本保留上游来源和精确版本，供再次核查与复现。
对外发布前团队应审核资源清单和自身权利边界，并如实说明 Codex 参与开发的环节。

## 在 Windows 重建应用包

在项目目录建立隔离构建环境：`python -m venv build/venv-exe`，再用该环境的 Python 安装 `pyinstaller`。
若本机 user site 装有旧版 `pathlib` 后向包，PyInstaller 会拒绝启动；用仓库内虚拟环境可绕开，不必改动全局环境。
先运行 `python scripts/prepare_release_corpus.py` 核验语料原包并保留许可材料。
使用 `release/build-env/Scripts/python.exe -m PyInstaller CodeGuard.spec --noconfirm` 编译启动器；生成目录应与 `scripts/package_release.py` 期待的 `release/app/CodeGuard` 对齐，或直接使用以下命令：

```
build/venv-exe/Scripts/python.exe -m PyInstaller --noconfirm --onedir --name CodeGuard --paths src --add-data "src/codeguard/data:codeguard/data" --add-data "src/codeguard/static:codeguard/static" --distpath release/app --workpath release/build launch.py
python scripts/package_release.py
python scripts/smoke_app.py
```

报告再生成需要 reportlab 和本机宋体；官方 Schema 验证脚本需要开发期 jsonschema/referencing，以及 `release/schema` 中官方1.6版Schema文件。这些不属于软件运行依赖。
每次重建后检查 `release/SHA256SUMS.txt`；应用包冒烟测试只终止自己启动的测试进程。
