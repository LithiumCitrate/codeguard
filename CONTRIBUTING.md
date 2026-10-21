# 贡献指南

欢迎把 CodeGuard 接到你自己的流水线里，也欢迎补充语言支持、许可证知识与实验用例。

## 环境

```bash
git clone <your-fork>
cd codeguard
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m codeguard doctor
```

运行时**只依赖 Python 标准库**（>=3.9）。唯一需要网络的是 `codeguard corpus`（从 PyPI 拉取 sdist 作为语料）；评测与扫描完全离线。

## 开发流程

1. 从 `main` 切分支：`feat/...`、`fix/...`、`docs/...`。
2. 改动算法层时，必须同步更新或新增 `tests/` 用例；改动检索/打分逻辑时，必须重跑
   `python -m codeguard benchmark --files 12 --chars 4000`，并在 PR 描述里贴出检出率与误报的变化。
3. `python -m pytest`（或 `python -m unittest discover -s tests`）全绿。
4. 提交信息用祈使句，说明**为什么**这样改，而不只是改了什么。

## 代码约定

- 零第三方运行时依赖。这条是产品定位的一部分：评审要在任何机器上一条命令复现实验，不能卡在环境上。
- 每个模块首段 docstring 说明它的设计取舍（为什么这么做、代价是什么），而不是罗列 API。
- 注释只在"为什么"不显然时写：隐藏约束、微妙的不变量、针对某个具体 bug 的绕行方案。
- 任何影响输出格式的改动都要同步 `report.py` 的 schema 版本号（`codeguard.provenance/v1`、CycloneDX `specVersion`）。
- 索引格式改动必须递增 `INDEX_VERSION`，并保持 `load()` 对旧版本明确报错而不是静默错误匹配。

## 测试与实验

`tests/` 只用固定样本（fixtures）运行，不访问网络，秒级完成。量化评测在
`benchmark` 子命令里，用例全部由仓库自带的 `mutations.py` 生成，负例来自
`src/codeguard/data/negatives/`（为本项目从零编写的独立实现）。

新增变异类型时，请同时：
- 在 `mutations.MUTATIONS` 注册，并在 `describe()` 给出中文标签；
- 确认变异后的文件仍可 `compile()`（否则你测的是回退词法器，不是指纹）；
- 在 `CHANGELOG.md` 记录。

## 许可证与来源边界

- 本项目以 Apache-2.0 发布，保留 `NOTICE`。
- 语料包源码**不入库**，只作为只读输入；新增语料必须同时记录其 SPDX 标识与解析来源，并更新 `THIRD_PARTY_NOTICES.md`。
- 不接受把 GPL/AGPL/LGPL 源码复制进本仓库实现的 PR；参考公开接口设计、独立实现是允许的。
- 引入新的第三方依赖需要说明：许可证、使用方式、义务限制、与自研代码的边界（PR 模板里有这一节）。

## 行为准则

对事不对人。评审关注的是可复现的证据，不是提交者的资历。
