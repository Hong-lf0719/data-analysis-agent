# -*- coding: utf-8 -*-
"""复现 README 性能表（可重复、离线、不烧 token）。

口径说明：
  - 数据为固定随机种子合成的表格，**不是真实业务数据**；
  - LLM 被打桩为不可用，走项目自带的确定性降级路径，
    测的是「加载 → 清洗 → 统计 → 可视化 → 报告」的墙钟时间，
    **不含 LLM 网络调用**（含 LLM 的端到端耗时取决于网络，不可复现）；
  - 每个规模跑两次取较快一次，降低冷启动影响。

用法（项目根目录）：python scripts/benchmark.py
产出：docs/benchmark.md + stdout 表格
"""
from __future__ import annotations

import contextlib
import io
import platform
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402


class OfflineLLM:
    """让所有 LLM 节点走确定性降级，不联网、不花 token。"""

    def invoke(self, *args, **kwargs):
        raise RuntimeError("benchmark: LLM disabled")


SIZES = (634, 5000, 12003)
SEED = 20261113


def make_df(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    qty = rng.integers(1, 200, n)
    unit = rng.uniform(20, 500, n)
    return pd.DataFrame({
        "日期": pd.date_range("2026-01-01", periods=n, freq="h").astype(str),
        "地区": rng.choice(["华东", "华北", "华南", "华中"], n),
        "产品类别": rng.choice(["家居用品", "电子产品", "服饰", "食品"], n),
        "销量": qty,
        "销售额": np.round(qty * unit, 2),
        "利润率": np.round(rng.uniform(0.20, 0.50, n), 4),
    })


def run_once(csv_path: str) -> tuple[float, int, int]:
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        t0 = time.perf_counter()
        result = agent.analyze(csv_path)
        elapsed = time.perf_counter() - t0
    return (elapsed,
            len(result.get("final_report", "") or ""),
            len(result.get("chart_files", []) or []))


def main() -> None:
    agent._llm_cache = OfflineLLM()

    rows = []
    with tempfile.TemporaryDirectory(prefix="daa_bench_") as tmp:
        for n in SIZES:
            path = str(Path(tmp) / f"bench_{n}.csv")
            make_df(n).to_csv(path, index=False, encoding="utf-8")
            trials = [run_once(path) for _ in range(2)]
            best = min(trials, key=lambda r: r[0])
            rows.append((n, best[0], best[1], best[2]))
            print(f"{n:>6} 行  {best[0]:>6.2f}s  报告 {best[1]} 字符  图表 {best[2]} 张")

    lines = [
        "# 性能基准",
        "",
        f"> 由 `python scripts/benchmark.py` 生成于 {date.today().isoformat()}，可重复执行。",
        "",
        "## 口径（先说清楚，避免数字被误读）",
        "",
        "- 数据：固定随机种子 `20261113` **合成**的表格，不是真实业务数据；",
        "- LLM：打桩为不可用，走项目自带的确定性降级路径，**不含 LLM 网络调用**；",
        "- 计时：`agent.analyze()` 从加载到完整报告产出的墙钟时间，每档跑两次取较快一次；",
        f"- 环境：{platform.system()} / Python {platform.python_version()} / "
        f"pandas {pd.__version__} / numpy {np.__version__}。",
        "",
        "| 数据行数 | 确定性管线耗时 | 报告长度 | 图表数 |",
        "|---:|---:|---:|---:|",
    ]
    for n, sec, chars, charts in rows:
        lines.append(f"| {n:,} | {sec:.2f} s | {chars:,} 字符 | {charts} |")
    lines += [
        "",
        "> 简历中所写「端到端 12–21 秒（实测 634~12003 行）」是**含 LLM 生成**的历史实测，",
        "> 受网络与模型响应影响；上表是可复现的确定性部分，两者口径不同，请勿直接对比。",
        "",
    ]
    out = ROOT / "docs" / "benchmark.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
