# -*- coding: utf-8 -*-
"""
数据质量评分工具

从三个维度给数据集打一个 0-100 的综合分：
  - 完整性（completeness）：单元格非空比例
  - 唯一性（uniqueness）：非重复行比例
  - 有效性（validity）：非"无用列"（Unnamed / 空列名）的比例

权重：完整性 40% + 唯一性 20% + 有效性 40%。
空数据集返回 0 分。
"""
import pandas as pd


def quality_score(df: "pd.DataFrame") -> dict:
    """
    返回 {"score": float(0-100), "dimensions": {"完整性":.., "唯一性":.., "有效性":..}}。

    score 为整数化前的四舍五入值；dimensions 各项为 0-100 的百分比。
    """
    n_rows = len(df)
    n_cols = df.shape[1]
    if n_rows == 0 or n_cols == 0:
        return {"score": 0.0, "dimensions": {"完整性": 0.0, "唯一性": 0.0, "有效性": 0.0}}

    # 完整性：所有单元格的非空占比
    completeness = 1.0 - float(df.isnull().mean().mean())

    # 唯一性：非重复行占比
    dup_rate = float(df.duplicated().mean())
    uniqueness = 1.0 - dup_rate

    # 有效性：非无用列占比（Unnamed / 空列名 视为无效）
    useless = sum(
        1 for c in df.columns if "Unnamed" in str(c) or str(c).strip() == ""
    ) / n_cols
    validity = 1.0 - useless

    score = (completeness * 0.4 + uniqueness * 0.2 + validity * 0.4) * 100.0
    score = max(0.0, min(100.0, score))

    return {
        "score": round(score, 1),
        "dimensions": {
            "完整性": round(completeness * 100, 1),
            "唯一性": round(uniqueness * 100, 1),
            "有效性": round(validity * 100, 1),
        },
    }


def quality_label(score: float) -> str:
    """把分数映射成可读等级。"""
    if score >= 80:
        return "良好"
    if score >= 60:
        return "一般"
    return "偏差"
