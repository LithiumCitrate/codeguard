# 真实 GitHub 项目扫描

- 仓库：12；采样/成功扫描：447 / 447；发现：320；阻断级发现：0
- 生成时间：2026-10-20T09:39:01Z
- 方法：deterministic SHA-256 rank by repository-relative path；文件大小 900–90000 B；目标许可证按仓库 LICENSE；使用方式 distribution
- 全局单文件耗时 p50 / p95 / max：182 / 1090 / 3717 ms；真实 vendoring 命中：50

| 项目 | commit | 许可证 | 采样 | 发现 | S0/S1/S2/S3/S4 | 阻断 | p95 ms |
|---|---|---|---|---|---|---|---|
| requests | `611c6162cbc4` | Apache-2.0 | 17 | 12 | 12/0/0/0/0 | 0 | 1949 |
| flask | `d086db856be1` | BSD-3-Clause | 22 | 17 | 16/1/0/0/0 | 0 | 1088 |
| fastapi | `051bdfe2da49` | MIT | 27 | 23 | 19/2/2/0/0 | 0 | 888 |
| httpx | `b5addb64f016` | BSD-3-Clause | 21 | 24 | 23/0/1/0/0 | 0 | 1423 |
| poetry | `38a86661d2ae` | MIT | 40 | 54 | 53/0/1/0/0 | 0 | 724 |
| pip | `f6e52de21c12` | MIT | 40 | 10 | 10/0/0/0/0 | 0 | 522 |
| pip-vendor | `f6e52de21c12` | MIT | 60 | 45 | 25/19/1/0/0 | 0 | 893 |
| setuptools | `301e27a484f1` | MIT | 40 | 7 | 7/0/0/0/0 | 0 | 766 |
| setuptools-vendor | `301e27a484f1` | MIT | 60 | 38 | 16/20/2/0/0 | 0 | 1146 |
| pytest | `49ea4d08714f` | MIT | 40 | 31 | 27/0/4/0/0 | 0 | 1155 |
| sqlmap | `9b0e26256052` | GPL-2.0-or-later | 40 | 46 | 40/0/6/0/0 | 0 | 1156 |
| mitmproxy | `c8a55fff43df` | MIT | 40 | 13 | 11/1/1/0/0 | 0 | 768 |

## 阻断级发现（需人工复核）

无。

## 回归案例

- `setuptools/_vendor/wheel/_commands/__init__.py`：S3 (false block) → S2 (review)；证据：6 generic argparse spans, coverage 0.222, 5 verbatim tokens, confidence 0.671

## 真实 vendoring 命中

- **pip-vendor**：预期来源包 requests, urllib3, packaging；命中 26 条
  - urllib3@2.8.0:urllib3-2.8.0/src/urllib3/connectionpool.py ← [1, 1191]（conf 1.00，S1）
  - urllib3@2.8.0:urllib3-2.8.0/src/urllib3/util/url.py ← [1151, 1163]（conf 0.63，S0）
  - packaging@26.3:packaging-26.3/src/packaging/licenses/__init__.py ← [32, 198]（conf 1.00，S1）
  - urllib3@2.8.0:urllib3-2.8.0/src/urllib3/contrib/emscripten/response.py ← [1, 281]（conf 1.00，S1）
  - urllib3@2.8.0:urllib3-2.8.0/src/urllib3/contrib/emscripten/fetch.py ← [1, 726]（conf 1.00，S1）
  - urllib3@2.8.0:urllib3-2.8.0/src/urllib3/util/proxy.py ← [1, 43]（conf 1.00，S1）
- **setuptools-vendor**：预期来源包 packaging；命中 24 条
  - packaging@26.3:packaging-26.3/src/packaging/tags.py ← [141, 147]（conf 0.45，S0）
  - packaging@26.3:packaging-26.3/src/packaging/_ranges.py ← [4, 836]（conf 1.00，S1）
  - packaging@26.3:packaging-26.3/src/packaging/pylock.py ← [1, 943]（conf 1.00，S1）
  - packaging@26.3:packaging-26.3/src/packaging/direct_url.py ← [113, 122]（conf 0.64，S0）
  - packaging@26.3:packaging-26.3/src/packaging/_structures.py ← [5, 33]（conf 1.00，S1）
  - packaging@26.3:packaging-26.3/src/packaging/_parser.py ← [1, 418]（conf 1.00，S1）

## 说明

- 真实仓库扫描不做变异；阻断级发现必须逐条人工复核，可能包含真实 vendoring、通用代码形状或误报。
- 采样文件数与仓库总量不同；本结果不外推到未采样文件或未测试项目。
- 目标许可证按仓库 LICENSE 固定；更换使用方式（内部/网络服务）会改变风险等级。
