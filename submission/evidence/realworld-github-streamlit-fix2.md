# 真实 GitHub 项目扫描

- 仓库：1；采样/成功扫描：40 / 40；发现：32；阻断级发现：0
- 生成时间：2026-10-23T19:16:31Z
- 方法：deterministic SHA-256 rank by repository-relative path；文件大小 900–90000 B；目标许可证按仓库 LICENSE；使用方式 distribution
- 全局单文件耗时 p50 / p95 / max：487 / 3541 / 5276 ms；真实 vendoring 命中：0

| 项目 | commit | 许可证 | 采样 | 发现 | S0/S1/S2/S3/S4 | 阻断 | p95 ms |
|---|---|---|---|---|---|---|---|
| streamlit | `76ac4836ecd3` | Apache-2.0 | 40 | 32 | 26/0/6/0/0 | 0 | 3541 |

## 阻断级发现（需人工复核）

无。

## 回归案例

- `setuptools/_vendor/wheel/_commands/__init__.py`：S3 (false block) → S2 (review)；证据：6 generic argparse spans, coverage 0.222, 5 verbatim tokens, confidence 0.671

## 真实 vendoring 命中


## 说明

- 真实仓库扫描不做变异；阻断级发现必须逐条人工复核，可能包含真实 vendoring、通用代码形状或误报。
- 采样文件数与仓库总量不同；本结果不外推到未采样文件或未测试项目。
- 目标许可证按仓库 LICENSE 固定；更换使用方式（内部/网络服务）会改变风险等级。
