# -*- coding: utf-8 -*-
"""
数据清洗工具

负责：诊断问题 → 处理缺失 → 检测异常 → 修正错误
"""
import pandas as pd
import numpy as np
import json
from typing import Optional


def find_issues(df: pd.DataFrame) -> dict:
    """
    诊断数据质量问题，返回结构化报告。
    """
    issues = {
        "total_rows": len(df),
        "total_cols": len(df.columns),
        "problems": [],
    }

    # 1. 列名检查
    for col in df.columns:
        # 检查首尾空格
        if col != col.strip():
            issues["problems"].append({
                "type": "column_name",
                "severity": "low",
                "column": col,
                "detail": f"列名 '{col}' 首尾有空格"
            })
        # 检查 Unnamed 列
        if "Unnamed" in str(col) or col.strip() == "":
            miss_rate = df[col].isnull().mean() if col in df.columns else 1.0
            issues["problems"].append({
                "type": "useless_column",
                "severity": "high",
                "column": col,
                "missing_rate": round(miss_rate * 100, 1),
                "detail": f"无用列 '{col}'（缺失率 {miss_rate*100:.0f}%），建议删除"
            })

    # 2. 高缺失率列（>50% 且未被 Unnamed 标记）
    for col, count in df.isnull().sum().items():
        if count > 0 and "Unnamed" not in str(col):
            pct = count / len(df) * 100
            sev = "high" if pct > 50 else "medium" if pct > 20 else "low"
            issues["problems"].append({
                "type": "high_missing" if pct > 50 else "missing_values",
                "severity": sev,
                "column": col,
                "count": int(count),
                "percentage": round(pct, 1),
                "detail": f"列 '{col}' 缺失 {pct:.0f}%（{count}/{len(df)}）"
            })

    # 3. 数值列异常检测（IQR 方法）
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        Q1 = df[col].quantile(0.25)
        Q3 = df[col].quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 3 * IQR  # 用 3 倍 IQR，只捕获极端异常
        upper = Q3 + 3 * IQR

        outliers = df[(df[col] < lower) | (df[col] > upper)]
        if len(outliers) > 0:
            issues["problems"].append({
                "type": "outliers",
                "severity": "high" if len(outliers) > len(df) * 0.1 else "medium",
                "column": col,
                "count": len(outliers),
                "values": outliers[col].tolist(),
                "bounds": {"lower": round(lower, 2), "upper": round(upper, 2)},
                "detail": f"列 '{col}' 发现 {len(outliers)} 个极端异常值（超出 [{lower:.0f}, {upper:.0f}]）"
            })

    # 4. 重复行
    dupes = df.duplicated().sum()
    if dupes > 0:
        issues["problems"].append({
            "type": "duplicates",
            "severity": "medium",
            "count": int(dupes),
            "detail": f"发现 {dupes} 行完全重复"
        })

    issues["problem_count"] = len(issues["problems"])
    return issues


def clean_data(df: pd.DataFrame, actions: list[dict]) -> dict:
    """
    根据清洗指令执行操作。

    actions 格式：
    [
        {"action": "rename", "old": "revnue", "new": "revenue"},
        {"action": "drop_outliers", "column": "revenue", "threshold": 3},
        {"action": "fillna", "column": "age", "method": "median"},
        {"action": "drop_duplicates"},
    ]
    """
    log = []
    df = df.copy()

    for act in actions:
        try:
            if act["action"] == "rename":
                df.rename(columns={act["old"]: act["new"]}, inplace=True)
                log.append(f"✓ 重命名: {act['old']} → {act['new']}")

            elif act["action"] == "drop_outliers":
                col = act["column"]
                threshold = act.get("threshold", 3)
                Q1, Q3 = df[col].quantile(0.25), df[col].quantile(0.75)
                IQR = Q3 - Q1
                before = len(df)
                df = df[(df[col] >= Q1 - threshold * IQR) & (df[col] <= Q3 + threshold * IQR)]
                dropped = before - len(df)
                log.append(f"✓ 删除异常值: {col} 列移除了 {dropped} 行")

            elif act["action"] == "fillna":
                col, method = act["column"], act.get("method", "median")
                before = df[col].isnull().sum()
                if method == "median":
                    df[col] = df[col].fillna(df[col].median())
                elif method == "mean":
                    df[col] = df[col].fillna(df[col].mean())
                elif method == "mode":
                    df[col] = df[col].fillna(df[col].mode()[0])
                elif "value" in act:
                    df[col] = df[col].fillna(act["value"])
                log.append(f"✓ 填充缺失: {col} 列填充了 {before} 个值（方法: {method}）")

            elif act["action"] == "drop_duplicates":
                before = len(df)
                df.drop_duplicates(inplace=True)
                log.append(f"✓ 删除重复行: 移除了 {before - len(df)} 行")

            elif act["action"] == "drop_column":
                df.drop(columns=[act["column"]], inplace=True)
                log.append(f"✓ 删除列: {act['column']}")

        except Exception as e:
            log.append(f"✗ 失败: {act['action']} - {str(e)}")

    return {
        "ok": True,
        "remaining_rows": len(df),
        "remaining_cols": len(df.columns),
        "log": log,
        "cleaned_summary": df.describe(include="all").to_dict(),
    }
