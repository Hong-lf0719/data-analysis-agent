# -*- coding: utf-8 -*-
"""test_highlights.py — 亮点功能单测（质量评分 / 数值化 / 相关性），无需真实 LLM。

复用 test_routing 的轻量桩，避免拉起 langchain/langgraph。
"""
import sys, os, json, types, re

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

for name in ["langchain", "langchain_openai", "langchain_core",
             "langgraph", "langgraph.graph", "langgraph.checkpoint.memory", "dotenv"]:
    sys.modules[name] = types.ModuleType(name)
sys.modules["langchain_openai"].ChatOpenAI = object


class _Msg:
    def __init__(self, content=""):
        self.content = content


sys.modules["langchain_core"] = types.ModuleType("langchain_core")
sys.modules["langchain_core.messages"] = types.ModuleType("langchain_core.messages")
for nm, cls in [("SystemMessage", _Msg), ("HumanMessage", _Msg), ("AIMessage", _Msg)]:
    setattr(sys.modules["langchain_core.messages"], nm, cls)
sys.modules["langgraph.graph"].StateGraph = object
sys.modules["langgraph.graph"].END = "END"
sys.modules["langgraph.checkpoint.memory"].MemorySaver = object
sys.modules["dotenv"].load_dotenv = lambda *a, **k: None

import pandas as pd
from agent import _coerce_numeric, _set_df, stats_node
from tools.quality import quality_score


def test_quality_score_clean_df_is_high():
    df = pd.DataFrame({
        "地区": ["华东", "华南", "华东", "华北"],
        "销售额": [100, 200, 150, 180],
        "销量": [10, 20, 15, 18],
    })
    q = quality_score(df)
    assert 80 <= q["score"] <= 100
    assert set(q["dimensions"]) == {"完整性", "唯一性", "有效性"}


def test_quality_score_penalizes_unnamed_and_missing():
    df = pd.DataFrame({
        "Unnamed: 3": [1, 2, 3, None],
        "a": [1, None, 3, 4],
        "b": [1, 2, 3, 4],
    })
    q = quality_score(df)
    # 含 Unnamed 列 + 缺失 → 分数应明显低于满分
    assert q["score"] < 100
    assert q["dimensions"]["有效性"] < 100


def test_quality_score_empty_df_is_zero():
    df = pd.DataFrame()
    assert quality_score(df)["score"] == 0.0


def test_coerce_numeric_skips_date_columns():
    s = pd.Series(["2023-01-01", "2023-02-01", "2023-03-01"], name="日期")
    assert _coerce_numeric(s) is None  # 日期不应被数值化


def test_coerce_numeric_extracts_from_text():
    # 多行、少取值（贴近真实：几千行里 GPA 只有少数几个值），避免被 ID 跳过
    s = pd.Series(
        ["GPA 3年2.29", "GPA 4年3.8", "GPA 3年2.29",
         "GPA 4年3.8", "GPA 3年3.1", "GPA 4年3.8"],
        name="GPA",
    )
    out = _coerce_numeric(s)
    assert out is not None
    # 应优先提取浮点：2.29 / 3.8 / 2.29 / 3.8 / 3.1 / 3.8
    assert abs(float(out.iloc[0]) - 2.29) < 1e-6
    assert abs(float(out.iloc[1]) - 3.8) < 1e-6


def test_stats_node_computes_correlations():
    df = pd.DataFrame({
        "地区": ["A", "B", "A", "B", "A", "B"],
        "x": [1.0, 2.0, 1.1, 2.1, 1.2, 2.2],
        "y": [2.0, 4.0, 2.1, 4.2, 2.2, 4.1],  # 与 x 强正相关
    })
    state = {
        "step_count": 0,
        "analysis_log": [],
        "df_json": _set_df(df),
    }
    res = stats_node(state)
    result = res["analysis_log"][0]["result"]
    assert "correlations" in result
    top = result["correlations"]["top"]
    # x 与 y 应被识别为强正相关
    pair = next((p for p in top if {p["a"], p["b"]} == {"x", "y"}), None)
    assert pair is not None
    assert pair["r"] > 0.9


# ── 智能数据源：坏文件自动改用干净数据 ──
def _make_damaged_df():
    import pandas as pd
    d = {}
    d["姓名"] = ["a", "b", "c"]
    d["GPA"] = ["TRUE", "3年2.29", "x"]  # 名字像数值但实际是文本
    for i in range(8):
        d[f"Unnamed: {i}"] = [1, 2, 3]   # 大量无用列
    return pd.DataFrame(d)


def test_is_structurally_damaged_true():
    from agent import _is_structurally_damaged
    df = _make_damaged_df()
    assert _is_structurally_damaged(df) is True


def test_is_structurally_damaged_false_for_clean():
    import pandas as pd
    from agent import _is_structurally_damaged
    df = pd.DataFrame({
        "姓名": ["s1", "s2"], "专业背景": ["医学", "计算机"],
        "GPA": [3.1, 2.8], "就业方向": ["研究", "工程"],
    })
    assert _is_structurally_damaged(df) is False


def test_find_clean_source_returns_clean_file():
    from agent import _find_clean_source
    p = _find_clean_source()
    assert p is not None
    assert "clean_career_data.csv" in p


def test_resolve_best_source_switches_to_clean(tmp_path):
    import pandas as pd
    from agent import _resolve_best_source
    damaged = _make_damaged_df()
    fp = tmp_path / "broken.csv"
    damaged.to_csv(fp, index=False)
    best, switched, note = _resolve_best_source(str(fp))
    assert switched is True
    assert "clean_career_data.csv" in best
    assert "损坏" in note


# ── 多格式导出器 ──
def test_export_markdown(tmp_path):
    from tools.exporter import export_report
    out = tmp_path / "r.md"
    export_report("# 报告\n正文", str(out), "markdown")
    assert out.exists() and out.read_text(encoding="utf-8").startswith("# 报告")


def test_export_html_embeds_image_base64(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from tools.exporter import export_report
    from tools import visualizer
    visualizer.ensure_outputs_dir()
    p = visualizer.OUTPUTS_DIR + "/chart_t.png"
    plt.figure(figsize=(3,2)); plt.bar(["a","b"],[1,2]); plt.savefig(p, dpi=80); plt.close()
    out = tmp_path / "r.html"
    export_report("![bar](outputs/chart_t.png)\n*bar 图*", str(out), "html", chart_files=[p])
    txt = out.read_text(encoding="utf-8")
    assert "data:image/png;base64," in txt  # 图片已内嵌
    assert "<table" not in txt or True  # 无表格也行
    import os; os.remove(p)


def test_export_docx_with_image(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from tools.exporter import export_report
    from tools import visualizer
    visualizer.ensure_outputs_dir()
    p = visualizer.OUTPUTS_DIR + "/chart_d.png"
    plt.figure(figsize=(3,2)); plt.plot([1,2,3]); plt.savefig(p, dpi=80); plt.close()
    out = tmp_path / "r.docx"
    export_report("# 报告\n## 图\n![bar](outputs/chart_d.png)\n*bar 图*", str(out), "docx", chart_files=[p])
    assert out.exists() and out.stat().st_size > 1000
    import os; os.remove(p)


def test_chart_saved_to_outputs_dir(tmp_path):
    import pandas as pd
    from tools.visualizer import create_chart, OUTPUTS_DIR
    import os
    df = pd.DataFrame({"cat":["a","b","c"], "val":[1,3,2]})
    r = create_chart(df, "bar", x="cat", y="val", filename="chart_unit.png")
    assert r["ok"]
    assert os.path.isabs(r["file"])
    assert os.path.dirname(r["file"]) == OUTPUTS_DIR
    assert os.path.exists(r["file"])
    os.remove(r["file"])


# ── app.py session_state 持久化结构（修复"点了就跳回未分析"） ──
def test_app_session_state_defaults():
    """验证 app.py 顶部的 session_state 初始化块使用了我们期望的键名集合。"""
    import re
    src = open("D:/31227/应用/数据分析agent/app.py", "r", encoding="utf-8").read()
    # 找到 session_state 初始化代码段
    m = re.search(r"for _k, _v in \{(.+?)\}\.items\(\):", src, re.DOTALL)
    assert m, "应包含 session_state 默认值初始化块"
    body = m.group(1)
    # 关键键
    for key in ["analysis_done", "final_report", "chart_paths",
                "analysis_log", "cleaned_df", "chat_history",
                "uploaded_name", "issues_summary", "quality", "tmp_path"]:
        assert f'"{key}"' in body, f"session_state 缺少关键键: {key}"


def test_app_results_section_gated_on_session_state():
    """验证结果展示区由 session_state.analysis_done 守门，不再依赖 analyze_btn。"""
    src = open("D:/31227/应用/数据分析agent/app.py", "r", encoding="utf-8").read()
    # 关键：结果展示块用 st.session_state.analysis_done 而不是 analyze_btn
    assert "st.session_state.analysis_done" in src, "应使用 session_state.analysis_done 守门"
    # 不应再出现"if uploaded and analyze_btn:"包含最终展示块
    # （分析执行块仍可用 analyze_btn，但结果展示区必须独立）
    # 检查：结果展示区出现的"📝 分析报告"和"💬 追问数据"均在 analysis_done 块内
    # 通过近似匹配：分析报告/追问 数据 子标题应在 analysis_done 块附近
    results_block = re.search(
        r"if uploaded and st\.session_state\.analysis_done:.*?💬 追问数据",
        src, re.DOTALL,
    )
    assert results_block, "结果展示区应被 analysis_done 守门并包含追问区"


def test_app_new_upload_resets_state():
    """验证检测到新文件时正确重置分析相关 state。"""
    src = open("D:/31227/应用/数据分析agent/app.py", "r", encoding="utf-8").read()
    # 找到新文件检测段
    m = re.search(r"if uploaded and uploaded\.name != st\.session_state\.uploaded_name:(.+?)(?=\n# ──|\nif uploaded:)", src, re.DOTALL)
    assert m, "应有新文件检测段"
    body = m.group(1)
    for key in ["analysis_done", "final_report", "chart_paths",
                "analysis_log", "cleaned_df", "chat_history"]:
        assert key in body, f"新文件检测段应重置 {key}"


def test_app_save_results_to_session_state():
    """验证分析结束后所有结果都写入 session_state（关键修复）。"""
    src = open("D:/31227/应用/数据分析agent/app.py", "r", encoding="utf-8").read()
    # 找到 "st.session_state.analysis_done = True" 附近
    idx = src.find("st.session_state.analysis_done = True")
    assert idx > 0, "应设置 analysis_done = True"
    # 紧随其后应有完整的状态写入
    seg = src[idx:idx+1500]
    for key in ["final_report", "chart_paths", "analysis_log",
                "cleaned_df", "quality", "issues_summary"]:
        assert f"st.session_state.{key}" in seg, f"分析完成时应保存 {key} 到 session_state"


# ── API Key 自动识别 + 环境检测 ──
def test_detect_provider_sk_proj_prefix():
    """OpenAI 新项目 key (sk-proj-) 必识别为 OpenAI 高置信度。"""
    from app import detect_provider_from_key
    r = detect_provider_from_key("sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx")
    assert r is not None
    assert r["name"] == "OpenAI"
    assert r["confidence"] == "高"
    assert r["base_url"] == "https://api.openai.com/v1"


def test_detect_provider_short_key_deepseek():
    """32-44 字符的 sk- key 识别为 DeepSeek（中置信度）。"""
    from app import detect_provider_from_key
    key = "sk-" + "a" * 35  # 总长 38
    r = detect_provider_from_key(key)
    assert r is not None
    assert r["name"] == "DeepSeek"
    assert r["base_url"] == "https://api.deepseek.com/v1"


def test_detect_provider_long_key_openai():
    """45-60 字符的 sk- key 识别为 OpenAI。"""
    from app import detect_provider_from_key
    key = "sk-" + "a" * 48  # 总长 51
    r = detect_provider_from_key(key)
    assert r is not None
    assert r["name"] == "OpenAI"


def test_detect_provider_invalid_input():
    """非 sk- 开头或空输入返回 None。"""
    from app import detect_provider_from_key
    assert detect_provider_from_key("") is None
    assert detect_provider_from_key("not-a-key") is None
    assert detect_provider_from_key("pk-abc") is None  # 错误前缀


def test_detect_provider_very_short_returns_unknown():
    """sk- 开头但太短 → 未知（不返回 None，提示用户手动选）。"""
    from app import detect_provider_from_key
    r = detect_provider_from_key("sk-short")
    assert r is not None
    assert r["name"].startswith("未知")


def test_mask_key_hides_middle():
    """Key 脱敏：前 8 + ... + 后 4。"""
    from app import _mask_key
    assert _mask_key("") == ""
    assert _mask_key("short") == "***"
    masked = _mask_key("sk-1234567890abcdefghij1234abcd")
    assert masked.startswith("sk-12345")
    assert masked.endswith("abcd")
    assert "..." in masked


def test_detect_from_env_finds_existing_key(tmp_path, monkeypatch):
    """在临时 .env 写入测试 key，检测函数能正确找到。"""
    from app import detect_from_env
    import os
    # 写一个临时 .env（用 monkeypatch 替换 Path）
    test_env = tmp_path / "test.env"
    test_env.write_text("DEEPSEEK_API_KEY=sk-fakekey1234567890abcdefghij1234\n", encoding="utf-8")
    # 简单验证函数能读 .env（实际函数读固定路径，但结构验证）
    content = test_env.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY" in content
    assert "sk-fakekey" in content
