# -*- coding: utf-8 -*-
"""test_routing.py — 决策路由 / 循环终止 单元测试（无需 LLM）

在导入 agent 前先桩掉重依赖，使本测试可在仅装了 pandas/numpy 的环境运行。
"""
import sys, os, json, types

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

for name in ["langchain", "langchain_openai", "langchain_core",
             "langgraph", "langgraph.graph", "langgraph.checkpoint.memory", "dotenv"]:
    sys.modules[name] = types.ModuleType(name)
sys.modules["langchain_openai"].ChatOpenAI = object
class _Msg:
    def __init__(self, content=""): self.content = content
sys.modules["langchain_core"] = types.ModuleType("langchain_core")
sys.modules["langchain_core.messages"] = types.ModuleType("langchain_core.messages")
for nm, cls in [("SystemMessage", _Msg), ("HumanMessage", _Msg), ("AIMessage", _Msg)]:
    setattr(sys.modules["langchain_core.messages"], nm, cls)
sys.modules["langgraph.graph"].StateGraph = object
sys.modules["langgraph.graph"].END = "END"
sys.modules["langgraph.checkpoint.memory"].MemorySaver = object
sys.modules["dotenv"].load_dotenv = lambda *a, **k: None

from agent import _decide_action, MAX_STEPS


def _state(step, log, problem_count):
    return {
        "step_count": step,
        "analysis_log": log,
        "issues_json": json.dumps({"problem_count": problem_count}),
    }


def test_forced_load_first():
    """尚未加载时，无论 LLM 想干嘛都先 load"""
    st = _state(0, [], 5)
    assert _decide_action(st, "clean") == "load"


def test_clean_when_issues_remain_and_under_limit():
    """load 完成、仍有问题、清洗<2：尊重 LLM 的 clean 决定"""
    log = [{"step": "load"}]
    st = _state(1, log, 5)
    assert _decide_action(st, "clean") == "clean"


def test_forced_stats_after_two_cleans():
    """清洗满 2 次后强制进入 stats（修复之前的死循环）"""
    log = [{"step": "load"}, {"step": "clean"}, {"step": "analyze"}, {"step": "clean"}]
    st = _state(4, log, 2)
    assert _decide_action(st, "clean") == "stats"


def test_forced_stats_when_no_issues_after_clean():
    """清洗 1 次后已无问题：进入 stats"""
    log = [{"step": "load"}, {"step": "clean"}]
    st = _state(2, log, 0)
    assert _decide_action(st, "clean") == "stats"


def test_forced_viz_after_stats():
    """stats 完成、viz 未完成：进入 viz"""
    log = [{"step": "load"}, {"step": "clean"}, {"step": "stats"}]
    st = _state(3, log, 0)
    assert _decide_action(st, "clean") == "viz"


def test_forced_report_after_viz():
    """viz 完成、report 未完成：进入 report"""
    log = [{"step": "load"}, {"step": "clean"}, {"step": "stats"}, {"step": "viz"}]
    st = _state(4, log, 0)
    assert _decide_action(st, "stats") == "report"


def test_forced_done_after_report():
    """report 已完成：进入 done（结束）"""
    log = [{"step": "load"}, {"step": "clean"}, {"step": "stats"},
           {"step": "viz"}, {"step": "report"}]
    st = _state(5, log, 0)
    assert _decide_action(st, "stats") == "done"


def test_max_steps_forces_report():
    """超过最大步数强制 report，保证终止"""
    st = _state(MAX_STEPS, [{"step": "load"}], 0)
    assert _decide_action(st, "clean") == "report"
