# 数据分析 Agent — 代码审查与改进建议

> 审查范围：`agent.py`(决策引擎) · `tools/*`(5 个工具) · `app.py`(Web UI) · `run.py`(启动器) · `tests/*` · `skills/` · `deploy/` · 数据/配置文件
> 审查时间：2026-07-18
> 结论：架构思路清晰（LangGraph 动态决策 + LLM 驱动清洗/统计/可视化），但**决策循环、编码一致性、依赖/部署、密钥管理、测试覆盖**存在必须修的硬伤。下面按优先级给出。

---

## 0. 总体印象（优点）

- **架构分层合理**：决策引擎(`agent.py`) 与工具层(`tools/`) 解耦，每个工具单一职责，可读性好。
- **清洗/统计思路专业**：IQR 异常值、自动 t-test / Mann-Whitney 选择、Cohen's d 效应量、缺失率分级，超出一般 demo。
- **`_safe()` 序列化守卫**对 NaN/Inf/numpy 类型做了防护，细节到位。
- **测试意识好**：cleaner / loader / statistician 都有单测，且专门准备了 GBK fixture。
- **部署完备**：Dockerfile + docker-compose + 中文字体，体感专业。

---

## 🔴 P0 — 必须修（会直接导致功能失败或安全风险）

### P0-1. 决策循环可能死循环，且"强制规则"只是 prompt 文字，代码不兜底
**位置**：`agent.py` → `analyze_node()`（约 L99–191）+ `clean_node()`
**问题**：
- `clean_node` 里 `find_issues()` 会**把任意缺失值（哪怕 0.08%）都算作 problem**（cleaner.py L45–56），所以 `problem_count` 几乎不会降到 0。
- `analyze_node` 在 prompt 里写了"清洗≥2 强制 stats"，但 **解析完 LLM 返回后，代码只强制了 `step >= MAX_STEPS → report`（L177）**。如果 LLM 在 `clean_count>=2` 时仍返回 `clean`，代码照单全收 → 反复清洗同一低严重度问题。
- 这在现有 `analysis_report.md` 里已被坐实：业务洞察段明确写着 *"系统反复尝试清洗同一低严重度问题，但未进行任何统计分析"*。最终是靠 `MAX_STEPS=12` 硬截断才结束。

**修复（建议，二选一）**：
1. 轻量版——在 `analyze_node` 解析后加代码兜底，覆盖 prompt 里的强制规则：
```python
counts = _tally(state)            # 统计 clean/stats/viz/report 完成次数
forced = None
if counts["clean"] >= 2 and counts["stats"] == 0:
    forced = "stats"
elif counts["stats"] >= 1 and counts["viz"] == 0:
    forced = "viz"
elif counts["viz"] >= 1:
    forced = "report"
if forced:
    action = forced
```
2. 彻底版——把 `analyze` 改成**确定性状态机**，LLM 只负责"这一步内部怎么做"（选哪些列清洗、做哪些检验），不再让它决定"下一步去哪"。这样既能保留"动态决策"卖点，又能 100% 保证终止。

### P0-2. 编码处理不一致 → 中文乱码（已复现）
**位置**：`loader.py load_data()`（有编码检测，但没人用）vs `agent.py`/`loader.inspect_data`/`app.py` 各自读文件
**问题**：
- 真正带编码检测的函数是 `load_data()`（loader.py L16–53，已支持 utf-8/gbk/gb2312/latin-1/Excel），但 **整个 agent 流程从未调用它**。`inspect_data()`、所有 `pd.read_csv(fp, on_bad_lines="warn")` 都用默认 UTF-8，且**不传 encoding**。
- `app.py` 上传时用一套独立的编码探测（app.py L109–118），但 agent 重新读 `_tmp_upload.csv` 时又走默认 UTF-8，两条路径脱节。
- 结果：非 UTF-8 来源或探测失败时就出现 `å§å` 这类乱码。**当前 `analysis_report.md` 第 8 行字段名就是乱码**，已实锤。
- 实测数据：`data/raw/data.csv` 为 UTF-8；`tests/fixtures/gbk_sample.csv` 为 GBK。混合来源下必然踩坑。

**修复**：抽一个唯一入口 `_read_df(fp)`（复用 `load_data` 的探测逻辑 + 显式 encoding），让 `inspect_data`、`load_node`、`_get_df` 兜底、以及 `app.py` 全部调用它；写文件一律显式 `encoding="utf-8"`。不要让 `load_data` 成为死代码。

### P0-3. 真实 API Key 以明文落在工作区
**位置**：`.env`（根目录），内容为 `OPENAI_API_KEY=sk-0c8a19f796...`
**问题**：虽已被 `.gitignore` 正确忽略（这点做得对，不会误提交），但**明文密钥长期躺在磁盘上**仍是风险，且一旦换机/备份/截图就可能泄露。
**修复**：
- 立即去 DeepSeek 控制台**吊销并轮换**该 key（它已暴露在本机）。
- 考虑用环境变量或密钥管理器注入，而不是落盘 `.env`；若必须落盘，至少 `.env` 权限设为仅本人可读。
- CI/协作时不要共享同一把 key。

### P0-4. Docker 镜像缺 streamlit → `web` 服务起不来
**位置**：`requirements.txt`（streamlit 被注释，L9–10）vs `deploy/docker-compose.yml` `web` 服务 `entrypoint: streamlit run app.py`
**问题**：Dockerfile 只 `pip install -r requirements.txt`（没有 streamlit），但 compose 的 `web` 服务入口是 `streamlit run app.py` → 容器内 `streamlit: command not found`，**`docker compose up web` 直接崩**。
**修复**：把 `streamlit>=1.28.0` 加回 `requirements.txt`（或 Dockerfile 单独装），保持 CLI 与 Web 依赖一致。

---

## 🟠 P1 — 重要（影响正确性/健壮性/可维护性）

### P1-1. 测试覆盖有"假象"：核心决策逻辑零测试
**现状**：README 宣称 "26 tests, 100% pass"。函数数量我数过确实约 26 个，但——
- `test_agent.py` 只测了 `_safe` / `_filter_df` / `_set_df`/`_get_df` 等**辅助函数**，**完全没有测 LangGraph 路由、clean→stats 转换、循环终止**。
- 也就是说 README 主打的"动态决策"恰恰是测试盲区——而 P0-1 的循环 bug 正是这里。
- `test_statistician.py::test_auto_select` 用 `np.random.normal` **未设种子** → 偶发波动（flaky）。
- `test_check_assumptions_normal` 函数体只有 `pass`，**没有任何断言**，是无效测试。
- `test_load_gbk_encoding` 只断言 `shape>0`，即使编码探测悄悄回退成别的也能过。

**修复**：
- 新增"路由/状态机"单测：构造 `analysis_log` 直接喂给 `route_action` / `analyze_node` 的计数逻辑，断言 clean≥2 后必走 stats、viz 后必走 report、MAX_STEPS 截断。
- `test_auto_select` 加 `np.random.seed(42)`。
- 给 `test_check_assumptions_normal` 补真实断言；GBK 测试断言 `r["encoding"]=="gbk"`。
- 考虑用 `langgraph` 的 `compile` + 伪造 LLM（返回固定 JSON）做一次端到端图测试。

### P1-2. 统计分析太"窄"且用了已弃用 API
**位置**：`agent.py stats_node()`（L362–389）
**问题**：
- 只拿**前 2 个分类列 × 前 2 个数值列**做两两比较（`cats[:2]` / `nums[:2]`），会漏掉真正有意思的关系。
- `df.groupby(cat)[num].apply(list)` 在 pandas 2.0+ 已**弃用**（含 grouping 列告警，未来版本会报错），应改用 `groupby(cat)[num].apply(list, include_groups=False)` 或直接 `df.groupby(cat)[num].apply(list)` 的推荐写法，或 `df.groupby(cat)[num].apply(lambda s: s.tolist())`。
- 没有**多重比较校正**（跑很多组检验会放大假阳性），对"统计"卖点是个短板。

**修复**：让 LLM（或规则）选出有业务意义的"分类×数值"组合（如按相关性/方差筛选 top-N），而不是硬取前 2 个；加 Bonferroni/Holm 校正或至少提示 p 值未校正。

### P1-3. 追问（多轮对话）基本是"空壳"
**位置**：`agent.py _interactive_loop()` / `app.py` 追问块
**问题**：
- CLI：追问时 `_interactive_loop` 用 `pd.read_csv(filepath)` 重新读**原始文件**，而不是清洗后的 DataFrame → 追问基于脏数据，且与报告结论不一致。
- `app.py` 追问调用 `answer_question(..., analysis_log=st.session_state.get("analysis_log", []))`，但 `st.session_state.analysis_log` **全程从未被赋值**（L328 只在聊天块之后初始化为空列表），所以 Web 端追问**拿不到任何分析上下文**。
- `_filter_df()`（agent.py L542–569）只认硬编码的"华东/华南/华北/电子产品/家居/家电"，换份数据就失效，且该函数**当前根本没被调用**。

**修复**：把清洗后的 `df` 和分析日志真正传进 `answer_question`；用 LLM/工具做自然语言筛选代替硬编码；CLI 追问用 agent state 里的 `df_json` 还原 DataFrame。

### P1-4. LLM 返回 JSON 解析失败 → 直接跳到 report
**位置**：`agent.py analyze_node()`（L166–178）
**问题**：`json.loads` 失败时 `d = {"next_action":"report", ...}` ——一旦模型输出带多余文字或格式飘了，**直接跳过剩余分析步骤**，而不是重试或降级。对弱模型/长输出尤其危险。
**修复**：
- 优先用结构化输出：`llm.with_structured_output(...)`（Pydantic）或 `response_format={"type":"json_object"}`。
- 保留降级：解析失败先尝试剥离 ``` 围栏（已有），再失败则**重试一次**，仍失败才保守地按"剩余步骤最少"推进，而不是无脑 report。

### P1-5. 可视化中文在 Docker/Linux 下会"豆腐块"
**位置**：`tools/visualizer.py` L14 字体设置
**问题**：`font.sans-serif = ["Microsoft YaHei","SimHei",...]` 在 Windows 有，但 Dockerfile 装的是 `fonts-wqy-microhei`（文泉驿微米黑），名字不匹配 → 图表中文标题变方框。
**修复**：字体列表加上 `"WenQuanYi Micro Hei"`，或运行时探测可用中文字体。

### P1-6. `create_llm()` 每次节点都 new 一个客户端
**位置**：`agent.py` L91 / 被 4 处调用
**问题**：`analyze_node`/`clean_node`/`report_node`/`answer_question` 各自 `create_llm()`，重复建连。量小无所谓，但属于明显浪费。
**修复**：模块级缓存单例（如 `functools.lru_cache` 或全局变量），或显式传 `llm` 进节点。

---

## 🟡 P2 — 打磨项（体验/规范）

1. **多重比较无校正**（见 P1-2）：报告里至少标注"p 值未做多重比较校正"。
2. **图表/报告产物路径**：`create_chart` 写固定 `chart_bar.png`/`chart_box.png`，`report_node` 写固定 `analysis_report.md`（CWD 相对路径）。多份数据连续跑会互相覆盖，且报告里用相对路径引用图片，换目录打开就裂图。建议输出到带时间戳/文件名的目录，或把图片 base64 内嵌进报告。
3. **`skills/`、`README.md`、`demos/` 三套文档严重冗余**：SKILL.md 描述的还是"v2.0 LangGraph"架构，和 `README.md` 重复；`demos/*.md` 又是同样的 5 段。维护成本高、易失同步。建议以 README 为单一事实源，SKILL.md 只保留"如何作为 WorkBuddy 技能调用"。
4. **`run.py` 品牌不一致**：标题打印 `⚔️ 星见 · 数据分析`，与全局 "Data Analysis Agent" 对不上，疑似旧项目残留。
5. **缺根目录 LICENSE**：README 写 MIT，但只有 `deploy/LICENSE`，根目录没有，GitHub 徽章对应的 LICENSE 文件缺失。
6. **Docker CLI 入口依赖 TTY**：`agent.py __main__` 跑完 `analyze()` 后进入 `_interactive_loop` 的 `input()`，容器内无 TTY 会立刻 `EOFError` 退出。建议检测非交互环境时跳过交互循环。
7. **错误处理粒度**：`report_node` 等节点未对 LLM 调用做 try/except，单点 LLM 超时/限流会让整次运行半途崩溃（app.py 外层有兜底，CLI `analyze()` 没有）。
8. **token 成本**：`analyze_node` 每步都塞 `data_json[:3000]` + 历史，对 6198×76 的大表会迅速膨胀。可对大表只传 `describe` 摘要 + 列名，省 token。

---

## 优先级路线图

| 优先级 | 项 | 影响 | 工作量 |
|--------|----|------|--------|
| P0-1 | 决策循环/终止兜底 | 分析可能卡死、产不出统计 | 中 |
| P0-2 | 统一编码入口 | 中文乱码（已复现） | 小 |
| P0-3 | 轮换泄露的 API Key | 安全风险 | 小（运维） |
| P0-4 | Docker 补 streamlit | Web 部署不可用 | 小 |
| P1-1 | 补决策逻辑测试 | 回归保护 | 中 |
| P1-2 | 统计更宽 + 修弃用 API | 正确性/未来崩溃 | 中 |
| P1-3 | 修复追问上下文 | 核心功能残缺 | 中 |
| P1-4 | 结构化 LLM 输出 | 健壮性 | 小 |
| P1-5 | Docker 中文字体 | 图表可读性 | 小 |
| P1-6 | LLM 客户端缓存 | 性能 | 小 |

---

## 我建议的下一步

最划算的修复顺序：**P0-2（编码，半小时）→ P0-4（Docker，5 分钟）→ P0-1（循环兜底，1 小时）→ P1-3（追问，1 小时）→ P1-1（补测试，2 小时）**。这 5 项覆盖了"跑不起来/跑不通/跑不对"的全部硬伤。

需要的话，我可以直接动手改 `agent.py` / `tools/` / `requirements.txt` / `app.py` 并补上决策逻辑的单元测试。你点头我就开干。

---

## ✅ 已修复（2026-07-18）

| 项 | 文件 | 改动 |
|----|------|------|
| P0-1 决策循环 | `agent.py` | 新增 `_decide_action()` / `_tally()`：代码层强制路由（load→clean→stats→viz→report），`analyze_node` 调用它兜底；LLM 的 JSON 解析改用 `_extract_json()`（兼容 ``` 围栏 + 正则兜底）。**已写单测验证，含"LLM 一直返回 clean 也不死循环"的模拟（9/9 通过）**。 |
| P0-2 编码乱码 | `tools/loader.py` + `agent.py` | 新增 `read_df()` / `detect_encoding_and_sep()`；`inspect_data()` 与 `load_node` / `_get_df` 全部改走统一编码探测，不再用默认 UTF-8 裸读。 |
| P0-4 Docker | `requirements.txt` | 取消注释 `streamlit>=1.28.0`，`docker compose up web` 不再因缺命令崩溃。 |
| P1-3 追问上下文 | `agent.py` + `app.py` | CLI 追问改用 agent 最终状态的清洗后 DataFrame（不再裸读原文件）；Web 端把 `analysis_log` 与 `cleaned_df` 存入 `session_state` 并传给 `answer_question`。 |
| P1-1 测试 | `tests/test_routing.py` | 新增 8 条路由/循环终止单测（无需 LLM）。 |
| P1-2 统计 | `agent.py` | `stats_node` 修复 pandas 2 弃用的 `groupby.apply(list)`，改为 `.tolist()`；组合放宽到 (分类×数值) 前 3×前 3、上限 6 组，并 `dropna` 防 NaN 进 scipy。 |
| P1-5 字体 | `tools/visualizer.py` | 中文字体列表加入 `WenQuanYi Micro Hei`（Docker 不再豆腐块）。 |
| P1-6 LLM 缓存 | `agent.py` | `create_llm()` 改为模块级单例缓存，不再每节点新建客户端。 |

> **未处理 / 需你操作**：
> - **P0-3 密钥**：`.env` 里的真实 DeepSeek key 仍建议去控制台**吊销轮换**（代码未改动该文件，避免破坏你的本地运行）。
> - P1-4 结构化输出、P2 各项（产物路径/文档冗余/品牌/LICENSE/TTY/错误处理）按优先级可后续跟进。
> - 本地运行前请 `pip install -r requirements.txt`（含 streamlit），并 `python -m pytest tests/ -v` 跑一遍（本机已装依赖时）。
