# -*- coding: utf-8 -*-
"""生成 README 首屏用的真实演示产物（可复现，非占位图）。

用法（项目根目录）：python scripts/generate_demo.py

产出：
  docs/真实运行报告.md            — 端到端跑 examples/sample_sales.csv 的完整报告
  docs/screenshots/chart_*.png    — 同一次运行真实生成的图表
  docs/screenshots/报告预览.html   — 图片内嵌的自包含 HTML 报告
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import analyze                    # noqa: E402
from tools.exporter import export_report     # noqa: E402

SAMPLE = ROOT / "examples" / "sample_sales.csv"
DOCS = ROOT / "docs"
SHOTS = DOCS / "screenshots"


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)

    result = analyze(str(SAMPLE))
    report = result.get("final_report", "")
    if not report:
        raise SystemExit("分析未产出报告，终止")

    (DOCS / "真实运行报告.md").write_text(report, encoding="utf-8")

    chart_files = [Path(p) for p in result.get("chart_files", []) if p]
    if not chart_files:
        chart_files = sorted((ROOT / "outputs").glob("chart_*.png"))

    copied = []
    for src in chart_files:
        if src.exists():
            shutil.copy2(src, SHOTS / src.name)
            copied.append(src.name)

    try:
        export_report(report, str(SHOTS / "报告预览.html"), "html",
                      [str(p) for p in chart_files])
    except Exception as exc:  # pragma: no cover - 展示产物不阻断主流程
        print(f"[warn] HTML 预览生成失败: {exc}")

    print(f"报告: {len(report)} 字符 -> docs/真实运行报告.md")
    print(f"图表: {copied}")
    print("HTML: docs/screenshots/报告预览.html")


if __name__ == "__main__":
    main()
