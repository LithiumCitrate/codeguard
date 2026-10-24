# 真实 GitHub 项目扫描

- 仓库：5；采样/成功扫描：168 / 168；发现：263；阻断级发现：0
- 生成时间：2026-10-24T04:41:34Z
- 方法：deterministic SHA-256 rank by repository-relative path；文件大小 900–90000 B；目标许可证按仓库 LICENSE；使用方式 distribution
- 全局单文件耗时 p50 / p95 / max：232 / 2215 / 6268 ms；真实 vendoring 命中：0

| 项目 | commit | 许可证 | 采样 | 发现 | S0/S1/S2/S3/S4 | 阻断 | p95 ms |
|---|---|---|---|---|---|---|---|
| jinja | `5ef70112a1ff` | BSD-3-Clause | 25 | 56 | 49/2/5/0/0 | 0 | 5176 |
| starlette | `a85a5c36d779` | BSD-3-Clause | 35 | 81 | 70/0/11/0/0 | 0 | 1301 |
| typer | `a5882dedf0bc` | MIT | 28 | 109 | 88/17/4/0/0 | 0 | 1663 |
| pyinstaller | `b206650681ec` | GPL-2.0-or-later | 40 | 8 | 7/1/0/0/0 | 0 | 379 |
| gin | `0f09c3a9b462` | MIT | 40 | 9 | 6/0/3/0/0 | 0 | 1879 |

## 阻断级发现（需人工复核）

无。

## 回归案例

- `setuptools/_vendor/wheel/_commands/__init__.py`：S3 (false block) → S2 (review)；证据：6 generic argparse spans, coverage 0.222, 5 verbatim tokens, confidence 0.671

## 真实 vendoring 命中


## 说明

- 真实仓库扫描不做变异；阻断级发现必须逐条人工复核，可能包含真实 vendoring、通用代码形状或误报。
- 采样文件数与仓库总量不同；本结果不外推到未采样文件或未测试项目。
- 目标许可证按仓库 LICENSE 固定；更换使用方式（内部/网络服务）会改变风险等级。
