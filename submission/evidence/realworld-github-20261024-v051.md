# 真实 GitHub 项目扫描

- 仓库：27；采样/成功扫描：1119 / 1119；发现：2098；阻断级发现：0
- 生成时间：2026-10-23T19:25:46Z
- 方法：deterministic SHA-256 rank by repository-relative path；文件大小 900–90000 B；目标许可证按仓库 LICENSE；使用方式 distribution
- 全局单文件耗时 p50 / p95 / max：240 / 1671 / 5056 ms；真实 vendoring 命中：56

| 项目 | commit | 许可证 | 采样 | 发现 | S0/S1/S2/S3/S4 | 阻断 | p95 ms |
|---|---|---|---|---|---|---|---|
| pip | `f6e52de21c12` | MIT | 40 | 74 | 66/0/8/0/0 | 0 | 2431 |
| pip-vendor | `f6e52de21c12` | MIT | 60 | 103 | 74/20/9/0/0 | 0 | 1611 |
| setuptools | `301e27a484f1` | MIT | 40 | 59 | 52/0/7/0/0 | 0 | 1270 |
| setuptools-vendor | `301e27a484f1` | MIT | 60 | 67 | 32/20/15/0/0 | 0 | 1484 |
| pytest | `49ea4d08714f` | MIT | 40 | 106 | 93/0/13/0/0 | 0 | 1569 |
| sqlmap | `9b0e26256052` | GPL-2.0-or-later | 40 | 138 | 120/1/17/0/0 | 0 | 1648 |
| mitmproxy | `c8a55fff43df` | MIT | 40 | 54 | 42/1/11/0/0 | 0 | 1070 |
| ansible | `ba22fe441408` | GPL-3.0-only | 40 | 50 | 30/3/17/0/0 | 0 | 1180 |
| yt-dlp | `fa9886678eb6` | Unlicense | 40 | 49 | 37/2/10/0/0 | 0 | 697 |
| black | `333d8a97d2ad` | MIT | 39 | 43 | 24/0/19/0/0 | 0 | 1949 |
| mypy | `62dad9ad6e69` | MIT | 40 | 120 | 93/1/26/0/0 | 0 | 2525 |
| rich | `9d8f9a372cc5` | MIT | 40 | 58 | 53/0/5/0/0 | 0 | 1329 |
| scrapy | `171ccbedb734` | BSD-3-Clause | 40 | 89 | 70/2/17/0/0 | 0 | 607 |
| celery | `682754c16ac9` | BSD-3-Clause | 40 | 90 | 55/0/35/0/0 | 0 | 804 |
| sphinx | `c386315ff193` | BSD-2-Clause | 40 | 94 | 78/0/16/0/0 | 0 | 1728 |
| httpie | `5b604c37c6c6` | BSD-3-Clause | 40 | 33 | 24/0/9/0/0 | 0 | 505 |
| localstack | `8b9a79f05846` | Apache-2.0 | 40 | 70 | 44/0/26/0/0 | 0 | 759 |
| streamlit | `76ac4836ecd3` | Apache-2.0 | 40 | 32 | 26/0/6/0/0 | 0 | 737 |
| salt | `03d8a9816865` | Apache-2.0 | 40 | 31 | 19/0/12/0/0 | 0 | 1365 |
| datasets | `ef61228a5756` | Apache-2.0 | 40 | 52 | 41/0/11/0/0 | 0 | 1083 |
| openai-python | `56a55f243960` | Apache-2.0 | 40 | 31 | 25/2/4/0/0 | 0 | 958 |
| freqtrade | `12e0878f8554` | AGPL-3.0-only | 40 | 52 | 36/3/13/0/0 | 0 | 511 |
| airflow | `9ef5f3d463f0` | Apache-2.0 | 40 | 76 | 63/0/13/0/0 | 0 | 1595 |
| keras | `184cdcb83c1e` | Apache-2.0 | 40 | 116 | 83/3/30/0/0 | 0 | 2933 |
| pandas | `4e78ed1653e9` | BSD-3-Clause | 40 | 150 | 116/0/34/0/0 | 0 | 1856 |
| numpy | `ef046f8df8bd` | BSD-3-Clause | 40 | 60 | 43/1/16/0/0 | 0 | 1982 |
| aiohttp | `2c94f31a22c2` | Apache-2.0 | 40 | 201 | 177/0/24/0/0 | 0 | 2088 |

## 阻断级发现（需人工复核）

无。

## 回归案例

- `setuptools/_vendor/wheel/_commands/__init__.py`：S3 (false block) → S2 (review)；证据：6 generic argparse spans, coverage 0.222, 5 verbatim tokens, confidence 0.671

## 真实 vendoring 命中

- **pip-vendor**：预期来源包 requests, urllib3, packaging；命中 30 条
  - urllib3@2.8.0:urllib3-2.8.0/src/urllib3/connectionpool.py ← [1, 1191]（conf 1.00，S1）
  - urllib3@2.8.0:urllib3-2.8.0/src/urllib3/connection.py ← [1005, 1091]（conf 0.64，S0）
  - urllib3@2.8.0:urllib3-2.8.0/src/urllib3/util/retry.py ← [1087, 1095]（conf 0.45，S0）
  - packaging@26.3:packaging-26.3/src/packaging/licenses/__init__.py ← [32, 198]（conf 0.99，S1）
  - urllib3@2.8.0:urllib3-2.8.0/src/urllib3/contrib/emscripten/response.py ← [1, 281]（conf 0.99，S1）
  - urllib3@2.8.0:urllib3-2.8.0/src/urllib3/contrib/emscripten/fetch.py ← [1, 726]（conf 0.99，S1）
- **setuptools-vendor**：预期来源包 packaging；命中 26 条
  - packaging@26.3:packaging-26.3/src/packaging/tags.py ← [141, 147]（conf 0.39，S0）
  - packaging@26.3:packaging-26.3/src/packaging/_ranges.py ← [4, 836]（conf 0.99，S1）
  - packaging@26.3:packaging-26.3/src/packaging/pylock.py ← [1, 943]（conf 1.00，S1）
  - packaging@26.3:packaging-26.3/src/packaging/direct_url.py ← [113, 122]（conf 0.63，S0）
  - packaging@26.3:packaging-26.3/src/packaging/ranges.py ← [327, 336]（conf 0.42，S0）
  - packaging@26.3:packaging-26.3/src/packaging/_structures.py ← [5, 33]（conf 1.00，S1）

## 说明

- 真实仓库扫描不做变异；阻断级发现必须逐条人工复核，可能包含真实 vendoring、通用代码形状或误报。
- 采样文件数与仓库总量不同；本结果不外推到未采样文件或未测试项目。
- 目标许可证按仓库 LICENSE 固定；更换使用方式（内部/网络服务）会改变风险等级。
