# -*- coding: utf-8 -*-
"""
LangGraph 数据分析 Agent — 决策引擎

架构：
    ┌──────────┐
    │  analyze │ ← LLM 检查数据 → 决定"下一步干什么"
    └────┬─────┘
         │
    ┌────┼────┬────┬────┬────┐
    ▼    ▼    ▼    ▼    ▼    ▼
  load clean stats viz report DONE
    │    │    │    │    │
    └────┴────┴────┴────┘
         │
    回到 analyze（循环）
"""

import os, sys, io, json, re, operator, builtins
from typing import TypedDict, Literal, Annotated
from dotenv import load_dotenv

load_dotenv()

import numpy as np
import pandas as pd
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from tools import load_data, inspect_data, read_df, find_issues, clean_data
from tools import check_assumptions, run_test
from tools import suggest_chart, create_chart
from tools import generate_report

MAX_STEPS = 12

# ── 序列化安全 ──
def _safe(obj):
    if isinstance(obj, (np.integer,)): return int(obj)
    if isinstance(obj, (np.floating,)):
        if np.isnan(obj): return None
        if np.isinf(obj): return None
        return float(obj)
    if isinstance(obj, float):
        # 纯 Python float 的 NaN/Inf
        import math
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, np.ndarray): return [_safe(v) for v in obj.tolist()]
    if isinstance(obj, dict): return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)): return [_safe(v) for v in obj]
    return obj

# ── 安全输出 ──
def _emit(*args, **kwargs):
    """替代裸 print：Streamlit 会重定向并关闭 stdout，
    裸 print 在关闭的文件上会抛 `ValueError: I/O operation on closed file`。
    这里捕获该异常，保证 Agent 在任何运行环境（CLI / Streamlit / 子进程）都不崩。"""
    try:
        builtins.print(*args, **kwargs)
    except (ValueError, OSError, AttributeError):
        pass


# ── 状态 ──
class AnalysisState(TypedDict):
    messages: Annotated[list, operator.add]
    filepath: str
    df_json: str
    data_json: str
    issues_json: str
    analysis_log: Annotated[list, operator.add]
    step_count: int
    next_action: str
    final_report: str
    chart_files: list  # 图表绝对路径清单（report 节点写入，供导出器使用）


# ── DataFrame 状态管理 ──
def _get_df(state: AnalysisState) -> pd.DataFrame:
    """从 state 获取 DataFrame — 优先用缓存，降级到磁盘"""
    dj = state.get("df_json", "")
    if dj:
        return pd.read_json(io.StringIO(dj), orient="split")
    fp = state["filepath"]
    return read_df(fp)


def _set_df(df: pd.DataFrame) -> str:
    """DataFrame → JSON 字符串（NaN 安全，保留索引）"""
    return df.to_json(orient="split", force_ascii=False, date_format="iso")


def _coerce_numeric(series: "pd.Series") -> "pd.Series | None":
    """尝试把 object 列转成数值。多数单元格是数字则返回转换后的 Series，
    否则返回 None（不该转）。支持从组合文本提取数字，如 GPA='3年2.29' → 2.29。

    自动跳过标识符型列（姓名/学号/编号/手机号等）与高基数 ID 列，
    避免把"学生0001"误转成 1、2、3… 这种无意义数值。
    """
    if pd.api.types.is_numeric_dtype(series):
        return series
    name = str(series.name or "")
    # 标识符类（姓名/学号…）以及日期/时间类不要数值化
    if re.search(r"(姓名|学号|编号|序号|手机号|电话|手机|邮箱|邮件|身份证|ID|id|日期|时间|date|time|datetime)", name, re.IGNORECASE):
        return None
    s = series.astype(str).str.strip()
    n = max(len(s), 1)
    # 1) 直接数值化（"2.79" / "100"）
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().sum() / n >= 0.5:
        if num.nunique() / n > 0.9:   # 几乎全唯一 → 疑似 ID，不转
            return None
        return num
    # 2) 从文本中提取数字（优先浮点，如 "3年2.29" → 2.29；纯 "4年" → 4）
    extracted = s.str.extract(r"(-?\d+\.\d+)")[0]  # 先取浮点
    num2 = pd.to_numeric(extracted, errors="coerce")
    if num2.notna().sum() / n >= 0.5:
        if num2.nunique() / n > 0.9:
            return None
        return num2
    extracted = s.str.extract(r"(-?\d+)")[0]  # 退回到整数
    num2 = pd.to_numeric(extracted, errors="coerce")
    if num2.notna().sum() / n >= 0.5:
        if num2.nunique() / n > 0.9:
            return None
        return num2
    return None


_NUMERIC_NAME_HINT = re.compile(r"(GPA|gpa|成绩|分数|得分|年龄|岁|收入|薪资|工资|价格|单价|金额|数量|销量|次数|时长|年限|比率|比例|占比|率)")
def _detect_structural_issue(df_before: "pd.DataFrame", df_after: "pd.DataFrame") -> str | None:
    """检测"表头合并/列错位"类结构性损坏。

    典型信号：原始表有大量无意义列（Unnamed/空列），且某个名字暗示数值的
    字段（如 GPA）实际全是非数字文本 —— 说明 CSV 由合并表头的 Excel 导出，
    列与数据已错位，无法自动修复，应改用已清洗的数据。
    """
    if df_before.shape[1] == 0:
        return None
    junk_ratio = sum(
        1 for c in df_before.columns
        if "Unnamed" in str(c) or str(c).strip() == ""
    ) / df_before.shape[1]
    # 找"名字像数值、内容却不是数值"的列
    misaligned = []
    for c in df_after.columns:
        if _NUMERIC_NAME_HINT.search(str(c)) and not pd.api.types.is_numeric_dtype(df_after[c]):
            nonnull = df_after[c].dropna().astype(str)
            if len(nonnull) and pd.to_numeric(nonnull, errors="coerce").notna().mean() < 0.5:
                misaligned.append(str(c))
    if junk_ratio >= 0.3 and misaligned:
        return (
            f"⚠️ 检测到疑似结构性损坏：原始表含 {junk_ratio*100:.0f}% 的无意义列"
            f"（Unnamed/空列），且数值型字段 {misaligned} 实际为文本，"
            f"说明文件很可能由「合并表头的 Excel」导出导致列错位。"
            f"建议改用已清洗的数据（如 data/clean/clean_career_data.csv）后重新分析。"
        )
    return None


# ── 智能数据源：坏文件自动改用干净数据 ──
def _is_structurally_damaged(df: "pd.DataFrame") -> bool:
    """判断 DataFrame 是否「结构性损坏」（由合并表头/列错位的 Excel 导出导致）。

    信号：① 大量无用列（Unnamed/空列占比 ≥ 30%）；
          ② 列名含 '?' 或同时含 ≥2 个 '·'/'、'（多个字段被合并成一列）；
          ③ 列数 ≥ 4 却无任何数值列（疑似列错位，全部文本）。
    """
    if df.shape[1] == 0:
        return False
    junk = sum(1 for c in df.columns if "Unnamed" in str(c) or str(c).strip() == "") / df.shape[1]
    if junk >= 0.3:
        return True
    for c in df.columns:
        s = str(c)
        if "?" in s and len(s) > 8:
            return True
        if s.count("·") >= 2 or s.count("、") >= 2:
            return True
    if df.shape[1] >= 4 and len(df.select_dtypes(include=[np.number]).columns) == 0:
        return True
    return False


def _find_clean_source() -> "str | None":
    """在 data/clean/ 下寻找一个结构正常的 CSV 作为干净数据源。

    评分优先：列数适中、数值列多的文件更可能是「已清洗的可分析数据」。
    """
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "clean")
    if not os.path.isdir(base):
        return None
    candidates = []
    for name in os.listdir(base):
        if not name.lower().endswith(".csv"):
            continue
        p = os.path.join(base, name)
        try:
            d = read_df(p)
        except Exception:
            continue
        if d.shape[0] < 2 or d.shape[1] < 2:
            continue
        junk = sum(1 for c in d.columns if "Unnamed" in str(c) or str(c).strip() == "") / d.shape[1]
        if junk >= 0.3:
            continue
        score = d.shape[1] + 0.5 * len(d.select_dtypes(include=[np.number]).columns)
        candidates.append((score, p))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _resolve_best_source(filepath: str):
    """若当前文件结构性损坏、且 data/clean/ 有干净文件，则自动切换数据源。

    返回 (best_filepath, switched: bool, note: str)。
    """
    try:
        df = read_df(filepath)
    except Exception:
        return filepath, False, ""
    if not _is_structurally_damaged(df):
        return filepath, False, ""
    clean = _find_clean_source()
    if not clean:
        return filepath, False, ""
    note = (f"检测到原始文件结构性损坏（{df.shape[1]} 列中大量无用/乱码列），"
            f"已自动改用干净数据：{os.path.basename(clean)}")
    return clean, True, note


# ── 决策辅助 ──
def _tally(state: AnalysisState) -> dict:
    """统计各步骤已完成次数"""
    c = {"load": 0, "clean": 0, "stats": 0, "viz": 0, "report": 0}
    for e in state.get("analysis_log", []):
        s = e.get("step", "")
        if s in c:
            c[s] += 1
    return c


def _current_problem_count(state: AnalysisState) -> int:
    """读取当前剩余问题数（来自 state 的 issues_json）。"""
    try:
        issues = json.loads(state.get("issues_json", "") or "{}")
        return issues.get("problem_count", 0) if isinstance(issues, dict) else 0
    except Exception:
        return 0


def _decide_action(state: AnalysisState, llm_action: str) -> str:
    """线性状态机式强制路由：clean / stats / viz / report 每种至少执行一次，
    保证流程必然产出「有统计、有图表、有报告」的结果，且必然终止。

    设计目标（解决历史 bug：干净数据被直接跳到 report，导致 0 检验 0 图）：
    - 始终至少做一次清洗（去无用列 + 数值化），让后续有数值列可用；
    - 清洗次数 < 2 且仍有问题 → 再洗一次（最多 2 次，避免死循环）；
    - 之后依次强制 stats → viz → report；
    - LLM 仅在「已无强制步骤」时生效，且失效（None）时退化为确定性推进，
      使 Agent 即便没有 API Key 也能跑出完整报告。
    """
    step = state.get("step_count", 0) + 1
    if step >= MAX_STEPS:
        return "report"
    counts = _tally(state)
    if counts["report"] >= 1:
        return "done"
    if counts["load"] == 0:
        return "load"
    if counts["clean"] < 1:
        return "clean"
    # 问题仍多且清洗未达上限 → 再洗一次（最多 2 次，避免死循环）
    if counts["clean"] < 2 and _current_problem_count(state) > 0:
        return "clean"
    if counts["stats"] < 1:
        return "stats"
    if counts["viz"] < 1:
        return "viz"
    if counts["report"] < 1:
        return "report"
    # LLM 兜底（仅在已无强制步骤时生效）
    if llm_action in ("load", "clean", "stats", "viz", "report", "done"):
        return llm_action
    # 都没有就按线性推进，绝不空转
    return "report"


def _extract_json(raw):
    """从 LLM 输出中稳健提取 JSON（兼容 ``` 围栏 / 多余文字）。"""
    if raw is None:
        return None
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None

# ── LLM ──
_llm_cache = None

def create_llm():
    global _llm_cache
    if _llm_cache is not None:
        return _llm_cache
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    k = {"model": model}
    if base_url: k["base_url"] = base_url
    _llm_cache = ChatOpenAI(temperature=0.1, **k)
    return _llm_cache

# ── 决策节点 ──
def analyze_node(state: AnalysisState) -> dict:
    llm = create_llm()
    step = state.get("step_count", 0) + 1
    analysis_log = state.get("analysis_log", [])

    # 统计已完成的步骤类型
    done_types = set()
    clean_count = 0
    stats_count = 0
    for e in analysis_log:
        t = e.get("step", "")
        if t == "clean":
            clean_count += 1
            done_types.add(t)
        elif t == "stats":
            stats_count += 1
            done_types.add(t)
        elif t in ("load", "viz", "report"):
            done_types.add(t)
    done_str = ", ".join(sorted(done_types)) if done_types else "无"

    # 历史摘要
    history = ""
    for e in analysis_log:
        history += f"\n[{e.get('step_num','?')}] {e.get('step','?')}: {e.get('summary','')[:80]}"

    prompt = f"""你是数据分析专家。文件：{state.get('filepath','?')}

## 数据摘要
{state.get('data_json','')[:3000]}

## 当前剩余问题
{state.get('issues_json','')[:1500]}

## 已完成的步骤类型
{done_str}

## 历史
{history if history else '（尚未开始）'}

## 清洗已执行次数
{clean_count} 次（≥2 则强制跳过）

## 统计已执行次数
{stats_count} 次（≥2 则强制 viz）

## 强制决策（优先级最高，忽略下方规则）
- 清洗次数 ≥ 2 且剩余问题数 ≤ 3 → 强制 stats
- 统计次数 ≥ 2 → 强制 viz
- 全部完成 → report

## 常规决策规则
1. 数据未加载 → load
2. 剩余问题 > 0 且清洗 < 2 → clean
3. 清洗 ≥ 2 → 强制 stats
4. stats 完成一次 且 viz 未做 → viz
5. load+stats+viz 完成 → report
6. 当前第 {step}/{MAX_STEPS} 步

返回 JSON（不要 markdown 包裹）：
{{"summary":"...","next_action":"load|clean|stats|viz|report|done","reason":"..."}}"""

    try:
        response = llm.invoke([
            SystemMessage(content="你是数据分析专家。只返回 JSON。"),
            HumanMessage(content=prompt)
        ])
        d = _extract_json(response.content) or {}
    except Exception as e:
        # LLM 失效（网络/Key/限流）→ 不崩溃，交给 _decide_action 的确定性兜底
        _emit(f"   [LLM 异常，启用确定性路由兜底] {e}")
        d = {}

    llm_action = d.get("next_action")  # 可能为 None，_decide_action 会退化推进

    # 代码层强制路由（保证流程必然终止，不受 LLM 飘忽影响）
    action = _decide_action(state, llm_action)
    if action != llm_action:
        _emit(f"   [强制路由] LLM 想走 {llm_action}，按规则改为 {action}")

    _emit(f"\n🧠 [分析-{step}] {d.get('summary','')[:100]}")
    _emit(f"   决策: {action}")

    return _safe({
        "step_count": step,
        "next_action": action,
        "analysis_log": [{
            "step_num": step, "step": "analyze",
            "summary": d.get("summary",""), "decision": action,
        }],
        "messages": [AIMessage(content=response.content)],
    })

# ── 加载节点 ──
def load_node(state: AnalysisState) -> dict:
    fp = state["filepath"]
    _emit(f"\n📂 [加载] {fp}")
    # 智能数据源：坏文件（合并表头/列错位）自动改用 data/clean/ 的干净数据
    best_fp, switched, note = _resolve_best_source(fp)
    if switched:
        _emit(f"   ⚠️ {note}")
        fp = best_fp
    data_json = inspect_data(fp)
    df = read_df(fp)
    issues = find_issues(df)
    _emit(f"   发现 {issues['problem_count']} 个问题")
    return _safe({
        "filepath": fp,  # 关键：切换后更新，后续节点读到干净数据
        "df_json": _set_df(df),
        "data_json": data_json,
        "issues_json": json.dumps(issues, ensure_ascii=False),
        "analysis_log": [{
            "step_num": state.get("step_count",0), "step": "load",
            "summary": f"加载完成: {len(df)}行×{len(df.columns)}列" + ("（已自动切换至干净数据）" if switched else ""),
            "result": {"shape": list(df.shape), "columns": list(df.columns), "switched_from_raw": switched},
        }],
    })

# ── 清洗节点 ──
def clean_node(state: AnalysisState) -> dict:
    _emit(f"\n🧹 [清洗]")
    df = _get_df(state)
    df_before = df.copy()  # 用于结构性损坏检测（对比清洗前/后）

    # 自动删除：Unnamed 列 + 缺失率 > 60% 的列（不需要 LLM 决策）
    auto_drop = []
    for col in df.columns:
        if "Unnamed" in str(col) or col.strip() == "":
            auto_drop.append(col)
        elif df[col].isnull().mean() > 0.6:
            auto_drop.append(col)
    if auto_drop:
        df.drop(columns=auto_drop, inplace=True, errors="ignore")
        _emit(f"   自动删除 {len(auto_drop)} 个无用列")

    # 数值化：把"看起来像数字"的文本列转成数值（如 GPA='3年2.29' → 2.29），
    # 这样后续统计节点 / 可视化节点才有数值列可用（否则会 0 检验、0 图）。
    coerced_cols = []
    for col in list(df.columns):
        if not pd.api.types.is_numeric_dtype(df[col]):
            new = _coerce_numeric(df[col])
            if new is not None:
                df[col] = new
                coerced_cols.append(col)
    if coerced_cols:
        _emit(f"   数值化 {len(coerced_cols)} 列: {', '.join(map(str, coerced_cols))}")

    # 结构性损坏检测（表头合并/列错位）
    warning = _detect_structural_issue(df_before, df)
    if warning:
        _emit(f"   {warning}")

    # 检测剩余问题
    issues = find_issues(df)
    problem_count = issues.get("problem_count", 0)

    # 没有剩余问题时直接跳过
    if problem_count == 0:
        _emit(f"   数据已干净，无需清洗")
        return _safe({
            "df_json": _set_df(df),
            "issues_json": "{}",
            "analysis_log": [{
                "step_num": state.get("step_count", 0), "step": "clean",
                "summary": f"清洗完成: 自动删除{len(auto_drop)}个无用列, 剩余0个问题"
                           + ("" if not warning else "；⚠️" + warning),
                "result": {"auto_dropped": len(auto_drop), "problem_count": 0,
                           "actions": [], "warning": warning},
            }],
        })

    # LLM 驱动清洗决策 — 只传前 20 个问题，避免 token 爆炸
    llm = create_llm()
    top_issues = _safe(issues["problems"])[:20]
    all_cols = list(df.columns)

    prompt = f"""你是数据清洗专家。发现以下问题（共{problem_count}个，仅展示前20个）：
{json.dumps(top_issues, ensure_ascii=False, indent=2)[:3000]}

数据列（共{len(all_cols)}列）：{all_cols[:10]}{"..." if len(all_cols) > 10 else ""}

请决定清洗方案。返回纯 JSON（不要 markdown 包裹）：
{{"actions": [
    {{"action": "drop_outliers|drop_duplicates|fillna|rename|drop_column",
      "column": "列名", "method": "median|mean|mode", "reason": "为什么"}}
]}}

规则：
1. 不要删除超过10%的数据
2. 优先填充而非删除
3. 合并重复操作：如果多个列需要相同处理，只输出一次并注明范围
4. drop_column 时如果多个连续列都要删，合并成一条说明范围"""

    try:
        resp = llm.invoke([
            SystemMessage(content="你是数据清洗专家。只返回 JSON，action 列表不超过 10 条。"),
            HumanMessage(content=prompt),
        ])
        raw = resp.content.strip()
    except Exception as e:
        _emit(f"   [LLM 异常，跳过智能清洗，仅做自动清洗] {e}")
        raw = "{}"
        actions = []
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError:
        plan = {"actions": []}
    actions = plan.get("actions", [])

    # 限制 actions 数量，防止 LLM 生成过多操作
    actions = actions[:10]
    _emit(f"   LLM 决定执行 {len(actions)} 个清洗操作")
    for a in actions:
        _emit(f"      → {a.get('action')}: {a.get('reason', '-')[:50]}")

    # ⚠️ 核心修复：直接对 cleaned 应用全部 actions，不用 clean_data 的废弃结果
    cleaned = df.copy()
    action_log = []
    before_rows = len(cleaned)
    before_cols = len(cleaned.columns)

    for act in actions:
        act_type = act.get("action", "")
        col = act.get("column", "")
        try:
            if act_type == "rename":
                old = act.get("old", col)
                new = act.get("new", "")
                if old in cleaned.columns and new:
                    cleaned.rename(columns={old: new}, inplace=True)
                    action_log.append(f"✓ 重命名: {old} → {new}")

            elif act_type == "drop_outliers":
                if col in cleaned.columns:
                    Q1, Q3 = cleaned[col].quantile(0.25), cleaned[col].quantile(0.75)
                    IQR = Q3 - Q1
                    cleaned = cleaned[(cleaned[col] >= Q1 - 3*IQR) & (cleaned[col] <= Q3 + 3*IQR)]
                    action_log.append(f"✓ 删除异常值: {col}")

            elif act_type == "fillna":
                method = act.get("method", "median")
                if col in cleaned.columns:
                    if method == "median":
                        cleaned[col] = cleaned[col].fillna(cleaned[col].median())
                    elif method == "mean":
                        cleaned[col] = cleaned[col].fillna(cleaned[col].mean())
                    elif method == "mode":
                        cleaned[col] = cleaned[col].fillna(cleaned[col].mode()[0] if not cleaned[col].mode().empty else 0)
                    action_log.append(f"✓ 填充缺失: {col} ({method})")

            elif act_type == "drop_duplicates":
                cleaned.drop_duplicates(inplace=True)
                action_log.append(f"✓ 删除重复行")

            elif act_type == "drop_column":
                if col and col in cleaned.columns:
                    cleaned.drop(columns=[col], inplace=True, errors="ignore")
                    action_log.append(f"✓ 删除列: {col}")
        except Exception as e:
            action_log.append(f"✗ 失败: {act_type}({col}) - {e}")

    after_rows = len(cleaned)
    after_cols = len(cleaned.columns)
    _emit(f"   清洗后: {before_rows}→{after_rows} 行, {before_cols}→{after_cols} 列")

    # 清洗后重新检测问题
    new_issues = find_issues(cleaned)
    _emit(f"   剩余问题: {new_issues['problem_count']} 个")

    return _safe({
        "df_json": _set_df(cleaned),
        "data_json": json.dumps({
            "shape": list(cleaned.shape),
            "columns": list(cleaned.columns),
            "describe": cleaned.describe().to_dict(),
            "sample": cleaned.head(3).to_dict(orient="records"),
        }, ensure_ascii=False),
        "issues_json": json.dumps(_safe(new_issues), ensure_ascii=False),
        "analysis_log": [{
            "step_num": state.get("step_count", 0), "step": "clean",
            "summary": f"清洗完成: {before_rows}→{after_rows}行, {before_cols}→{after_cols}列, 剩余{new_issues['problem_count']}个问题"
                       + ("" if not warning else "；⚠️" + warning),
            "result": {
                "problem_count_before": problem_count,
                "problem_count_after": new_issues["problem_count"],
                "actions": action_log,
                "warning": warning,
            },
        }],
    })

# ── 统计节点 ──
def _usable_cats(df: "pd.DataFrame", max_card: int = 50) -> list:
    """选取适合做分组变量的分类列：排除唯一值过多（如姓名/ID，nunique≈行数）
    或过少（<2）的列，避免把每个个体拿来两两比较（p=1.0 的噪声）。"""
    cats = df.select_dtypes(include=["string", "object", "category"]).columns.tolist()
    n = len(df)
    out = []
    for c in cats:
        nu = df[c].nunique(dropna=True)
        if 2 <= nu <= min(max_card, max(2, n // 2)):
            out.append(c)
    return out

def stats_node(state: AnalysisState) -> dict:
    _emit(f"\n🔬 [统计]")
    df = _get_df(state)
    nums = df.select_dtypes(include=[np.number]).columns.tolist()
    cats = _usable_cats(df)
    # 生成 (分类, 数值) 组合，限制数量避免检验爆炸（注意：未做多重比较校正）
    pairs = [(c, n) for c in cats[:3] for n in nums[:3]][:6]
    results = []
    for cat, num in pairs:
        grp = df.groupby(cat)[num]
        groups = {str(k): v.dropna().tolist() for k, v in grp}
        names = list(groups.keys())
        # 跳过组为空或样本不足（<3）的分组，避免 run_test 抛异常
        valid = [nm for nm in names if len(groups[nm]) >= 3]
        if len(valid) >= 2:
            r = run_test(np.array(groups[valid[0]]), np.array(groups[valid[1]]))
            if r.get("error"):
                _emit(f"   {valid[0]} vs {valid[1]}({num}) 检验失败: {r['error']}")
                continue
            results.append({
                "dimension": f"{cat}→{num}",
                "groups": [str(valid[0]), str(valid[1])],
                "test": str(r.get("test_used","?")),
                "p_value": float(r.get("p_value",0)),
                "significant": bool(r.get("significant",False)),
                "interpretation": str(r.get("interpretation","")),
            })
            _emit(f"   {valid[0]} vs {valid[1]}({num}): {r.get('interpretation','')}")

    # 相关性分析（亮点）：数值列 ≥ 2 时自动计算 Pearson 相关，取强相关 Top 对
    corr = {"top": []}
    numdf = df.select_dtypes(include=[np.number])
    if numdf.shape[1] >= 2:
        c = numdf.corr(numeric_only=True).round(2)
        pairs_c = []
        cols = c.columns.tolist()
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                v = c.iloc[i, j]
                if pd.notna(v) and abs(v) >= 0.3:
                    pairs_c.append({"a": cols[i], "b": cols[j], "r": float(v)})
        pairs_c.sort(key=lambda x: -abs(x["r"]))
        corr = {"top": pairs_c[:6]}
        if corr["top"]:
            _emit(f"   发现 {len(corr['top'])} 对强相关变量（|r|≥0.3）")

    return _safe({
        "analysis_log": [{
            "step_num": state.get("step_count",0), "step": "stats",
            "summary": f"{len(results)}组检验 + {len(corr['top'])}对强相关",
            "result": {"tests": results, "correlations": corr},
        }],
    })

# ── 可视化节点 ──
def viz_node(state: AnalysisState) -> dict:
    _emit(f"\n📈 [可视化]")
    df = _get_df(state)
    nums = df.select_dtypes(include=[np.number]).columns.tolist()
    # 选可读性好的分类轴：基数适中（2~20），避免把姓名/ID 这种唯一列画成上千根柱
    cats_all = df.select_dtypes(include=["string", "object", "category"]).columns.tolist()
    cats = [c for c in cats_all if 2 <= df[c].nunique(dropna=True) <= 20] or cats_all[:1]
    charts = []
    if cats and nums:
        r = create_chart(df, "bar", x=cats[0], y=nums[0], filename="chart_bar.png")
        charts.append(r)
        r = create_chart(df, "box", column=nums[0], by=cats[0], filename="chart_box.png")
        charts.append(r)
        _emit(f"   生成 {len(charts)} 张图表（x轴: {cats[0]}, y轴: {nums[0]}）")
    elif nums:
        r = create_chart(df, "hist", column=nums[0], filename="chart_hist.png")
        charts.append(r)
        _emit(f"   无合适分类轴，生成 {len(charts)} 张数值分布图")
    else:
        # 纯分类数据：画频次图，避免「无图」的空结果
        if cats_all:
            r = create_chart(df, "count", column=cats_all[0], filename="chart_freq.png")
            charts.append(r)
            _emit(f"   无数值列，生成分类频次图: {cats_all[0]}")

    # 相关性热力图（亮点）：数值列 ≥ 2 时自动生成
    if len(nums) >= 2:
        r = create_chart(df, "heatmap", filename="chart_corr.png")
        if r.get("ok"):
            charts.append(r)
            _emit(f"   生成相关性热力图（{len(nums)} 个数值变量）")
    return _safe({
        "analysis_log": [{
            "step_num": state.get("step_count",0), "step": "viz",
            "summary": f"生成{len(charts)}张图",
            "result": {"charts": charts},
        }],
    })

# ── 报告节点 ──
def report_node(state: AnalysisState) -> dict:
    _emit(f"\n📝 [报告]")
    log = state.get("analysis_log", [])
    _emit(f"   analysis_log 条目数: {len(log)}")
    for e in log:
        _emit(f"   [{e.get('step_num','?')}] {e.get('step','?')}: {e.get('summary','')[:60]}")
    dj = state.get("data_json", "")

    # 用"清洗后"的数据计算概览，使"数据概况"展示真实被分析的列，而非 76 列原始脏数据
    try:
        _df = _get_df(state)
        cleaned_overview = {
            "shape": [int(_df.shape[0]), int(_df.shape[1])],
            "columns": [str(c) for c in _df.columns],
        }
    except Exception:
        _df = None
        cleaned_overview = None

    # 数据质量评分（亮点）：基于清洗后数据的完整性/唯一性/有效性
    quality = None
    if _df is not None:
        try:
            from tools.quality import quality_score
            quality = quality_score(_df)
        except Exception as e:
            _emit(f"   [质量评分跳过] {e}")
            quality = None

    # 工具生成基础报告（返回完整文本，不再只取 preview 前 500 字）
    rr = generate_report(log, dj[:500], cleaned_overview=cleaned_overview, quality=quality)
    base = rr.get("report", rr.get("preview", ""))
    chart_files = rr.get("charts", [])  # 图表绝对路径清单，供导出器内嵌

    # LLM 生成业务洞察（API 不可用时不崩溃，给出降级说明）
    llm = create_llm()
    log_text = json.dumps([{
        "step": e.get("step"), "summary": e.get("summary"),
    } for e in log], ensure_ascii=False)

    prompt = f"""基于分析记录，给出业务建议（200字内）。

分析记录：{log_text}
数据摘要：{dj[:1000]}

输出：
1. 关键发现（2-3条）
2. 业务建议（2-3条）"""

    try:
        resp = llm.invoke([
            SystemMessage(content="你是商业分析师。"),
            HumanMessage(content=prompt),
        ])
        insights = resp.content
    except Exception as e:
        _emit(f"   [LLM 异常，跳过业务洞察] {e}")
        insights = "（本次未生成 LLM 业务洞察：API 暂时不可用。报告已包含完整的数据概况、清洗、统计检验与可视化结论。）"

    full = base + "\n\n## 业务洞察\n\n" + insights

    with open("analysis_report.md", "w", encoding="utf-8") as f:
        f.write(full)

    return _safe({
        "final_report": full,
        "chart_files": chart_files,
        "analysis_log": [{
            "step_num": state.get("step_count",0), "step": "report",
            "summary": "报告生成完成",
            "result": {"file": "analysis_report.md"},
        }],
    })

# ── 路由 ──
def route_action(state: AnalysisState) -> Literal["load","clean","stats","viz","report","__end__"]:
    a = state.get("next_action", "done")
    if a == "done":
        return "__end__"
    if a in ("load","clean","stats","viz","report"):
        return a
    return "__end__"

# ── 组装图 ──
def create_agent():
    g = StateGraph(AnalysisState)
    for n in ["analyze","load","clean","stats","viz","report"]:
        g.add_node(n, globals()[f"{n}_node"])
    g.set_entry_point("analyze")
    g.add_conditional_edges("analyze", route_action, {
        "load":"load","clean":"clean","stats":"stats","viz":"viz","report":"report","__end__":END,
    })
    g.add_edge("load","analyze")
    g.add_edge("clean","analyze")
    g.add_edge("stats","analyze")
    g.add_edge("viz","analyze")
    g.add_edge("report", END)
    return g.compile(checkpointer=MemorySaver())


# ── 多轮对话 ──
def answer_question(filepath: str, analysis_log: list, data_json: str,
                   final_report: str, question: str,
                   df: pd.DataFrame = None) -> str:
    """
    基于分析结果回答用户的追问。
    支持：数据筛选、深入分析、预测、解释等。
    """
    llm = create_llm()

    # 构建上下文
    log_text = json.dumps(_safe([{
        "step": e.get("step"), "summary": e.get("summary"),
    } for e in analysis_log]), ensure_ascii=False, indent=2)

    # 如果有 DataFrame，提供数据样本
    df_context = ""
    if df is not None:
        df_context = f"""
## 当前数据
列：{list(df.columns)}
行数：{len(df)}
统计摘要：
{df.describe().to_string()[:1500]}

前5行样本：
{df.head(5).to_string()}
"""

    prompt = f"""你是数据分析专家，刚完成了一份数据分析报告。用户现在追问你问题。

## 文件
{filepath}

{df_context}

## 分析过程
{log_text[:2000]}

## 之前的报告摘要
{final_report[:2000]}

## 用户的问题
{question}

请基于以上分析结果和数据，简洁回答用户的问题（不超过300字）：
1. 如果涉及数据筛选/分组，说明你会怎么操作
2. 如果能直接回答，给出答案
3. 如果需要进行额外分析，说明分析思路和预期结果"""

    resp = llm.invoke([
        SystemMessage(content="你是数据分析专家，回答要基于数据、简洁有力。"),
        HumanMessage(content=prompt),
    ])
    return resp.content


def _filter_df(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """根据自然语言查询筛选 DataFrame（简单实现）。"""
    query_lower = query.lower()
    result = df.copy()

    # 地区筛选
    if "华东" in query:
        if "地区" in result.columns:
            result = result[result["地区"] == "华东"]
    elif "华南" in query:
        if "地区" in result.columns:
            result = result[result["地区"] == "华南"]
    elif "华北" in query:
        if "地区" in result.columns:
            result = result[result["地区"] == "华北"]

    # 产品筛选
    if "电子产品" in query or "电子" in query_lower:
        if "产品类别" in result.columns:
            result = result[result["产品类别"] == "电子产品"]
    elif "家居" in query:
        if "产品类别" in result.columns:
            result = result[result["产品类别"] == "家居用品"]
    elif "家电" in query:
        if "产品类别" in result.columns:
            result = result[result["产品类别"] == "家电"]

    return result

# ── 入口 ──
def analyze(filepath: str) -> dict:
    agent = create_agent()
    cfg = {"configurable": {"thread_id": f"a-{os.path.basename(filepath)}"}}

    initial = {
        "filepath": filepath, "df_json": "", "data_json": "", "issues_json": "",
        "analysis_log": [], "step_count": 0, "next_action": "load",
        "final_report": "", "chart_files": [], "messages": [],
    }

    _emit("=" * 60)
    _emit(f"LangGraph 数据分析 Agent | {filepath}")
    _emit("=" * 60)

    for event in agent.stream(initial, cfg):
        pass

    final = agent.get_state(cfg)
    report = final.values.get("final_report", "")
    _emit(f"\n{'='*60}\n最终报告：\n{'='*60}")
    _emit(report[:2000])
    _emit("=" * 60)
    return {"ok": True, "final_report": report, "analysis_log": final.values.get("analysis_log",[]),
            "df_json": final.values.get("df_json", ""),
            "chart_files": final.values.get("chart_files", [])}

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        _emit("用法: python agent.py <文件路径>")
        _emit("示例: python agent.py data/sample_sales.csv")
        sys.exit(1)
    result = analyze(sys.argv[1])
    _interactive_loop(result, sys.argv[1])


def _interactive_loop(result: dict, filepath: str):
    """分析完成后的交互式问答"""
    import sys
    report = result.get("final_report", "")
    analysis_log = result.get("analysis_log", [])

    # 追问基于"清洗后"的数据（来自 agent 最终状态），而非原始文件
    df_json = result.get("df_json", "")
    if df_json:
        try:
            df = pd.read_json(io.StringIO(df_json), orient="split")
        except Exception:
            df = None
    else:
        df = None
    if df is None:
        try:
            df = read_df(filepath)
        except Exception:
            df = None

    _emit(f"\n{'='*60}")
    _emit("💬 你可以继续追问数据相关的问题（输入 q 退出）")
    _emit(f"{'='*60}")

    while True:
        try:
            q = input("\n🔍 你的问题: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in ("q", "quit", "exit", "退出"):
            _emit("再见！")
            break

        _emit(f"\n🤔 思考中...")
        try:
            answer = answer_question(
                filepath=filepath,
                analysis_log=analysis_log,
                data_json="",
                final_report=report,
                question=q,
                df=df,
            )
            _emit(f"\n📝 {answer}")
        except Exception as e:
            _emit(f"\n❌ 回答失败: {e}")


def main():
    """CLI 入口：daa <文件路径>"""
    import sys
    if len(sys.argv) < 2:
        _emit("用法: daa <文件路径>")
        _emit("示例: daa data/sample_sales.csv")
        sys.exit(1)
    result = analyze(sys.argv[1])
    _interactive_loop(result, sys.argv[1])
    if not result.get("ok"):
        sys.exit(1)
