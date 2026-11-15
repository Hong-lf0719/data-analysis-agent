# -*- coding: utf-8 -*-
"""评测集 pytest 回归包装：让 CI 也跑确定性管线评测。

与 evals/run_eval.py 共用同一套用例与判分逻辑——
跑分不达标即测试失败，防止管线回归静默通过。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.eval_cases import CLEAN_CASES, STAT_CASES
from evals.run_eval import eval_clean_case, eval_stat_case


def test_stat_selection_all_cases():
    for c in STAT_CASES:
        r = eval_stat_case(c)
        assert r["ok"], f"统计选型未达标: {r['case']} → {r.get('note', '')}"


def test_clean_detection_all_cases():
    for c in CLEAN_CASES:
        r = eval_clean_case(c)
        assert r["detection_ok"], f"缺陷漏检: {r['case']}（命中 {r['detection_hits']}/{r['detection_total']}）"


def test_clean_fix_all_cases():
    for c in CLEAN_CASES:
        r = eval_clean_case(c)
        assert r["fix_ok"], f"修复不变量不成立: {r['case']} → {r['failures']}"
