# -*- coding: utf-8 -*-
"""
数据可视化工具

负责：选图类型 → 生成图表 → 保存文件
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# 设置中文字体
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ── 专用输出目录（绝对路径），避免工作目录漂移导致 app 读不到图 ──
# 项目根 = visualizer.py 所在目录的上一级
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUTS_DIR = os.path.join(_PROJECT_ROOT, "outputs")


def ensure_outputs_dir() -> str:
    """确保 outputs/ 目录存在，返回其绝对路径。"""
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    return OUTPUTS_DIR


def resolve_chart_path(filename: str) -> str:
    """把图表文件名解析为 outputs/ 下的绝对路径。
    已是绝对路径则原样返回。"""
    if os.path.isabs(filename):
        return filename
    return os.path.join(ensure_outputs_dir(), filename)


def suggest_chart(data_info: dict, question: str = "") -> dict:
    """
    根据数据特征和问题，建议最合适的图表类型。
    """
    suggestions = []

    # 只有一个数值列 → 分布图
    num_cols = [c for c, t in data_info.get("dtypes", {}).items()
                if "int" in t or "float" in t]
    cat_cols = [c for c, t in data_info.get("dtypes", {}).items()
                if "object" in t or "category" in t]

    if len(num_cols) >= 1 and len(cat_cols) >= 1:
        suggestions.append({
            "chart": "bar",
            "reason": f"比较 {cat_cols[0]} 各组 '{num_cols[0]}' 的差异",
            "x": cat_cols[0],
            "y": num_cols[0],
        })

    if len(num_cols) >= 2:
        suggestions.append({
            "chart": "scatter",
            "reason": f"探索 '{num_cols[0]}' 与 '{num_cols[1]}' 的关系",
            "x": num_cols[0],
            "y": num_cols[1],
        })

    if len(num_cols) >= 1:
        suggestions.append({
            "chart": "box",
            "reason": f"查看 '{num_cols[0]}' 的分布和异常值",
            "column": num_cols[0],
        })

    return {"suggestions": suggestions}


def create_chart(df: pd.DataFrame, chart_type: str, **kwargs) -> dict:
    """
    生成图表并保存。

    chart_type: "bar" | "scatter" | "box" | "line" | "pie" | "hist"
    """
    plt.figure(figsize=(10, 6))

    try:
        if chart_type == "bar":
            x, y = kwargs.get("x"), kwargs.get("y")
            data = df.groupby(x)[y].mean().sort_values()
            data.plot(kind="barh", color="#4e79a7")
            plt.xlabel(y)
            plt.title(f"{y} by {x}")

        elif chart_type == "scatter":
            x, y = kwargs.get("x"), kwargs.get("y")
            hue_col = kwargs.get("hue")
            if hue_col and hue_col in df.columns:
                for label, group in df.groupby(hue_col):
                    plt.scatter(group[x], group[y], label=str(label), alpha=0.7)
                plt.legend()
            else:
                plt.scatter(df[x], df[y], alpha=0.7)
            plt.xlabel(x)
            plt.ylabel(y)

        elif chart_type == "box":
            col, by = kwargs.get("column"), kwargs.get("by")
            if by:
                df.boxplot(column=col, by=by)
            else:
                plt.boxplot(df[col].dropna())
                plt.xticks([1], [col])

        elif chart_type == "line":
            x, y = kwargs.get("x"), kwargs.get("y")
            for label, group in df.groupby(kwargs.get("hue")) if kwargs.get("hue") else [("", df)]:
                plt.plot(group[x], group[y], marker="o", label=label)
            plt.xlabel(x)
            plt.ylabel(y)
            if kwargs.get("hue"):
                plt.legend()

        elif chart_type == "hist":
            col = kwargs.get("column")
            plt.hist(df[col].dropna(), bins=20, color="#4e79a7", edgecolor="white")
            plt.xlabel(col)

        elif chart_type == "pie":
            col = kwargs.get("column")
            df[col].value_counts().plot(kind="pie", autopct="%1.1f%%")

        elif chart_type == "heatmap":
            numdf = df.select_dtypes(include=[np.number])
            if numdf.shape[1] >= 2:
                corr = numdf.corr(numeric_only=True)
                im = plt.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1, aspect="auto")
                plt.colorbar(im, fraction=0.046, pad=0.04)
                plt.xticks(range(len(corr.columns)), corr.columns, rotation=45, ha="right")
                plt.yticks(range(len(corr.columns)), corr.columns)
                plt.title("相关性热力图（Pearson）")
            else:
                raise ValueError("数值列不足 2 个，无法绘制热力图")

        elif chart_type == "count":
            col = kwargs.get("column")
            if col and col in df.columns:
                counts = df[col].value_counts().head(20)
                counts.sort_values().plot(kind="barh", color="#59a14f")
                plt.xlabel("频数")
                plt.title(f"{col} 取值分布（Top {len(counts)}）")
            else:
                raise ValueError("未指定有效的分类列")

        filename = kwargs.get("filename", f"chart_{chart_type}.png")
        # 解析到 outputs/ 绝对路径，避免工作目录漂移导致后续读取失败
        abs_path = resolve_chart_path(filename)
        plt.tight_layout()
        plt.savefig(abs_path, dpi=150)
        plt.close()

        # 返回的 file 为绝对路径；同时给一个 basename 便于报告里做相对引用
        return {"ok": True, "file": abs_path, "name": os.path.basename(abs_path),
                "chart_type": chart_type}

    except Exception as e:
        plt.close()
        return {"ok": False, "error": str(e)}
