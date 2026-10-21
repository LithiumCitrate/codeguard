# 将 CodeGuard 接入现有流程

CodeGuard 的公开契约是退出码和 SARIF/JSON 输出，不要求替换现有 CI。推荐把
“扫描”和“阻断”分开：扫描负责生成证据，门禁负责决定构建是否失败。

## 1. GitHub Actions：PR diff 门禁 + Code Scanning

```yaml
name: codeguard
on: [pull_request]
permissions:
  contents: read
  security-events: write   # 上传 SARIF 所需
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e .
      - name: Build knowledge base
        run: |
          codeguard corpus --workers 4 --max-files 40
          codeguard index
      - name: Gate the added lines
        run: |
          git diff "origin/${{ github.base_ref }}...HEAD" > pr.diff
          codeguard gate --diff pr.diff --license Apache-2.0 --usage distribution \
            --sarif .codeguard/reports/pr.sarif
      - name: Upload SARIF
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: .codeguard/reports/pr.sarif
          category: codeguard
```

要点：

- `security-events: write` 是 GitHub Code Scanning 上传 SARIF 的权限；
- **私有仓库没有 Advanced Security 授权时上传会报 `Resource not accessible by integration`**，
  用 `if: always() && github.event.repository.private == false` 跳过即可，仓库转公开后自动生效；
- `if: always()` 保证门禁失败时也能上传证据；
- `gate` 的退出码是契约：`0` 通过，`1` 有阻断级发现，`2` 环境/用法错误；
- PR diff 的扫描目标是新增行，行号用于定位，完整上下文需看出处证书；
- 首次运行需要联网构建语料；可把 `.codeguard/` 作为 CI 缓存，但索引与语料必须一起缓存。

## 2. 全仓扫描并上传 Code Scanning

`scan` 接受多个路径，按**每个源文件**写一份报告（`<文件名词干>.{provenance.json,cdx.json,report.html,sarif}`），
所以全仓扫描要单独指定 `--out`，再把整个目录交给上传步骤：

```yaml
      - run: codeguard scan src/ --license Apache-2.0 --usage distribution \
               --format json,cdx,html,sarif --out .codeguard/reports/scan
      - uses: github/codeql-action/upload-sarif@v3
        if: always() && github.event.repository.private == false
        with: { sarif_file: .codeguard/reports/scan }
```

SARIF 里的 `artifactLocation.uri` 是相对仓库根的路径（如 `src/codeguard/cli.py`），
GitHub 直接按此定位告警行；单文件扫描时 `scan <file>` 只产出一份 `<file词干>.sarif`。

`scan` 的 SARIF 和人类可读 HTML、CycloneDX SBOM 同源，但用途不同：

| 输出 | 消费方 | 用途 |
|---|---|---|
| SARIF | GitHub Code Scanning / IDE | 代码行级告警与趋势 |
| `codeguard.provenance/v1` JSON | 自建平台 / 审计 | 逐片段证据、模型特征、索引指纹 |
| CycloneDX 1.6 | 供应链/SBOM 工具 | 把内联复制作为 occurrence 带入 SBOM |
| HTML | 人工复核 | 离线查看来源与义务，无外部资源 |

## 3. SARIF 规则与等级

| ruleId | 风险 | 等级 | 含义 |
|---|---|---|---|
| `CG001` | S4 | error | 阻断级许可冲突 |
| `CG002` | S3 | error | 需满足条件的冲突/升级义务 |
| `CG003` | S2 | warning | 证据不足阻断，需人工复核 |
| `CG004` | S0/S1 | note | 来源观察，当前使用方式不构成阻断 |

GitHub Code Scanning 只会把 error/warning 作为告警展示；note 仍保留在 SARIF 中，
便于审计“看见过但未阻断”的候选。规则 ID 是稳定的，升级算法时不要复用为不同含义。

## 4. pre-commit

仓库自带 `hooks/pre-commit`：

```bash
cp hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
codeguard corpus && codeguard index   # 首次
```

钩子只取暂存的 `*.py` 新增行，阻断时退出 1，并给出替换、改许可证或记录内部使用三种处置。
它依赖本地索引和语料；缺失时明确报错而不是静默放行。

## 5. 本地运行与集成边界

- `codeguard scan` 可扫描文件或目录；默认扩展名 `py`，可用 `--ext py,pyi` 调整；
- 运行期零第三方依赖，不需要 GPU/API Key；
- 索引不含源码原文，但精确验证需要本地语料可读；语料缺失时退出 2；
- 结果定位到“候选来源”，不是侵权认定；许可证结论需人工复核；
- SARIF 的 `artifactLocation.uri` 使用扫描目标路径；在容器或临时目录运行时，应让
  扫描目标相对于仓库根目录，Code Scanning 才能正确映射到代码行。

## 6. 复现与缓存建议

```bash
codeguard corpus --workers 4 --max-files 40
codeguard index
codeguard doctor
codeguard scan src/ --license Apache-2.0 --usage distribution --format sarif
```

CI 中缓存 `.codeguard/` 时，务必把 `corpus/`、`index.bin` 和 `model.json` 一起缓存；
只缓存索引会导致语料路径失效，扫描会以退出码 2 拒绝“看起来干净”的结论。
