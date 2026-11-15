# -*- coding: utf-8 -*-
"""评测跑分器：确定性管线的 检测 / 修复 / 统计选型 三项准确率量化回归。

用法：
    python evals/run_eval.py          # Markdown 报告，全部达标退出码 0
    python evals/run_eval.py --json   # JSON 输出（CI 友好）

评分口径：
  - 检测准确率：find_issues 检出的 type 是否覆盖标注答案（用例：已知缺陷）
  - 修复准确率：clean_data 执行后不变量是否全部成立（行数/无缺失/无重复/列删除）
  - 选型正确率：run_test 自动选择的检验方法是否与合成分布的统计常识一致
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from evals.eval_cases import CLEAN_CASES, STAT_CASES, build_stat_pairs
from tools.cleaner import clean_data, find_issues
from tools.statistician import run_test


def eval_clean_case(case) -> dict:
    df = case["build"]()
    issues = find_issues(df)
    found = {i["type"] for i in issues["problems"]}
    expected = case["expect_types"]
    detected = expected & found

    fix_ok, failures = True, []
    r = clean_data(df, case["fix"])
    for label, check in case["invariants"]:
        try:
            passed = bool(check(r["df"]))
            err = ""
        except Exception as e:  # noqa: BLE001
            passed, err = False, str(e)
        if not passed:
            fix_ok = False
            failures.append(f"{label}（{err or '不变量不成立'}）")

    return {
        "case": case["name"],
        "detection_hits": len(detected),
        "detection_total": len(expected),
        "detection_ok": detected == expected,
        "fix_ok": fix_ok,
        "failures": failures,
        "problem_count": issues["problem_count"],
    }


def eval_stat_case(case) -> dict:
    d1, d2 = build_stat_pairs(case)
    is_paired = bool(case.get("is_paired"))
    try:
        r = run_test(d1, d2, paired=is_paired)
    except Exception as e:  # noqa: BLE001
        return {"case": case["name"], "method": None, "significant": None,
                "method_ok": False, "sig_ok": False, "ok": False,
                "note": f"异常: {e}"}
    err = r.get("error")
    if "expect_error" in case:
        ok = bool(err) == bool(case["expect_error"])
        return {"case": case["name"], "method": r.get("test_used"), "significant": None,
                "method_ok": ok, "sig_ok": ok, "ok": ok, "note": f"error={err}"}
    method = r.get("test_used")
    sig = bool(r.get("significant"))
    method_ok = (case.get("expect_method") is None) or (method == case["expect_method"])
    sig_ok = (case.get("expect_significant") is None) or (sig == case["expect_significant"])
    return {"case": case["name"], "method": method, "significant": sig,
            "method_ok": method_ok, "sig_ok": sig_ok,
            "ok": method_ok and sig_ok and not err, "note": ""}
    method_ok = method == case["expect_method"]
    sig_ok = sig == case["expect_significant"]
    return {"case": case["name"], "method": method, "significant": sig,
            "method_ok": method_ok, "sig_ok": sig_ok,
            "ok": method_ok and sig_ok, "note": ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    stat_results = [eval_stat_case(c) for c in STAT_CASES]
    clean_results = [eval_clean_case(c) for c in CLEAN_CASES]

    stat_ok = sum(1 for r in stat_results if r["ok"])
    det_hits = sum(r["detection_hits"] for r in clean_results)
    det_total = sum(r["detection_total"] for r in clean_results)
    fix_ok = sum(1 for r in clean_results if r["fix_ok"])
    clean_total = len(clean_results)

    report = {
        "stat_selection": {
            "passed": stat_ok, "total": len(stat_results),
            "rate": round(stat_ok / len(stat_results), 4),
            "cases": stat_results,
        },
        "clean_detection": {
            "hits": det_hits, "total": det_total,
            "rate": round(det_hits / det_total, 4),
        },
        "clean_fix": {"passed": fix_ok, "total": clean_total,
                      "rate": round(fix_ok / clean_total, 4),
                      "cases": clean_results},
        "all_passed": stat_ok == len(stat_results) and det_hits == det_total and fix_ok == clean_total,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"# 评测报告（确定性管线 · {len(stat_results) + clean_total} 用例）\n")
        print(f"## 统计检验自动选型：{stat_ok}/{len(stat_results)}\n")
        for r in stat_results:
            mark = "✅" if r["ok"] else "❌"
            print(f"- {mark} {r['case']} → 方法={r['method']} 显著={r['significant']}")
        print(f"\n## 清洗检测：命中 {det_hits}/{det_total} ｜ 修复：{fix_ok}/{clean_total}\n")
        for r in clean_results:
            mark = "✅" if r["detection_ok"] and r["fix_ok"] else "❌"
            miss = "" if r["detection_ok"] else f"（漏检 {r['detection_total'] - r['detection_hits']}）"
            fails = f"（修复失败: {'; '.join(r['failures'])}）" if not r["fix_ok"] else ""
            print(f"- {mark} {r['case']}{miss}{fails}")
        print(f"\n## 总评：{'全部达标 ✅' if report['all_passed'] else '存在未达标 ❌'}")
        print(f"- 选型正确率：{report['stat_selection']['rate']*100:.0f}%")
        print(f"- 缺陷检测率：{report['clean_detection']['rate']*100:.0f}%")
        print(f"- 修复达标率：{report['clean_fix']['rate']*100:.0f}%")

    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
