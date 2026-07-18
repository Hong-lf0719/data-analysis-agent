# -*- coding: utf-8 -*-
"""
报告生成工具

负责：整合分析结果 → 生成 Markdown 报告 → 保存文件
"""
import json
from datetime import datetime


def generate_report(analysis_log: list[dict], data_summary: str = "",
                    output_path: str = "analysis_report.md",
                    cleaned_overview: dict = None,
                    quality: dict = None) -> dict:
    """
    基于分析日志生成结构化报告。

    支持两种 analysis_log 格式：
    1. agent.py 格式：{"step": "load", "summary": "...", "result": {...}}
    2. 旧格式：{"step": "load", "result": {...}}

    cleaned_overview: 可选，{"shape":[r,c], "columns":[...]} —— 优先用于"数据概况"，
    展示清洗后真正被分析的数据（而非原始 76 列含大量 Unnamed 的脏数据）。
    quality: 可选，tools.quality.quality_score 的返回值 {"score":float, "dimensions":{...}}，
    用于"数据质量评分"章节。
    """
    sections = [
        f"# 数据分析报告\n\n> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
    ]

    # ── 0. 数据质量评分（亮点） ──
    if quality and isinstance(quality, dict) and quality.get("score") is not None:
        score = quality["score"]
        dims = quality.get("dimensions", {})
        badge = "🟢 良好" if score >= 80 else "🟡 一般" if score >= 60 else "🔴 偏差"
        sections.append("## 0. 数据质量评分\n")
        sections.append(f"**综合得分：{score} / 100**  {badge}\n")
        if dims:
            sections.append("| 维度 | 得分 |")
            sections.append("|------|------|")
            for k, v in dims.items():
                sections.append(f"| {k} | {v} |")
            sections.append("")

    # ── 1. 数据概况 ──
    load_entries = [r for r in analysis_log if r.get("step") == "load"]
    overview = cleaned_overview
    if not overview and load_entries:
        overview = load_entries[-1].get("result", {})
    if overview:
        sections.append("## 1. 数据概况\n")
        if overview.get("shape"):
            tag = "（已清洗）" if cleaned_overview else ""
            sections.append(f"- 数据形状：{overview['shape'][0]} 行 × {overview['shape'][1]} 列{tag}")
        if overview.get("columns"):
            sections.append(f"- 字段：{', '.join(overview['columns'])}")
        if overview.get("encoding"):
            sections.append(f"- 编码：{overview['encoding']}")
        if load_entries[-1].get("summary"):
            sections.append(f"- 摘要：{load_entries[-1]['summary']}")
        sections.append("")

    # ── 2. 数据清洗 ──
    clean_entries = [r for r in analysis_log if r.get("step") == "clean"]
    if clean_entries:
        r = clean_entries[-1].get("result", {})
        sections.append("## 2. 数据清洗\n")

        # agent.py 新格式
        if r.get("problem_count") is not None:
            sections.append(f"- 发现问题数：{r['problem_count']}")
        if r.get("warning"):
            sections.append(f"\n> ⚠️ **数据质量警告**：{r['warning']}")
        if r.get("actions_taken"):
            sections.append("\n### 清洗操作\n")
            for action in r["actions_taken"]:
                sections.append(f"- {action}")

        # 旧格式兼容
        issues = r.get("issues", {}).get("problems", [])
        if issues:
            sections.append("\n### 发现的问题\n")
            for issue in issues:
                sections.append(f"- [{issue.get('severity', '?')}] {issue.get('detail', str(issue))}")
        log = r.get("log", [])
        if log:
            sections.append("\n### 清洗操作\n")
            for entry in log:
                sections.append(f"- {entry}")

        if clean_entries[-1].get("summary"):
            sections.append(f"\n> {clean_entries[-1]['summary']}")
        sections.append("")

    # ── 3. 统计分析 ──
    stats_entries = [r for r in analysis_log if r.get("step") == "stats"]
    if stats_entries:
        r = stats_entries[-1].get("result", {})
        sections.append("## 3. 统计分析\n")

        # agent.py 新格式：tests 列表
        tests = r.get("tests", [])
        if tests:
            sections.append("\n| 维度 | 组别 | 方法 | p 值 | 结论 |")
            sections.append("|------|------|------|------|------|")
            for t in tests:
                groups = " vs ".join(t.get("groups", ["?", "?"]))
                p_str = f"{t.get('p_value', 0):.4f}"
                sig = "✅ 显著" if t.get("significant") else "— 不显著"
                sections.append(
                    f"| {t.get('dimension', '?')} | {groups} | "
                    f"{t.get('test', '?')} | {p_str} | {sig} |"
                )
            sections.append("")

        # 旧格式兼容
        if not tests:
            if r.get("test_used"):
                sections.append(f"- 方法：{r['test_used']}")
                sections.append(f"- 统计量：{r.get('statistic', 'N/A')}")
                sections.append(f"- p 值：{r.get('p_value', 'N/A')}")
                sections.append(f"- 结论：{r.get('interpretation', 'N/A')}")
                if r.get("effect_size"):
                    es = r["effect_size"]
                    sections.append(f"- 效应量：{es['method']} = {es['value']}")
                sections.append("")

    # ── 3.5 相关性分析（亮点） ──
    corr_top = []
    for e in stats_entries:
        corr_top = (e.get("result", {}) or {}).get("correlations", {}).get("top", []) or []
        if corr_top:
            break
    if corr_top:
        sections.append("## 3.5 相关性分析\n")
        sections.append("> 数值变量间 Pearson 相关系数（|r| ≥ 0.3 的强相关对）\n")
        sections.append("| 变量 A | 变量 B | 相关系数 r | 强度 |")
        sections.append("|--------|--------|-----------|------|")
        for c in corr_top:
            r = c.get("r", 0)
            strength = "强" if abs(r) >= 0.7 else "中等" if abs(r) >= 0.5 else "弱"
            arrow = "↑ 正相关" if r > 0 else "↓ 负相关"
            sections.append(f"| {c.get('a','?')} | {c.get('b','?')} | {r} | {strength}（{arrow}） |")
        sections.append("")

    # ── 4. 可视化 ──
    viz_entries = [r for r in analysis_log if r.get("step") == "viz"]
    chart_list = []  # 收集所有图表的绝对路径，供导出器使用
    if viz_entries:
        r = viz_entries[-1].get("result", {})
        sections.append("## 4. 可视化\n")

        # agent.py 新格式：charts 列表
        charts = r.get("charts", [])
        for chart in charts:
            if chart.get("ok") and chart.get("file"):
                abs_path = chart["file"]
                chart_list.append(abs_path)
                # 报告里用相对路径引用（outputs/xxx.png），便于打包分发
                import os
                try:
                    rel = os.path.relpath(abs_path, os.path.dirname(output_path))
                    rel = rel.replace("\\", "/")
                except Exception:
                    rel = os.path.basename(abs_path)
                ctype = chart.get("chart_type", "图表")
                sections.append(f"![{ctype}]({rel})")
                sections.append(f"*{ctype} 图*\n")

        # 旧格式兼容
        if not charts and r.get("file"):
            sections.append(f"![{r.get('chart_type', '图表')}]({r['file']})\n")
            chart_list.append(r["file"])

        if viz_entries[-1].get("summary"):
            sections.append(f"> {viz_entries[-1]['summary']}\n")
        sections.append("")

    # ── 5. 分析过程总览 ──
    sections.append("## 5. 分析过程\n")
    sections.append("| 步骤 | 操作 | 说明 |")
    sections.append("|------|------|------|")
    for entry in analysis_log:
        step_name = entry.get("step", "?")
        step_num = entry.get("step_num", "?")
        summary = entry.get("summary", "")[:60]
        emoji = {"load": "📂", "clean": "🧹", "stats": "🔬", "viz": "📈", "report": "📝", "analyze": "🧠"}.get(step_name, "→")
        sections.append(f"| {step_num} | {emoji} {step_name} | {summary} |")
    sections.append("")

    report = "\n".join(sections)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    # 返回完整报告文本（供 report_node 拼接业务洞察，不再只给前 500 字预览）
    # chart_list：所有图表的绝对路径，供 HTML/PDF/DOCX 导出时内嵌
    return {"ok": True, "file": output_path, "report": report, "preview": report[:500],
            "charts": chart_list}
