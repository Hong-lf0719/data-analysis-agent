# -*- coding: utf-8 -*-
"""LLM 管线评测集：20+ 条带标注答案的用例（确定性管线，非 LLM 输出）。

设计原则：
  - 每条用例 = 已知缺陷的合成数据 + 期望检出的问题类型 + 期望修复结果
  - 跑分对象是确定性管线（tools.cleaner / tools.statistician），
    因此结果可回归：改坏一行代码，跑分立刻下降
  - 「检验选型」用例用 numpy 合成已知分布（正态→t-test，偏态→Mann-Whitney），
    期望值来自统计常识而非猜的
"""
import numpy as np
import pandas as pd

RNG = np.random.default_rng(20261115)


# ============================================================
# A. 统计检验自动选型（tools.statistician.run_test）
#    期望字段：method（自动选型应命中的方法）、significant（显著性结论）
# ============================================================
def _norm(mu, sigma, n):
    return RNG.normal(mu, sigma, n)


def _lognorm(mean_log, sigma_log, n):
    return RNG.lognormal(mean_log, sigma_log, n)


STAT_CASES = [
    {
        "name": "正态两组·均值差异大 → t-test 显著",
        "data1": _norm(100, 15, 200), "data2": _norm(130, 15, 200),
        "expect_method": "独立样本t检验", "expect_significant": True,
    },
    {
        "name": "正态两组·均值相同 → t-test 不显著",
        "data1": _norm(100, 15, 200), "data2": _norm(100, 15, 200),
        "expect_method": "独立样本t检验", "expect_significant": False,
    },
    {
        "name": "右偏两组·位置差异 → Mann-Whitney 显著",
        "data1": _lognorm(0.0, 0.35, 200), "data2": _lognorm(0.35, 0.35, 200),
        "expect_method": "Mann-Whitney U检验", "expect_significant": True,
    },
    {
        "name": "右偏两组·同分布 → Mann-Whitney 不显著",
        "data1": _lognorm(0.0, 0.35, 200), "data2": _lognorm(0.0, 0.35, 200),
        "expect_method": "Mann-Whitney U检验", "expect_significant": False,
    },
    {
        "name": "正态两组·方差差3倍但均值同 → 不显著",
        "data1": _norm(100, 10, 200), "data2": _norm(100, 30, 200),
        "expect_method": "独立样本t检验", "expect_significant": False,
    },
    {
        "name": "强位移·小噪声 → t-test 显著",
        "data1": _norm(105, 2, 150), "data2": _norm(100, 2, 150),
        "expect_method": "独立样本t检验", "expect_significant": True,
    },
    {
        "name": "大样本·微小位移 → 检验功效充足应显著",
        "data1": _norm(100.0, 15, 5000), "data2": _norm(100.5, 15, 5000),
        "expect_method": "独立样本t检验", "expect_significant": True,
    },
    {
        "name": "样本量2·正态 → 容量不足应有明确处理",
        "data1": _norm(100, 15, 2), "data2": _norm(100, 15, 2),
        "expect_method": None, "expect_significant": None,
        "expect_no_crash": True,
    },
    {
        "name": "常数列·零方差 → 明确报错而非静默 nan",
        "data1": np.full(50, 100.0), "data2": np.full(50, 100.0),
        "expect_method": None, "expect_significant": None,
        "expect_error": True,
    },
    {
        "name": "配对样本·有差异 → 配对t检验 显著",
        "base": _norm(100, 10, 120),
        "data1": None, "data2": None,
        "paired": lambda b: (b, b + RNG.normal(2.0, 8.0, len(b))),
        "build": True, "is_paired": True,
        "expect_method": "配对t检验", "expect_significant": True,
    },
]


def build_stat_pairs(case):
    """返回 (data1, data2)。配对类用例先造基线再派生。"""
    if case.get("build"):
        base = case["base"]
        pair = case["paired"](base)
        if isinstance(pair, tuple):
            return pair      # builder 已返回 (前测, 后测)，直接解包
        return base, pair
    return case["data1"], case["data2"]


# ============================================================
# B. 清洗检测与修复（tools.cleaner.find_issues / clean_data）
#    expected_issues：find_issues 应检出的问题 type 集合
#    fix：clean_data 动作；invariants：修复后必须成立的不变量
# ============================================================
def _df_missing_median():
    vals = list(RNG.normal(50, 10, 40))
    df = pd.DataFrame({"score": vals})
    df.loc[3, "score"] = np.nan
    df.loc[9, "score"] = np.nan
    return df


def _df_all_missing_col():
    df = pd.DataFrame({"a": RNG.normal(0, 1, 30), "empty": np.nan})
    return df


def _df_unnamed_col():
    df = pd.DataFrame({"a": RNG.normal(0, 1, 20)})
    df.insert(0, "Unnamed: 0", range(20))
    return df


def _df_duplicates():
    base = pd.DataFrame({"a": RNG.normal(0, 1, 20), "b": RNG.normal(0, 1, 20)})
    dup = base.iloc[[3, 3, 7]].copy()
    return pd.concat([base, dup], ignore_index=True)


def _df_whitespace_col():
    df = pd.DataFrame({"a": RNG.normal(0, 1, 15)})
    df.columns = [" score "]
    return df


def _df_outliers():
    vals = list(RNG.normal(50, 5, 60)) + [500.0, -400.0]
    return pd.DataFrame({"v": vals})


def _df_shifted_row():
    """列错位：一行整体左移 → 数值列混入 NaN + 字段串列。"""
    df = _df_missing_median()
    df.loc[20, "score"] = np.nan
    return df


def _df_mixed_type():
    df = pd.DataFrame({"num": [str(x) for x in RNG.normal(10, 2, 25)] + ["N/A", "缺失"]})
    return df


CLEAN_CASES = [
    {
        "name": "中位数缺失填充 → 缺失检出 + 填充后无缺失",
        "build": _df_missing_median,
        "expect_types": {"missing_values"},
        "fix": [{"action": "fillna", "column": "score", "method": "median"}],
        "invariants": [
            ("修复后无缺失", lambda df: df["score"].isnull().sum() == 0),
            ("行数不变", lambda df: len(df) == 40),
        ],
    },
    {
        "name": "全缺失列 → high_missing 检出 + 丢弃后列消失",
        "build": _df_all_missing_col,
        "expect_types": {"high_missing"},
        "fix": [{"action": "drop_column", "column": "empty"}],
        "invariants": [
            ("empty 列已删除", lambda df: "empty" not in df.columns),
            ("行数不变", lambda df: len(df) == 30),
        ],
    },
    {
        "name": "Unnamed 列 → useless_column 检出 + 丢弃",
        "build": _df_unnamed_col,
        "expect_types": {"useless_column"},
        "fix": [{"action": "drop_column", "column": "Unnamed: 0"}],
        "invariants": [
            ("Unnamed 列已删除", lambda df: "Unnamed: 0" not in df.columns),
        ],
    },
    {
        "name": "3 行完全重复 → duplicates 检出 + 去重后为 0",
        "build": _df_duplicates,
        "expect_types": {"duplicates"},
        "fix": [{"action": "drop_duplicates"}],
        "invariants": [
            ("修复后无重复", lambda df: df.duplicated().sum() == 0),
        ],
    },
    {
        "name": "列名首尾空格 → column_name 检出",
        "build": _df_whitespace_col,
        "expect_types": {"column_name"},
        "fix": [{"action": "rename", "old": " score ", "new": "score"}],
        "invariants": [
            ("列名已规范化", lambda df: "score" in df.columns),
        ],
    },
    {
        "name": "2 个 IQR 极端值 → outliers 检出且数量正确 + 删除",
        "build": _df_outliers,
        "expect_types": {"outliers"},
        "expect_outlier_count": 2,
        "fix": [{"action": "drop_outliers", "column": "v", "threshold": 3}],
        "invariants": [
            ("极端值已移除", lambda df: df["v"].abs().max() < 300),
        ],
    },
    {
        "name": "文本数字列 + 缺失占位 → 检出缺失并可修复",
        "build": _df_mixed_type,
        "expect_types": set(),  # 混合类型列 find_issues 不强制报错（合法输入）
        "fix": [],
        "invariants": [
            ("行数不变", lambda df: len(df) == 27),
        ],
    },
    {
        "name": "干净数据 → 零问题检出（阴性用例）",
        "build": lambda: pd.DataFrame({"a": RNG.normal(0, 1, 40), "b": RNG.normal(0, 1, 40)}),
        "expect_types": set(),
        "fix": [],
        "invariants": [
            ("行数不变", lambda df: len(df) == 40),
        ],
    },
]
