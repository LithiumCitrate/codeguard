# GitHub 语料提交锁定表

语料库中的 GitHub 仓库按**具体提交**锁定，而非随 HEAD 漂移。下表 commit 为浅克隆时 `git rev-parse HEAD` 的完整 SHA，逐字记录在语料清单条目的 `sdist_sha256` 字段（`git:<sha>`），可据此精确复现语料。

| 仓库 | 许可证 | 语言 | 文件数 | 锁定提交 (commit) | 来源 |
|---|---|---|---|---|---|
| cobra | Apache-2.0 | generic | 36 | `adbc8813901bba65827259daa8e22ff94ec1f30e` | https://github.com/spf13/cobra |
| django | BSD-3-Clause | python | 120 | `1b40abab06d248ee409fa8b7a8dfb6312de6ca08` | https://github.com/django/django |
| fastapi | MIT | python | 120 | `69ddc2badf9da1123bba4d360225ae6b085985f6` | https://github.com/tiangolo/fastapi |
| flask | BSD-3-Clause | python | 69 | `d086db856be187255b8ec61ef409357393020f32` | https://github.com/pallets/flask |
| git | GPL-2.0-only | generic | 120 | `7e34d8174dcda3435d1404c9a30bef46afe6c13e` | https://github.com/git/git |
| html5ever | Apache-2.0 | generic | 74 | `7760920edff08e6dfd4b62affee39d8084e9dc45` | https://github.com/servo/html5ever |
| httpx | BSD-3-Clause | python | 55 | `b5addb64f0161ff6bfe94c124ef76f6a1fba5254` | https://github.com/encode/httpx |
| jquery | MIT | generic | 120 | `c2f27864e4ffc2d1409c289fcb9a42b6165dfeaf` | https://github.com/jquery/jquery |
| minio | AGPL-3.0-only | generic | 120 | `7aac2a2c5b7c882e68c1ce017d8256be2feea27f` | https://github.com/minio/minio |
| nginx | BSD-2-Clause | generic | 120 | `9a7439fd79076de03c408de136ba1772347030c2` | https://github.com/nginx/nginx |
| pydantic | MIT | generic | 120 | `37dc34b4f001191b4f3db707cc52bac95baf17f0` | https://github.com/pydantic/pydantic |
| radare2 | LGPL-3.0-only | generic | 120 | `7987c26b937987404dfd72bfc3c7592abd5fd776` | https://github.com/radareorg/radare2 |
| requests | Apache-2.0 | python | 36 | `611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60` | https://github.com/psf/requests |

合计 13 个仓库、1230 个源文件。许可证按仓库根目录许可文件检出（html5ever 为 Apache-2.0/MIT 双许可，按检出值记录）。

> 复现：`PYTHONPATH=src python scripts/expand_corpus_github.py` 会读取 `src/codeguard/data/github_pins.json` 并锁定到上述提交；首次运行记录提交，重跑不再随上游 HEAD 漂移。
