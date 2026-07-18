# -*- coding: utf-8 -*-
"""test_cleaner.py — 数据清洗模块单元测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import numpy as np
from tools.cleaner import find_issues, clean_data


def make_df(data: dict) -> pd.DataFrame:
    return pd.DataFrame(data)


def test_find_outliers_iqr():
    """极端异常值应被 IQR 方法检测到"""
    df = make_df({"a": [1, 2, 3, 4, 5, 100]})
    issues = find_issues(df)
    assert any(p["type"] == "outliers" for p in issues["problems"]), \
        "应检测到异常值"


def test_no_outliers_on_normal_data():
    """正常数据不应报告异常值"""
    df = make_df({"a": [10, 12, 11, 13, 12, 10]})
    issues = find_issues(df)
    outlier_count = sum(1 for p in issues["problems"] if p["type"] == "outliers")
    assert outlier_count == 0, f"正常数据不应有异常值，实际{outlier_count}个"


def test_find_missing_values():
    """缺失值应被检测"""
    df = make_df({"a": [1, np.nan, 3, np.nan, 5]})
    issues = find_issues(df)
    assert any(p["type"] == "missing_values" for p in issues["problems"]), \
        "应检测到缺失值"


def test_find_duplicates():
    """重复行应被检测"""
    df = make_df({"a": [1, 2, 2, 3], "b": [4, 5, 5, 6]})
    issues = find_issues(df)
    assert any(p["type"] == "duplicates" for p in issues["problems"]), \
        "应检测到重复行"


def test_clean_drop_outliers():
    """删除异常值后行数应减少"""
    df = make_df({"a": [1, 2, 3, 4, 5, 100]})
    r = clean_data(df, [{"action": "drop_outliers", "column": "a"}])
    assert r["remaining_rows"] < 6, "异常值行应被移除"


def test_clean_rename_column():
    """列重命名"""
    df = make_df({"old_name": [1, 2, 3]})
    r = clean_data(df, [{"action": "rename", "old": "old_name", "new": "new_name"}])
    # clean_data 改的是副本，不影响原始 df
    assert "new_name" in str(r["cleaned_summary"])


def test_clean_fillna_median():
    """缺失值填充"""
    df = make_df({"a": [1, np.nan, 3, np.nan, 5]})
    r = clean_data(df, [{"action": "fillna", "column": "a", "method": "median"}])
    assert r["remaining_rows"] == 5


def test_problem_count():
    """problem_count 应等于 problems 列表长度"""
    df = make_df({"a": [1, 2, np.nan, 4, 100], "b": ["x", "x", "y", "y", "y"]})
    issues = find_issues(df)
    assert issues["problem_count"] == len(issues["problems"]), \
        f"problem_count ({issues['problem_count']}) != len(problems) ({len(issues['problems'])})"
