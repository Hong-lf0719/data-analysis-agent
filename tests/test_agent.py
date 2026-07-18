# -*- coding: utf-8 -*-
"""test_agent.py — Agent 核心逻辑单元测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from agent import _filter_df, _safe, _get_df, _set_df


def test_safe_nan():
    """_safe() 应将 NaN 转为 None"""
    import numpy as np
    result = _safe({"a": np.float64(np.nan), "b": 1.0})
    assert result["a"] is None
    assert result["b"] == 1.0


def test_safe_inf():
    """_safe() 应将 Inf 转为 None"""
    import numpy as np
    result = _safe({"a": np.float64(np.inf), "b": np.float64(-np.inf)})
    assert result["a"] is None
    assert result["b"] is None


def test_safe_nested():
    """_safe() 应递归处理嵌套结构"""
    import numpy as np
    result = _safe([{"a": np.float64(3.14)}, np.int64(42)])
    assert result[0]["a"] == 3.14
    assert result[1] == 42


def test_filter_df_by_region():
    """_filter_df 应按地区筛选"""
    df = pd.DataFrame({
        "地区": ["华东", "华南", "华北", "华东"],
        "销售额": [100, 200, 300, 400],
    })
    result = _filter_df(df, "只看华东的数据")
    assert len(result) == 2
    assert all(result["地区"] == "华东")


def test_filter_df_by_product():
    """_filter_df 应按产品类别筛选"""
    df = pd.DataFrame({
        "产品类别": ["电子产品", "家居用品", "电子产品", "家电"],
        "销售额": [100, 200, 300, 400],
    })
    result = _filter_df(df, "电子产品的情况")
    assert len(result) == 2
    assert all(result["产品类别"] == "电子产品")


def test_filter_df_no_match():
    """_filter_df 无匹配时应返回原数据"""
    df = pd.DataFrame({
        "地区": ["华东", "华南"],
        "销售额": [100, 200],
    })
    result = _filter_df(df, "看看西北的数据")
    assert len(result) == 2  # 没有西北地区，返回全部


def test_set_and_get_df():
    """_set_df + _get_df 应完整往返"""
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    json_str = _set_df(df)
    restored = pd.read_json(__import__("io").StringIO(json_str), orient="split")
    assert restored.shape == df.shape
    assert list(restored.columns) == list(df.columns)
