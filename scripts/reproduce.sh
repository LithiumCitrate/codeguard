#!/bin/sh
# Reproduce every number in the technical report from a clean checkout.
# Needs only CPython 3.9+ (no third-party package, no GPU, no API key).
#
#   sh scripts/reproduce.sh              # 全流程，约 4 分钟（语料下载取决于网络）
#   sh scripts/reproduce.sh --offline    # 跳过 corpus，复用已有 .codeguard/corpus
set -e

cd "$(dirname "$0")/.."
export PYTHONPATH=src
# Windows/git-bash often has `python` but no `python3`; pick whichever exists.
if [ -z "${PYTHON:-}" ]; then
    for candidate in python3 python py; do
        if command -v "$candidate" >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
    done
fi
: "${PYTHON:=python3}"
echo "使用解释器：$PYTHON"

if [ "$1" = "--offline" ]; then
    echo "== 离线模式：复用 .codeguard/corpus"
else
    echo "== 1/5 下载许可证多样的语料"
    $PYTHON -m codeguard corpus
fi

echo "== 2/5 构建指纹索引"
$PYTHON -m codeguard index

echo "== 3/5 变异基准 + 消融实验 + 训练判定模型"
$PYTHON -m codeguard benchmark --files 24

echo "== 4/5 测试套件"
$PYTHON -m pytest -q || $PYTHON -m unittest discover -s tests -v

echo "== 5/5 门禁自检（应当返回 1）"
set +e
$PYTHON scripts/demo_gate.py --package paramiko --mutation compound \
    --license LicenseRef-Proprietary >/dev/null
code=$?
set -e
if [ "$code" != "1" ]; then
    echo "预期门禁阻断（退出码 1），实际 $code"; exit 1
fi
echo "门禁按预期阻断了 copyleft 复用（退出码 1）"

echo
echo "结果文件：.codeguard/benchmark/benchmark.md（与仓库内 docs/BENCHMARK.md 对照）"
$PYTHON -m codeguard doctor
