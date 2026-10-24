"""Package a zero-install annotation kit for teammates without a technical background.

The kit is a single-file browser app plus the trial forms.  It embeds the
LiCoEval answer/source pairs so the annotator only clicks A/B/C; the script
still performs all detection-side work (fetching, indexing, scanning, metrics,
highlighting, CSV export, agreement/kappa and report text).  It never fills a
human label: an automated label would make the "double independent annotation"
claim false.

Usage:
    python scripts/make_annotation_kit.py
    python scripts/make_annotation_kit.py --out scratch/annotation-kit --zip scratch/CodeGuard-annotation-kit.zip
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
TOOLS = ROOT / "tools" / "annotation-kit"
PACKET_SCRIPT = ROOT / "scripts" / "make_annotation_packet.py"
DATASET_LICENSE = ROOT / ".codeguard" / "external" / "licoeval" / "LICENSE"
DEFAULT_OUT = WORKSPACE / "scratch" / "annotation-kit"
DEFAULT_ZIP = WORKSPACE / "scratch" / "CodeGuard-annotation-kit.zip"

TRIAL_FILES = {
    "submission/12-用户试用反馈表-试用者1.md": "trial/trial-form-1.md",
    "submission/12-用户试用反馈表-试用者2.md": "trial/trial-form-2.md",
    "submission/12-用户试用执行说明.md": "trial/trial-guide.md",
    "submission/12-用户试用反馈汇总.md": "trial/trial-summary-template.md",
}
CSV_FILES = {
    "submission/evidence/model-leak-20261021-标注表-标注人1.csv": "csv/model-leak-20261021-标注表-标注人1.csv",
    "submission/evidence/model-leak-20261021-标注表-标注人2.csv": "csv/model-leak-20261021-标注表-标注人2.csv",
}


def load_packet_module():
    spec = importlib.util.spec_from_file_location("make_annotation_packet", PACKET_SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit("无法加载 %s" % PACKET_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_samples(packet) -> list:
    evidence = packet.load_json(packet.EVIDENCE)
    records = packet.load_json(packet.DATASET)
    rows = packet.rows_from_evidence(evidence, records)
    samples = []
    for row in rows:
        answer_blocks, source_blocks = packet.matching_blocks(row["_answer"], row["_source"])
        samples.append({
            "sample_id": row["sample_id"],
            "expected_project": row["expected_project"],
            "expected_license": row["expected_license"],
            "paper_bleu": row["paper_bleu"],
            "paper_jaccard": row["paper_jaccard"],
            "paper_label": row["paper_label"],
            "codeguard_max_risk": row["codeguard_max_risk"],
            "codeguard_verbatim": row["codeguard_verbatim"],
            "codeguard_coverage": row["codeguard_coverage"],
            "codeguard_attributed": row["codeguard_attributed"],
            "codeguard_matched_packages": row["codeguard_matched_packages"],
            "answer": row["_answer"],
            "source": row["_source"],
            "answer_blocks": answer_blocks,
            "source_blocks": source_blocks,
            "findings": [
                {
                    "package": item.get("package"),
                    "path": item.get("path"),
                    "license": item.get("license"),
                    "risk": item.get("risk"),
                    "confidence": round(float(item.get("confidence") or 0.0), 4),
                    "verbatim_run": item.get("verbatim_run"),
                }
                for item in row["_findings"]
            ],
        })
    return samples


def render_app(samples: list) -> str:
    template = (TOOLS / "app.html").read_text(encoding="utf-8")
    payload = {
        "schema": "codeguard.annotation-kit/v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "dataset": "LiCoEval real regurgitation cases (gpt-4o), ICSE 2025, AGPL-3.0-or-later",
            "evidence": "submission/evidence/model-leak-20261021.json",
            "privacy": "third-party source is embedded for local team annotation only",
        },
        "samples": samples,
    }
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    if "__DATA__" not in template:
        raise SystemExit("模板缺少 __DATA__ 占位符")
    return template.replace("__DATA__", blob)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_static(out: Path) -> None:
    for name in ("start.bat", "README.txt", "TUTORIAL.md"):
        shutil.copy2(TOOLS / name, out / name)
    for src, dest in TRIAL_FILES.items():
        source = ROOT / src
        if not source.exists():
            raise SystemExit("缺少试用材料: %s" % source)
        write_file(out / dest, source.read_text(encoding="utf-8"))
    for src, dest in CSV_FILES.items():
        source = ROOT / src
        if not source.exists():
            raise SystemExit("缺少 CSV 模板: %s\n先运行 python scripts/make_annotation_packet.py" % source)
        write_file(out / dest, source.read_text(encoding="utf-8"))
    if DATASET_LICENSE.exists():
        write_file(out / "LICENSE-LiCoEval.txt", DATASET_LICENSE.read_text(encoding="utf-8"))
    else:
        write_file(out / "LICENSE-LiCoEval.txt",
                   "LiCoEval is licensed under AGPL-3.0-or-later.\n"
                   "Source: https://github.com/osslab-pku/LiCoEval\n")


def clean_dir(path: Path) -> None:
    """Clear the kit directory without deleting the directory itself.

    Windows keeps a directory busy if another process (shell cwd, Explorer,
    an editor, or a browser preview) holds it, so only the contents are
    replaced.
    """
    path.mkdir(parents=True, exist_ok=True)
    for child in sorted(path.iterdir()):
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        except PermissionError as exc:
            raise SystemExit(
                "无法清理 %s：%s\n请关闭占用该目录的程序（终端当前目录、资源管理器、浏览器预览）后重试。" % (child, exc)
            )


def make_zip(out: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        try:
            zip_path.unlink()
        except PermissionError as exc:
            raise SystemExit("无法覆盖 %s：%s\n请关闭正在预览 zip 的程序后重试。" % (zip_path, exc))
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(out.parent).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    args = parser.parse_args()

    packet = load_packet_module()
    if not packet.EVIDENCE.exists():
        raise SystemExit("缺少 %s" % packet.EVIDENCE)
    if not packet.DATASET.exists():
        raise SystemExit("缺少 LiCoEval 缓存。先运行 python scripts/eval_model_leak.py")

    samples = build_samples(packet)
    if len(samples) != 47:
        raise SystemExit("应为 47 条样本，实际 %d 条" % len(samples))

    out = args.out
    clean_dir(out)
    write_file(out / "annotate.html", render_app(samples))
    copy_static(out)
    make_zip(out, args.zip)

    html_size = (out / "annotate.html").stat().st_size
    zip_size = args.zip.stat().st_size
    print("生成完成")
    print("  目录: %s" % out)
    print("  压缩包: %s" % args.zip)
    print("  annotate.html: %.1f KB" % (html_size / 1024))
    print("  zip: %.1f KB" % (zip_size / 1024))
    print("  样本: 47 条")
    print("把压缩包发给两位队友；他们只需要打开 annotate.html 点 A/B/C 并导出 CSV。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
