# CodeGuard 多语言语法感知归一化 · 离线基准评测

- 生成时间：2026-11-26T05:07:57Z
- 索引指纹：`121bb5650b959fc2912e5285f57fe09d`（documents=1717, chunks=127156, packages=32）
- 测试模式：纯标准库、完全离线，使用产品扫描链路（`FingerprintIndex` + `Scanner` + 逻辑回归判定模型）
- 总体文件级检出率：**124 / 128（96.9%）**；同包级归因：**128 / 128（100.0%）**
- 误阻断数：干净与跨语言互查 `0 / 61`，正例跨包误阻断 `0`（合计 `0`）
- 总耗时：82.60s

## 按语言变异检出率

| 语言 | 抽样文件 | 包来源 | identity | comment_inject | reformat | rename | 文件级检出 | 同包归因 | Top-1 | 跨包误阻断 | 耗时 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| c | 8 | git, nginx, radare2 | 100% | 100% | 100% | 100% | **100.0%** (32/32) | 100.0% | 100.0% | 0 | 29.71s |
| go | 8 | cobra, minio | 88% | 88% | 88% | 88% | **87.5%** (28/32) | 100.0% | 75.0% | 0 | 19.31s |
| javascript | 8 | django, fastapi, jquery, pydantic, radare2 | 100% | 100% | 100% | 100% | **100.0%** (32/32) | 100.0% | 100.0% | 0 | 10.40s |
| rust | 8 | html5ever, pydantic | 100% | 100% | 100% | 100% | **100.0%** (32/32) | 100.0% | 100.0% | 0 | 10.23s |

### 未精确命中的原文件路径说明

- `minio-7aac2a2c5b/cmd/bootstrap-peer-server_gen_test.go`（go / `minio`）：同包内存在结构/生成模板完全一致的兄弟文件，命中归因到 `minio-7aac2a2c5b/cmd/batch-expire_gen_test.go, minio-7aac2a2c5b/cmd/background-newdisks-heal-ops_gen_test.go`。

## 干净负例与跨语言互查

- Python 独立实现负例：9 条；C/Go/JS/Rust 自研干净负例：8 条；跨语言互查探针：44 条（共 61 条）
- 阻断级误报（S3/S4）：**0 / 61**
- 任意弱命中（含 S0/S1 观察）：2 / 61；耗时 12.94s

> 复现：`PYTHONPATH=src python scripts/eval_multilang.py`
