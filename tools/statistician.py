# -*- coding: utf-8 -*-
"""
统计分析工具

负责：检查假设 → 选择检验方法 → 执行检验 → 输出结论
"""
import numpy as np
from scipy import stats
from typing import Optional


def check_assumptions(data: np.ndarray, test_type: str = "auto") -> dict:
    """
    检查假设检验的前置条件。

    返回：
    {
        "normality": {"statistic": float, "p_value": float, "is_normal": bool},
        "sample_size": int,
        "recommendation": "t_test" | "mann_whitney" | "wilcoxon" | "anova" | "kruskal" | "insufficient"
    }
    """
    n = len(data)
    result = {"sample_size": n}

    if n < 3:
        result["recommendation"] = "insufficient"
        result["detail"] = "样本量不足，无法做统计检验"
        return result

    # 正态性检验（Shapiro-Wilk，n ≤ 5000）
    if 3 <= n <= 5000:
        stat, p = stats.shapiro(data)
        result["normality"] = {
            "statistic": round(float(stat), 4),
            "p_value": round(float(p), 4),
            "is_normal": p > 0.05,
        }
    else:
        result["normality"] = {"note": "样本过大，跳过 Shapiro-Wilk"}

    return result


def run_test(data1: np.ndarray, data2: Optional[np.ndarray] = None,
             test_type: str = "auto", paired: bool = False) -> dict:
    """
    执行统计检验，自动选择合适的方法。

    test_type:
    - "auto": 自动选择
    - "ttest": 独立样本 t 检验
    - "paired_ttest": 配对 t 检验
    - "mann_whitney": Mann-Whitney U 检验
    - "wilcoxon": Wilcoxon 符号秩检验
    - "anova": 单因素方差分析（data2 为分组列表时）
    - "chi2": 卡方检验

    返回：{"test_used": str, "statistic": float, "p_value": float, "significant": bool, "effect_size": dict}
    """
    result = {}

    # 自动选择
    if test_type == "auto":
        if data2 is None:
            # 单样本 vs 假设值
            test_type = "ttest_1sample"
        elif paired:
            test_type = "paired_ttest"
        else:
            # 检查正态性
            n1 = check_assumptions(data1)
            n2 = check_assumptions(data2)
            both_normal = n1.get("normality", {}).get("is_normal", False) and \
                          n2.get("normality", {}).get("is_normal", False)

            if both_normal:
                test_type = "ttest"
            else:
                test_type = "mann_whitney"

    try:
        if test_type == "ttest":
            stat, p = stats.ttest_ind(data1, data2)
            result["test_used"] = "独立样本t检验"
            # Cohen's d
            d = (np.mean(data1) - np.mean(data2)) / np.sqrt((np.var(data1) + np.var(data2)) / 2)
            result["effect_size"] = {"method": "Cohen's d", "value": round(float(d), 3)}

        elif test_type == "paired_ttest":
            stat, p = stats.ttest_rel(data1, data2)
            result["test_used"] = "配对t检验"

        elif test_type == "mann_whitney":
            stat, p = stats.mannwhitneyu(data1, data2, alternative="two-sided")
            result["test_used"] = "Mann-Whitney U检验"
            # 秩双列相关
            n1, n2 = len(data1), len(data2)
            r = 1 - (2 * stat) / (n1 * n2)
            result["effect_size"] = {"method": "秩双列相关 r", "value": round(float(r), 3)}

        elif test_type == "wilcoxon":
            stat, p = stats.wilcoxon(data1, data2)
            result["test_used"] = "Wilcoxon符号秩检验"

        elif test_type == "ttest_1sample":
            stat, p = stats.ttest_1samp(data1, 0)
            result["test_used"] = "单样本t检验"

        else:
            return {"error": f"不支持的检验类型: {test_type}"}

        result["statistic"] = round(float(stat), 4)
        result["p_value"] = round(float(p), 6)
        result["significant"] = p < 0.05
        if p < 0.05:
            stars = '*' * min(3, max(1, int(-np.log10(max(p, 1e-10)))))
            result["interpretation"] = f"存在显著差异（{stars}），p = {p:.4f}"
        else:
            result["interpretation"] = f"无显著差异（p = {p:.4f}，未达 0.05 显著性水平）"

        return result

    except Exception as e:
        return {"error": str(e)}
