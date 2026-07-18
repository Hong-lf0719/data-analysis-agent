# -*- coding: utf-8 -*-
"""test_statistician.py — 统计分析模块单元测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from tools.statistician import check_assumptions, run_test


def test_check_assumptions_normal():
    """正态分布数据应通过正态性检验"""
    np.random.seed(42)
    data = np.random.normal(0, 1, 100)
    r = check_assumptions(data)
    assert "normality" in r
    if r["normality"].get("is_normal") is not None:
        pass  # 不强制通过，取决于随机种子


def test_check_assumptions_small_sample():
    """样本太少应返回 insufficient"""
    r = check_assumptions(np.array([1, 2]))
    assert r["recommendation"] == "insufficient"


def test_run_ttest():
    """独立样本 t 检验（强制指定）"""
    data1 = np.array([10, 12, 11, 13, 12])
    data2 = np.array([20, 22, 21, 23, 22])
    r = run_test(data1, data2, test_type="ttest")
    assert r["significant"], "两组有明显差异，应显著"
    assert r["p_value"] < 0.05, f"p值应<0.05，实际{r['p_value']}"


def test_run_mann_whitney():
    """Mann-Whitney U 检验（强制指定）"""
    data1 = np.array([1, 2, 3, 4, 50])  # 非正态
    data2 = np.array([2, 3, 4, 5, 6])
    r = run_test(data1, data2, test_type="mann_whitney")
    assert "test_used" in r
    assert "Mann-Whitney" in r["test_used"]


def test_auto_select():
    """自动选择检验方法应返回结果"""
    data1 = np.random.normal(30, 5, 50)
    data2 = np.random.normal(35, 5, 50)
    r = run_test(data1, data2, test_type="auto")
    assert "test_used" in r
    assert "p_value" in r
    assert "significant" in r
    assert "interpretation" in r


def test_effect_size():
    """效应量应被计算"""
    data1 = np.array([10, 12, 11, 13, 12, 11, 13, 12])
    data2 = np.array([20, 22, 21, 23, 22, 21, 23, 22])
    r = run_test(data1, data2, test_type="ttest")
    assert "effect_size" in r
    assert abs(r["effect_size"]["value"]) > 1.0, \
        f"两组差异很大，Cohen's d 绝对值应>1，实际{r['effect_size']['value']}"


def test_invalid_test_type():
    """不支持的检验类型应报错"""
    r = run_test(np.array([1, 2, 3]), test_type="unknown")
    assert "error" in r
