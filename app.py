# -*- coding: utf-8 -*-
"""
📊 Data Analysis Agent — Web UI

启动：streamlit run app.py
"""
import sys, os, io, json, time

import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Data Analysis Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 把项目根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import create_agent, _get_df, _set_df, _safe, AnalysisState, answer_question
from agent import _is_structurally_damaged, _find_clean_source
from tools.loader import inspect_data, read_df
from tools.cleaner import find_issues
from tools.visualizer import OUTPUTS_DIR, ensure_outputs_dir
from tools.exporter import export_report, SUPPORTED as EXPORT_SUPPORTED

# ── 页面样式 ──
st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 700; margin-bottom: 0; }
    .step-box {
        padding: 12px 16px; border-radius: 8px; margin: 4px 0;
        border-left: 4px solid #4e79a7; background: #f8f9fa;
    }
    .step-load { border-left-color: #59a14f; }
    .step-clean { border-left-color: #e15759; }
    .step-stats { border-left-color: #4e79a7; }
    .step-viz { border-left-color: #f28e2b; }
    .step-report { border-left-color: #76b7b2; }
    .step-analyze { border-left-color: #b07aa1; }
</style>
""", unsafe_allow_html=True)


# ── 报告渲染辅助 ──
import re as _re

def _resolve_chart_path(ref: str, chart_paths: list) -> str | None:
    """把报告里的图片引用解析成可读的绝对路径。"""
    if os.path.exists(ref):
        return ref
    if not os.path.isabs(ref):
        abs_ref = os.path.abspath(ref)
        if os.path.exists(abs_ref):
            return abs_ref
    base = os.path.basename(ref)
    for p in chart_paths:
        if os.path.basename(p) == base:
            return p
    return None


def _render_report_with_images(report_text: str, chart_paths: list):
    """把报告按图片引用拆段：文本段用 st.markdown，图片段用 st.image 内联显示。
    这样不再出现 st.markdown 不渲染图片导致的「bar bar 图」替代文字。"""
    # 匹配 ![alt](path) 后面可能跟一行 *xxx 图* 图注
    pattern = _re.compile(r"!\[([^\]]*)\]\(([^)]+)\)\s*\n\*([^\n]*图)\*")
    pos = 0
    for m in pattern.finditer(report_text):
        # 渲染图片前的文本段
        before = report_text[pos:m.start()]
        if before.strip():
            st.markdown(before)
        alt, ref, caption = m.group(1), m.group(2), m.group(3)
        path = _resolve_chart_path(ref, chart_paths)
        if path:
            try:
                st.image(path, caption=caption, use_container_width=True)
            except Exception as e:
                st.warning(f"图片加载失败: {caption} ({e})")
        else:
            st.info(f"🖼️ {caption}（图片文件未找到：{ref}）")
        pos = m.end()
    # 兜底：处理没有图注的单独图片引用
    tail = report_text[pos:]
    if tail.strip():
        # 再扫一遍无图注的 ![alt](path)
        simple = _re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
        last = 0
        for m2 in simple.finditer(tail):
            seg = tail[last:m2.start()]
            if seg.strip():
                st.markdown(seg)
            alt, ref = m2.group(1), m2.group(2)
            path = _resolve_chart_path(ref, chart_paths)
            if path:
                try:
                    st.image(path, caption=alt, use_container_width=True)
                except Exception as e:
                    st.warning(f"图片加载失败: {alt} ({e})")
            else:
                st.info(f"🖼️ {alt}（图片文件未找到：{ref}）")
            last = m2.end()
        end_seg = tail[last:]
        if end_seg.strip():
            st.markdown(end_seg)


def _render_download_panel(final_report: str, chart_paths: list):
    """多格式下载面板：Markdown / HTML / PDF / DOCX，按可用库启用。"""
    if not final_report:
        st.info("暂无报告可下载")
        return

    st.markdown("**选择导出格式：**")
    fmt_options = []
    hints = {
        "markdown": "Markdown (.md) — 纯文本，可再编辑",
        "html": "HTML (.html) — 自包含单文件，图片内嵌，可直接浏览器打开",
        "pdf": "PDF (.pdf) — 适合打印分发",
        "docx": "Word (.docx) — 可在 Word/WPS 中编辑",
    }
    for fmt in ["markdown", "html", "pdf", "docx"]:
        if EXPORT_SUPPORTED.get(fmt):
            fmt_options.append((fmt, hints[fmt]))
    if not fmt_options:
        st.warning("无可用的导出后端，请安装 markdown / python-docx / xhtml2pdf")
        return

    choice = st.radio(
        "格式",
        options=[f[0] for f in fmt_options],
        format_func=lambda f: next(h for h in fmt_options if h[0] == f)[1],
        label_visibility="collapsed",
    )

    # 生成导出文件
    import tempfile, time
    ts = time.strftime("%Y%m%d_%H%M%S")
    ext = {"markdown": "md", "html": "html", "pdf": "pdf", "docx": "docx"}[choice]
    out_name = f"analysis_report_{ts}.{ext}"
    tmp = os.path.join(tempfile.gettempdir(), out_name)
    try:
        export_report(final_report, tmp, choice, chart_files=chart_paths)
        with open(tmp, "rb") as f:
            data = f.read()
        mime = {
            "markdown": "text/markdown", "html": "text/html",
            "pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }[choice]
        st.download_button(
            f"📥 下载 {out_name}",
            data=data,
            file_name=out_name,
            mime=mime,
            use_container_width=True,
        )
        st.caption(f"格式：{choice.upper()} · 大小：{len(data)/1024:.1f} KB · 图片：{len(chart_paths)} 张内嵌")
    except Exception as e:
        st.error(f"导出失败：{e}")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


# ── 标题 ──
st.markdown('<p class="main-header">📊 Data Analysis Agent</p>', unsafe_allow_html=True)
st.caption("上传数据 → AI Agent 自动清洗、统计检验、可视化、生成报告")

# ── 侧边栏：配置 ──

# 服务商预设（key 长度启发式 + 显式前缀）
_PROVIDER_PRESETS = [
    {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
        "env_var": "DEEPSEEK_API_KEY",
    },
    {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
        "default_model": "gpt-4o-mini",
        "env_var": "OPENAI_API_KEY",
    },
    {
        "name": "Qwen (DashScope)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max"],
        "default_model": "qwen-plus",
        "env_var": "DASHSCOPE_API_KEY",
    },
    {
        "name": "Zhipu (智谱)",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-plus", "glm-4-flash"],
        "default_model": "glm-4-flash",
        "env_var": "ZHIPUAI_API_KEY",
    },
]


def _mask_key(key: str) -> str:
    """脱敏显示 API Key：前 8 字符 + ... + 后 4 字符。"""
    if not key or len(key) < 12:
        return "***" if key else ""
    return f"{key[:8]}...{key[-4:]}"


def detect_provider_from_key(key: str) -> dict | None:
    """根据 API Key 字符串特征自动识别服务商。返回 {name, base_url, model, confidence} 或 None。
    启发式：
    - OpenAI 新项目 key 以 'sk-proj-' 开头 → OpenAI（高置信度）
    - 长度 32-44 字符 → 多半是 DeepSeek
    - 长度 48+ 字符 → 多半是 OpenAI 旧 key
    - 含 'dashscope' / 'qwen' 不在 key 中（按长度和常见模式判断）
    """
    if not key or not isinstance(key, str) or not key.strip().startswith("sk-"):
        return None
    key = key.strip()
    # OpenAI 新项目 key
    if key.startswith("sk-proj-"):
        return {
            "name": "OpenAI",
            "base_url": _PROVIDER_PRESETS[1]["base_url"],
            "model": _PROVIDER_PRESETS[1]["default_model"],
            "confidence": "高",
        }
    # 长度判断
    L = len(key)
    if 32 <= L <= 44:
        return {
            "name": "DeepSeek",
            "base_url": _PROVIDER_PRESETS[0]["base_url"],
            "model": _PROVIDER_PRESETS[0]["default_model"],
            "confidence": "中",
        }
    if 45 <= L <= 60:
        return {
            "name": "OpenAI",
            "base_url": _PROVIDER_PRESETS[1]["base_url"],
            "model": _PROVIDER_PRESETS[1]["default_model"],
            "confidence": "中",
        }
    # 太长/太短，标为未知
    return {
        "name": "未知（请手动选服务商）",
        "base_url": "",
        "model": "",
        "confidence": "低",
    }


def detect_from_env() -> list[dict]:
    """扫描系统环境变量 + 项目 .env + ~/.env，找出所有可能的 API Key 配置。
    返回列表，每项: {source, provider, key, key_preview, base_url, model, env_var}。
    """
    import re
    from pathlib import Path
    found = {}

    # 1. 系统环境变量（按服务商预设）
    for preset in _PROVIDER_PRESETS:
        for env_name in [preset["env_var"], "OPENAI_API_KEY"]:
            val = os.getenv(env_name)
            if val and val.strip() and len(val) > 16:
                found[val] = {
                    "source": f"环境变量 ${env_name}",
                    "provider": preset["name"],
                    "key": val.strip(),
                    "key_preview": _mask_key(val.strip()),
                    "base_url": preset["base_url"],
                    "model": preset["default_model"],
                    "env_var": env_name,
                }
                break  # 每个 Key 优先归到最匹配的服务商

    # 2. .env 文件（项目根 + 用户家目录）
    env_paths = [
        Path(__file__).parent / ".env",  # 项目根
        Path.home() / ".env",             # 用户家目录
    ]
    key_pattern = re.compile(r'^\s*([A-Z][A-Z0-9_]*_API_KEY)\s*=\s*"?([^"\s#]+)"?', re.IGNORECASE)
    for env_path in env_paths:
        if not env_path.exists():
            continue
        try:
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = key_pattern.match(line)
                if not m:
                    continue
                var_name, val = m.group(1), m.group(2)
                if not val or len(val) < 16:
                    continue
                # 匹配服务商
                preset = next((p for p in _PROVIDER_PRESETS if p["env_var"] == var_name.upper()), None)
                provider = preset["name"] if preset else "Unknown"
                base_url = preset["base_url"] if preset else ""
                model = preset["default_model"] if preset else ""
                if val not in found:
                    found[val] = {
                        "source": f".env: {var_name} ({env_path.name})",
                        "provider": provider,
                        "key": val,
                        "key_preview": _mask_key(val),
                        "base_url": base_url,
                        "model": model,
                        "env_var": var_name,
                    }
        except Exception:
            continue

    return list(found.values())


def _apply_config(cfg: dict):
    """把候选配置应用到 session_state（让 UI 自动同步）。"""
    st.session_state["_picked_key"] = cfg["key"]
    st.session_state["_picked_url"] = cfg.get("base_url", "")
    st.session_state["_picked_model"] = cfg.get("model", "")
    # 实际生效的环境变量
    if cfg.get("env_var"):
        os.environ[cfg["env_var"]] = cfg["key"]
    os.environ["OPENAI_API_KEY"] = cfg["key"]
    if cfg.get("base_url"):
        os.environ["OPENAI_BASE_URL"] = cfg["base_url"]


with st.sidebar:
    st.header("⚙️ 配置")

    # ── 🔍 自动检测环境 ──
    if st.button("🔍 自动检测环境", use_container_width=True, key="btn_auto_detect"):
        st.session_state.detect_results = detect_from_env()
        st.session_state.detect_shown = True

    if st.session_state.get("detect_shown"):
        results = st.session_state.get("detect_results", [])
        if not results:
            st.caption("⚠️ 未在环境变量或 .env 中找到任何 API Key。请手动填入。")
        else:
            st.caption(f"找到 {len(results)} 个候选配置，点「选用」自动填好：")
            for i, cfg in enumerate(results):
                with st.container():
                    st.markdown(
                        f"`{cfg['provider']}` · {cfg['source']}\n"
                        f"`{cfg['key_preview']}`"
                    )
                    if st.button("✅ 选用", key=f"pick_{i}", use_container_width=True):
                        _apply_config(cfg)
                        st.session_state.detect_shown = False
                        st.rerun()
        if st.button("✕ 收起", key="close_detect", use_container_width=True):
            st.session_state.detect_shown = False
            st.rerun()

    st.divider()

    # ── 手动输入区（自动识别） ──
    api_key = st.text_input(
        "API Key",
        type="password",
        value=st.session_state.get("_picked_key", os.getenv("OPENAI_API_KEY", "")),
        placeholder="sk-...（支持 DeepSeek / OpenAI / Qwen）",
        help="不会存储。填入后自动识别服务商；点上方「🔍 自动检测」可从环境一键选用。",
        key="_api_key_input",
    )

    # Key 实时识别（基于当前输入）
    if api_key and api_key.strip().startswith("sk-"):
        detected = detect_provider_from_key(api_key)
        if detected and detected["confidence"] != "低":
            badge = f"🟢 {detected['name']}（{detected['confidence']}置信度）"
            st.caption(f"已识别：**{badge}**")
        elif detected:
            st.caption(f"⚠️ {detected['name']}")

    base_url = st.text_input(
        "API Base URL",
        value=st.session_state.get("_picked_url", os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")),
        help="DeepSeek: https://api.deepseek.com/v1 · OpenAI: https://api.openai.com/v1",
        key="_base_url_input",
    )
    model = st.text_input(
        "模型",
        value=st.session_state.get("_picked_model", "deepseek-chat"),
        help="如 deepseek-chat / gpt-4o-mini / qwen-plus",
        key="_model_input",
    )

    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    if base_url:
        os.environ["OPENAI_BASE_URL"] = base_url

    # 清空"已选用"标记（下次再选会覆盖）
    for k in ("_picked_key", "_picked_url", "_picked_model"):
        st.session_state.pop(k, None)

    st.divider()
    st.markdown("""
    **使用说明：**
    1. 点「🔍 自动检测」一键选用环境 Key
    2. 或手动填入 API Key（自动识别服务商）
    3. 上传 CSV/Excel 文件
    4. 点击「开始分析」
    5. 查看 Agent 逐步决策过程
    6. 下载分析报告（MD/HTML/PDF/Word）
    """)

    st.divider()
    st.caption(f"Python {sys.version.split()[0]} · LangGraph")

# ── 主体：上传区域 ──
col1, col2 = st.columns([3, 1])
with col1:
    uploaded = st.file_uploader(
        "上传数据文件",
        type=["csv", "xlsx", "xls"],
        help="支持 CSV（逗号/制表符分隔）和 Excel 格式",
        label_visibility="collapsed",
        key="uploaded_file",
    )
with col2:
    analyze_btn = st.button("🚀 开始分析", type="primary", use_container_width=True, disabled=not uploaded)

# ── session_state 初始化（关键：解决"点了就跳回没分析"的状态丢失问题） ──
# Streamlit 每次交互都会从头重跑脚本；如果不把分析结果存进 session_state，
# 下一次脚本跑时 analyze_btn 又会变 False，导致整个结果区消失。
for _k, _v in {
    "analysis_done": False,        # 分析是否完成
    "uploaded_name": "",            # 当前文件标识（用于检测新文件）
    "final_report": "",             # 报告文本
    "chart_paths": [],              # 图表绝对路径清单
    "analysis_log": [],             # 完整分析日志
    "cleaned_df": None,             # 清洗后数据
    "issues_summary": None,         # 加载时发现的问题数
    "quality": None,                # 数据质量评分
    "chat_history": [],             # 追问历史
    "tmp_path": "",                 # 临时文件路径
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── 检测上传了新文件 → 重置分析结果 ──
if uploaded and uploaded.name != st.session_state.uploaded_name:
    st.session_state.analysis_done = False
    st.session_state.uploaded_name = uploaded.name
    st.session_state.final_report = ""
    st.session_state.chart_paths = []
    st.session_state.analysis_log = []
    st.session_state.cleaned_df = None
    st.session_state.issues_summary = None
    st.session_state.quality = None
    st.session_state.chat_history = []

# ── 数据预览（始终在文件上传后展示） ──
if uploaded:
    st.divider()
    st.subheader("📋 数据预览")

    df = None
    used_enc = None
    try:
        if uploaded.name.endswith(".csv"):
            raw_bytes = uploaded.read()
            # 优先 UTF-8（容错解码坏字节 → 替换符，而非崩溃），其次 GBK/GB18030；
            # 绝不使用 latin-1（会把 UTF-8 字节当 Latin-1 解码成 'å§å' 整列乱码）
            for enc in ["utf-8", "gbk", "gb18030"]:
                try:
                    txt = raw_bytes.decode(enc, errors="replace")
                except Exception:
                    continue
                try:
                    d = pd.read_csv(io.StringIO(txt))
                except Exception:
                    continue
                if len(d.columns) > 1:
                    df = d
                    used_enc = enc
                    break
            if df is not None:
                st.caption(f"编码: {used_enc} · {df.shape[0]} 行 × {df.shape[1]} 列")
        else:
            df = pd.read_excel(uploaded)
            st.caption(f"{df.shape[0]} 行 × {df.shape[1]} 列")
    except Exception as e:
        st.error(f"文件读取失败: {e}")
        st.stop()

    if df is None:
        st.error("无法解析该文件，请检查格式（UTF-8/GBK编码的CSV或Excel）")
        st.stop()

    # ── 智能数据源：上传文件结构性损坏时，自动改用 data/clean/ 中的干净数据 ──
    switched = False
    if _is_structurally_damaged(df):
        clean = _find_clean_source()
        if clean:
            df = read_df(clean)
            switched = True
            st.info(
                f"⚠️ 检测到上传文件结构性损坏（大量无用列/乱码表头），"
                f"已自动改用干净数据 `{os.path.basename(clean)}` 进行分析。"
            )
            st.caption(f"已切换数据源 · {df.shape[0]} 行 × {df.shape[1]} 列")

    st.dataframe(df.head(10), use_container_width=True, hide_index=True)

    # 保存临时文件（统一 UTF-8 编码，避免乱码）
    tmp_path = os.path.join(os.path.dirname(__file__), "_tmp_upload.csv")
    df.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    st.session_state.tmp_path = tmp_path
    st.session_state._current_df = df  # 暂存当前 df（供分析块和回退用）


# ── 分析流程（点击「开始分析」时执行一次，结果写入 session_state） ──
if uploaded and analyze_btn and not st.session_state.analysis_done:
    if not api_key:
        st.error("请先在左侧填入 API Key")
        st.stop()

    df = st.session_state._current_df
    tmp_path = st.session_state.tmp_path

    st.divider()
    st.subheader("🧠 Agent 分析过程")

    # 进度容器
    progress_bar = st.progress(0, text="初始化中...")
    step_log_container = st.container()

    # 第一步：数据加载
    with step_log_container:
        with st.spinner("📂 加载数据..."):
            data_json = inspect_data(tmp_path)
            issues = find_issues(df)

        st.markdown(
            f'<div class="step-box step-load">'
            f'<strong>📂 数据加载完成</strong><br>'
            f'{df.shape[0]} 行 × {df.shape[1]} 列 · '
            f'发现 {issues["problem_count"]} 个问题'
            f'</div>',
            unsafe_allow_html=True,
        )

        if issues["problem_count"] > 0:
            with st.expander(f"🔍 查看 {issues['problem_count']} 个问题", expanded=False):
                for p in issues["problems"]:
                    sev = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(p.get("severity", ""), "⚪")
                    st.markdown(f"{sev} **{p.get('type','?')}**: {p.get('detail','')}")

    progress_bar.progress(20, text="数据已加载")

    # 第二步：运行 Agent
    agent = create_agent()
    cfg = {"configurable": {"thread_id": f"ui-{uploaded.name}"}}

    initial: dict = {  # type: ignore[typeddict-item]
        "filepath": tmp_path,
        "df_json": _set_df(df),
        "data_json": data_json,
        "issues_json": json.dumps(_safe(issues), ensure_ascii=False),
        "analysis_log": [{
            "step_num": 0, "step": "load",
            "summary": f"加载完成: {df.shape[0]}行×{df.shape[1]}列",
            "result": {"shape": list(df.shape), "columns": list(df.columns)},
        }],
        "step_count": 0,
        "next_action": "clean" if issues["problem_count"] > 0 else "stats",
        "final_report": "",
        "chart_files": [],
        "messages": [],
    }

    step_map = {
        "load": "📂", "clean": "🧹", "stats": "🔬",
        "viz": "📈", "report": "📝", "analyze": "🧠",
    }
    color_map = {
        "load": "step-load", "clean": "step-clean", "stats": "step-stats",
        "viz": "step-viz", "report": "step-report", "analyze": "step-analyze",
    }

    step_num = 0
    step_names_done = set()
    final_report = ""
    chart_files_state = []
    analysis_log_all = []
    quality = None

    try:
        for event in agent.stream(initial, cfg):
            step_num += 1
            for node_name, node_output in event.items():
                step_names_done.add(node_name)

                log_entries = node_output.get("analysis_log", [])
                analysis_log_all.extend(log_entries)
                summary = log_entries[0].get("summary", "") if log_entries else ""

                with step_log_container:
                    st.markdown(
                        f'<div class="step-box {color_map.get(node_name, "")}">'
                        f'<strong>{step_map.get(node_name, "→")} {node_name}</strong>'
                        f'{(" — " + summary) if summary else ""}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                if node_name == "report":
                    final_report = node_output.get("final_report", "")
                    chart_files_state = node_output.get("chart_files", [])

            total_steps = 6
            pct = min(95, int(len(step_names_done) / total_steps * 100))
            progress_bar.progress(pct, text=f"步骤 {step_num}...")

        final_state = agent.get_state(cfg)
        if not final_report:
            final_report = final_state.values.get("final_report", "")
        if not chart_files_state:
            chart_files_state = final_state.values.get("chart_files", [])

        # 数据质量评分
        try:
            from tools.quality import quality_score
            quality = quality_score(df)
        except Exception:
            quality = None

        # 清洗后 df
        df_json = final_state.values.get("df_json", "")
        if df_json:
            try:
                cleaned_df = pd.read_json(io.StringIO(df_json), orient="split")
            except Exception:
                cleaned_df = df
        else:
            cleaned_df = df

        # ── 关键：把所有结果写入 session_state，让后续交互（追问、切 tab）不会丢 ──
        st.session_state.analysis_done = True
        st.session_state.final_report = final_report
        st.session_state.chart_paths = list(chart_files_state)
        # 补充扫描 outputs/（保证没漏图）
        try:
            ensure_outputs_dir()
            for f in sorted(os.listdir(OUTPUTS_DIR)):
                if f.startswith("chart_") and f.endswith(".png"):
                    p = os.path.join(OUTPUTS_DIR, f)
                    if p not in st.session_state.chart_paths:
                        st.session_state.chart_paths.append(p)
        except Exception:
            pass
        st.session_state.analysis_log = analysis_log_all
        st.session_state.cleaned_df = cleaned_df
        st.session_state.issues_summary = issues
        st.session_state.quality = quality

        progress_bar.progress(100, text="分析完成 ✅")

    except Exception as e:
        st.error(f"Agent 执行出错: {e}")
        st.stop()


# ── 持久化结果展示区（关键修复：独立于 analyze_btn，无论用户点什么都还在） ──
if uploaded and st.session_state.analysis_done:
    final_report = st.session_state.final_report
    chart_paths = list(st.session_state.chart_paths)
    analysis_log_all = list(st.session_state.analysis_log)
    cleaned_df = st.session_state.cleaned_df
    issues = st.session_state.issues_summary
    quality = st.session_state.quality
    tmp_path = st.session_state.tmp_path

    # 结果指标（亮点展示）
    st.divider()
    st.subheader("📊 分析指标")
    try:
        if quality is None and cleaned_df is not None:
            from tools.quality import quality_score
            quality = quality_score(cleaned_df)
        if quality:
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("数据质量评分", f"{quality['score']}",
                          quality_label(quality['score']))
            with c2:
                qdf = cleaned_df if cleaned_df is not None else df
                st.metric("数据规模", f"{qdf.shape[0]}×{qdf.shape[1]}")
            with c3:
                n_tests = sum(1 for e in analysis_log_all if e.get("step") == "stats")
                st.metric("统计检验", f"{n_tests} 步")
            with c4:
                st.metric("图表", f"{len(chart_paths)} 张")
    except Exception:
        pass

    # 分析过程回放
    st.divider()
    st.subheader("🧠 分析过程")
    step_map2 = {
        "load": "📂", "clean": "🧹", "stats": "🔬",
        "viz": "📈", "report": "📝", "analyze": "🧠",
    }
    color_map2 = {
        "load": "step-load", "clean": "step-clean", "stats": "step-stats",
        "viz": "step-viz", "report": "step-report", "analyze": "step-analyze",
    }
    for entry in analysis_log_all:
        step_name = entry.get("step", "?")
        summary = entry.get("summary", "")
        st.markdown(
            f'<div class="step-box {color_map2.get(step_name, "")}">'
            f'<strong>{step_map2.get(step_name, "→")} {step_name}</strong>'
            f'{(" — " + summary) if summary else ""}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # 报告区
    st.divider()
    st.subheader("📝 分析报告")

    tab1, tab2, tab3 = st.tabs(["📄 报告预览", "📊 图表", "📥 下载"])

    with tab1:
        if final_report:
            _render_report_with_images(final_report, chart_paths)
        else:
            st.warning("未生成报告内容")

    with tab2:
        if chart_paths:
            cols = st.columns(min(3, len(chart_paths)))
            for i, p in enumerate(chart_paths):
                with cols[i % len(cols)]:
                    try:
                        st.image(p, caption=os.path.basename(p), use_container_width=True)
                    except Exception as e:
                        st.warning(f"图片加载失败: {os.path.basename(p)} ({e})")
        else:
            st.info("未生成图表")

    with tab3:
        _render_download_panel(final_report, chart_paths)

    # ── 追问区（持久化在 session_state.chat_history） ──
    st.divider()
    st.subheader("💬 追问数据")
    st.caption("基于分析结果继续追问，Agent 会结合数据和报告回答你的问题")

    # 显示对话历史
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 输入框
    user_q = st.chat_input("例如：只看华东的数据 / 为什么家居用品利润率高？/ 帮我分析Q4趋势")
    if user_q:
        st.session_state.chat_history.append({"role": "user", "content": user_q})
        with st.chat_message("user"):
            st.markdown(user_q)

        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                try:
                    answer = answer_question(
                        filepath=tmp_path,
                        analysis_log=analysis_log_all,
                        data_json="",
                        final_report=final_report,
                        question=user_q,
                        df=cleaned_df,
                    )
                    st.markdown(answer)
                    st.session_state.chat_history.append({"role": "assistant", "content": answer})
                except Exception as e:
                    err_msg = f"回答失败: {e}"
                    st.error(err_msg)
                    st.session_state.chat_history.append({"role": "assistant", "content": err_msg})

    # 清理临时文件（仅在当前文件与上次不同 / 用户主动清理时做；这里跳过避免误删）


# ── 初始状态：未上传文件且未分析过时显示功能介绍 ──
if not uploaded and not st.session_state.analysis_done:
    st.divider()
    st.subheader("✨ 核心能力")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown("""
        **🔍 智能加载**
        - 自动编码检测
        - 分隔符识别
        - CSV / Excel 支持
        """)
    with c2:
        st.markdown("""
        **🧹 AI 驱动清洗**
        - LLM 智能决策
        - 缺失值自动填充
        - 异常值智能处理
        """)
    with c3:
        st.markdown("""
        **📊 自动统计**
        - 正态性检验
        - 自动选 t-test/M-W
        - 效应量计算
        """)
    with c4:
        st.markdown("""
        **📈 可视化 + 报告**
        - 自动选图表类型
        - Markdown 报告
        - LLM 业务洞察
        """)

    st.divider()
    st.info("👆 上传 CSV 或 Excel 文件，填入 API Key，点击「开始分析」即可体验！")


# ── 若已分析但当前没上传文件，给个"重新分析"提示（避免误以为结果丢了） ──
elif st.session_state.analysis_done and not uploaded:
    st.divider()
    st.subheader("✅ 上次分析结果已保留")
    st.info("👆 请重新上传文件后点击「🚀 开始分析」以分析新数据。")
