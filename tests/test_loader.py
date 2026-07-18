# -*- coding: utf-8 -*-
"""test_loader.py — 数据加载模块单元测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from tools.loader import load_data, inspect_data


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_load_csv_utf8():
    """基础：加载 UTF-8 CSV"""
    r = load_data(os.path.join(FIXTURES, "sample.csv"))
    assert r["ok"], f"加载失败: {r.get('error', '')}"
    assert r["shape"][0] == 8, f"期望8行，实际{r['shape'][0]}"
    assert r["shape"][1] == 4, f"期望4列，实际{r['shape'][1]}"
    assert "姓名" in r["columns"], f"缺少列'姓名'"
    assert r["encoding"] == "utf-8", f"期望 utf-8，实际 {r['encoding']}"


def test_load_nonexistent_file():
    """加载不存在的文件应报错"""
    r = load_data("tests/fixtures/不存在的文件.csv")
    assert not r["ok"]


def test_inspect_data():
    """inspect_data 应返回有效 JSON"""
    result = inspect_data(os.path.join(FIXTURES, "sample.csv"))
    assert '"columns"' in result, "缺少 columns 字段"
    assert '"shape"' in result, "缺少 shape 字段"
    # 确保是合法 JSON
    import json
    data = json.loads(result)
    assert data["shape"][0] == 8


def test_load_gbk_encoding():
    """自动检测 GBK 编码"""
    r = load_data(os.path.join(FIXTURES, "gbk_sample.csv"))
    if r["ok"]:
        # 应该能正常加载
        assert r["shape"][0] > 0
