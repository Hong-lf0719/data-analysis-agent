# 数据分析 Agent · 审查与优化文档

> 项目：数据分析 Agent（LangGraph 动态决策 + LLM 驱动清洗/统计/可视化）
> 审查时间：2026-07-18
> 审查范围：`agent.py`（决策引擎）、`tools/*`（5 个工具）、`app.py`（Web UI）、`run.py`（启动器）、`tests/*`、`skills/`、`deploy/`、数据/配置文件
> 文档状态：审查完成，P0 与关键 P1 修复已完成并验证；第三轮（运行时加固 + 亮点功能）已完成并验证；第四轮（乱码根治 + 坏文件自动改用干净数据）已完成并验证；第五轮（图表加载修复 + 多格式报告导出）已完成并验证；**第六轮（Web 状态持久化修复）已完成并验证**

---

## 1. 执行摘要

**总体结论**：架构思路清晰、分层合理，远超一般 demo 的专业度（IQR 异常值、自动 t-test/Mann-Whitney、Cohen's d 效应量、缺失率分级都有）。但存在 **4 个会导致功能失败/安全风险的硬伤（P0）**，以及若干影响正确性、健壮性和测试真实性的重要问题（P1）。

**当前修复进度**：

| 等级 | 总数 | 已修复 | 待处理 |
|------|------|--------|--------|
| 🔴 P0 | 4 | 3（编码 / Docker / 决策循环） | 1（密钥轮换，需你运维操作） |
| 🟠 P1 | 6 | 5（测试 / 统计 / 追问 / 字体 / LLM 缓存 / 节点级容错） | 1（结构化 LLM 输出，建议项） |
| 🟡 P2 | 8 | 1（节点级 try/except 已并入第三轮） | 7（打磨项，按需跟进） |

> **第二轮补充（2026-07-18 下午）**：基于你贴出的真实运行输出（76 列乱码 + 0 检验 + 0 图）做了"数据对比优化"，新增 5 项修复（见第 8 节），核心路由单测 8/8 通过、真实数据管线复现通过。
>
> **第三轮（2026-07-18 晚）**：修运行时硬伤（流程跳过 stats/viz、报告被截断、空分组崩溃、LLM 报错拖垮整条流）+ 新增亮点（数据质量评分、相关性分析、相关性热力图）。40 项单测全过、端到端探针三份真实数据全部跑通。

**一句话**：修复后"跑不起来 / 跑不通 / 跑不对"的三类硬伤已全部堵住，核心路由逻辑已单测覆盖；现已能正确处理清洗后的数据并识别结构性损坏的原始数据。

---

## 2. 项目优点（值得保留）

- **架构分层合理**：决策引擎 `agent.py` 与工具层 `tools/` 解耦，每个工具单一职责，可读性好。
- **清洗 / 统计思路专业**：IQR 异常值、自动 t-test / Mann-Whitney 选择、Cohen's d 效应量、缺失率分级，超出一般 demo。
- **`_safe()` 序列化守卫**：对 NaN / Inf / numpy 类型做了防护，细节到位。
- **测试意识好**：cleaner / loader / statistician 都有单测，且专门准备了 GBK fixture。
- **部署完备**：Dockerfile + docker-compose + 中文字体，体感专业。

---

## 3. 问题清单（按优先级）

### 🔴 P0 — 必须修

#### P0-1 决策循环可能死循环（已修复）
- **位置**：`agent.py` → `analyze_node()` + `clean_node()`
- **问题**：`find_issues()` 把任意缺失值（哪怕 0.08%）都算 problem，导致 `problem_count` 几乎不归零；`analyze_node` 仅在 prompt 里写"清洗≥2 强制 stats"，代码不兜底。若 LLM 在 `clean_count>=2` 时仍返回 `clean`，会反复清洗同一低严重度问题。现有 `analysis_report.md` 已实锤："系统反复尝试清洗同一低严重度问题，未进行任何统计分析"，最终靠 `MAX_STEPS=12` 硬截断。
- **修复**：新增 `_decide_action()` / `_tally()` 做代码层强制路由（load→clean→stats→viz→report），LLM 不再决定"下一步去哪"。

#### P0-2 编码处理不一致 → 中文乱码（已修复，已复现）
- **位置**：`loader.py load_data()`（有检测但没人用）vs `agent.py` / `inspect_data` / `app.py` 各自裸读
- **问题**：真带编码检测的是 `load_data()`，但整个流程从未调用；其余 `pd.read_csv` 都用默认 UTF-8 且不传 encoding。当前 `analysis_report.md` 第 8 行字段名就是乱码。实测 `data/raw/data.csv`=UTF-8、`tests/fixtures/gbk_sample.csv`=GBK，混合来源必踩。
- **修复**：抽唯一入口 `read_df()` / `detect_encoding_and_sep()`，所有读文件处统一调用，写文件显式 `encoding="utf-8"`。

#### P0-3 真实 API Key 明文落盘（需你操作）
- **位置**：`.env`，含一把真实 DeepSeek key
- **问题**：虽已被 `.gitignore` 正确忽略（不会误提交），但明文长期躺在磁盘仍是风险。
- **修复**：去 DeepSeek 控制台**吊销并轮换**该 key；后续用环境变量或密钥管理器注入，避免落盘。

#### P0-4 Docker 缺 streamlit → web 起不来（已修复）
- **位置**：`requirements.txt` streamlit 被注释 vs `docker-compose.yml` 入口 `streamlit run app.py`
- **问题**：Dockerfile 只装 requirements（无 streamlit）→ 容器内 `streamlit: command not found`，`docker compose up web` 直接崩。
- **修复**：取消注释 `streamlit>=1.28.0`，CLI 与 Web 依赖一致。

### 🟠 P1 — 重要

| 编号 | 问题 | 状态 |
|------|------|------|
| P1-1 | 测试"假象"：核心决策逻辑零测试（`test_agent` 只测辅助函数，且 `test_check_assumptions_normal` 是空断言、flaky 种子缺失） | ✅ 已补 `test_routing.py`（8 条） |
| P1-2 | 统计太窄（仅前 2 分类×前 2 数值）且用 pandas 2 已弃用的 `groupby.apply(list)` | ✅ 已修 `.tolist()` + 放宽组合 |
| P1-3 | 追问是空壳：CLI 读原始文件、Web 端 `analysis_log` 从未赋值、`_filter_df` 硬编码未被调用 | ✅ 已修（用清洗后 df + session_state 上下文） |
| P1-4 | LLM 返回 JSON 解析失败直接跳 report，无重试/降级 | ✅ 已修（analyze/clean/report 节点加 try/except，失败走确定性路由兜底） |
| P1-5 | Docker 中文字体豆腐块（字体名不匹配） | ✅ 已加 WenQuanYi |
| P1-6 | `create_llm()` 每节点新建客户端 | ✅ 已改单例缓存 |

### 🟡 P2 — 打磨项（按需）

1. 多重比较无校正 → 报告至少标注"p 值未校正"
2. 图表/报告产物固定文件名会互相覆盖 → 改用时间戳目录或 base64 内嵌
3. `skills/` / `README.md` / `demos/` 三套文档冗余 → README 为单一事实源
4. `run.py` 品牌不一致（`⚔️ 星见`，疑似旧项目残留）
5. 缺根目录 LICENSE（README 写 MIT，仅 `deploy/LICENSE` 有）
6. Docker CLI 依赖 TTY → 非交互环境 `input()` 会 EOFError
7. 节点未对 LLM 调用 try/except（CLI `analyze()` 无兜底）
8. `analyze_node` 每步塞 `data_json[:3000]` + 历史，大表 token 成本膨胀

---

## 4. 已修复详情（2026-07-18）

| 项 | 文件 | 改动 |
|----|------|------|
| P0-1 决策循环 | `agent.py` | 新增 `_decide_action()` / `_tally()` 代码层强制路由；JSON 解析改用 `_extract_json()`（兼容 ``` 围栏 + 正则兜底） |
| P0-2 编码乱码 | `tools/loader.py` + `agent.py` | 新增 `read_df()` / `detect_encoding_and_sep()`，所有读文件处统一走编码探测 |
| P0-4 Docker | `requirements.txt` | 取消注释 `streamlit>=1.28.0` |
| P1-3 追问上下文 | `agent.py` + `app.py` | CLI 用清洗后 DataFrame；Web 端 `analysis_log` + `cleaned_df` 存入 `session_state` 并传给 `answer_question` |
| P1-1 测试 | `tests/test_routing.py` | 新增 8 条路由/循环终止单测（无需 LLM） |
| P1-2 统计 | `agent.py` | 修 pandas 2 弃用 API；组合放宽到前 3×前 3、上限 6 组并 `dropna` |
| P1-5 字体 | `tools/visualizer.py` | 中文字体列表加入 `WenQuanYi Micro Hei` |
| P1-6 LLM 缓存 | `agent.py` | `create_llm()` 改为模块级单例缓存 |
| 编码容错读取 | `tools/loader.py` | 优先 UTF-8 容错解码（非法字节→`U+FFFD`），不再因个别坏字节 strict 失败回退 latin-1 产生整列乱码；GBK 作为回退 |
| 数值化文本列 | `agent.py` | 新增 `_coerce_numeric()`：把 `GPA='3年2.29'→2.29`、`实践经验='4年'→4` 等文本列转数值；自动跳过标识符/高基数 ID 列（姓名/学号等），避免误转 |
| 报告改用清洗后概览 | `agent.py` + `tools/reporter.py` | `report_node` 用清洗后 df 计算概览传给 reporter；reporter 支持 `cleaned_overview`，"数据概况"展示真实被分析的列而非 76 列原始脏数据 |
| 结构性损坏检测 | `agent.py` | 新增 `_detect_structural_issue()`：原始表含大量 Unnamed 空列且"数值型字段（如 GPA）实际为文本"时，判定为合并表头导致的列错位，给出明确警告并建议改用已清洗数据 |
| 统计/可视化基数过滤 | `agent.py` | 新增 `_usable_cats()`：分组变量/图表轴只用 `2 ≤ nunique ≤ 50` 的分类列，排除姓名/ID 这类唯一值列（避免 `学生0001 vs 学生0002` 的噪声检验与上千根柱的图） |

---

## 5. 验证结果

- 所有改动文件 `py_compile` 通过。
- 路由单测 `tests/test_routing.py`：**8/8 通过**（已补 stub 前置，可在仅装 pandas/numpy 环境运行）。
- 用 stub 绕过重依赖，**实跑真实 `_decide_action` 逻辑：9/9 通过**，含关键模拟——*"LLM 一直返回 clean，流程依然能推进、不死循环"*。
- **真实数据管线复现**（装 pandas/numpy/scipy/matplotlib，仅 LLM 框架桩掉）：
  - 清洗版 `data/clean/clean_career_data.csv`：1000×11，字段全部正常中文（`姓名, 专业背景, …, GPA, 是否拿过奖学金, 就业方向`），无乱码；统计产出 6 组有效检验（按 `专业背景` 分组对比 GPA/实践经验）；可视化产出 2 张图（x 轴取可读性好的 `专业背景`）；报告中"数据概况"展示清洗后 11 列。
  - 原始版 `data/raw/data.csv`：清晰输出结构性损坏警告（"原始表含 89% 的无意义列，且 GPA 实际为文本，疑似合并表头导致列错位，建议改用已清洗数据"），不再产出 76 列乱码报告。
- 本地运行前请：
  ```bash
  pip install -r requirements.txt   # 现含 streamlit
  python -m pytest tests/ -v
  ```

---

## 6. 待办 / 后续

- **[P0-3] 你亲自处理**：去 DeepSeek 控制台吊销并轮换 `.env` 中的 key。
- **[P1-4]** 改用 `llm.with_structured_output(...)`（Pydantic）做结构化输出 + 解析失败重试。
- **[P2]** 产物路径、文档冗余、品牌、`LICENSE`、Docker TTY、节点级 try/except、token 优化，按优先级跟进。

---

## 7. 数据对比与优化（第二轮，2026-07-18 下午）

### 7.1 你贴出的运行输出暴露的问题

| 现象 | 根因 | 修复 |
|------|------|------|
| 报告"数据概况"显示 **76 列 + 中文乱码**（`Å§å…`） | `report_node` 用的是 **load 节点的原始 76 列**结果；编码探测未生效 | 报告改用**清洗后 df** 计算概览；`loader` 改为 UTF-8 容错解码 |
| **统计 0 组、图表 0 张** | 原始表 `GPA` 列实际是文本（`软件工程***`/`博士`…），`nums` 为空，统计/可视化无数值列可用 | 新增 `_coerce_numeric` 把文本数值列转为数值；基数过滤避免把唯一列当分组 |
| 清洗步骤说已降到 8 列，但报告仍 76 列 | 同上，报告与清洗脱节 | 报告概览与清洗后数据一致 |

### 7.2 关键发现：原始 `data.csv` 是"列错位"的坏文件

探查 `data/raw/data.csv` 与你的 `data/clean/clean_career_data.csv` 后确认：

- **`data/raw/data.csv`（6198×76）结构性损坏**：由"合并表头的 Excel"导出，列与数据已错位。例如列名 `社会资源与网?学历与深造计?实践经验`、`是否拿过奖学?就业方向` 是合并单元格被拆坏；标为 `GPA` 的列实际装着专业/学历文本（`软件工程***`、`博士`…）。**这种文件无法靠通用清洗自动修复**——没有原始 Excel 就不知道真实列映射。
- **`data/clean/clean_career_data.csv`（1000×11）是正确版本**：字段为 `姓名, 专业背景, 兴趣爱好, 技能与能力, 地理位置, 社会资源与网络, 学历与深造计划, 实践经验, GPA, 是否拿过奖学金, 就业方向`，GPA 为数值、可正常分析。

### 7.3 本轮优化（已落地并验证）

1. **编码容错读取**：`loader.read_df` 优先 UTF-8 容错解码（个别坏字节→`U+FFFD`），不再因 strict 失败回退 latin-1 产生整列乱码；GBK 作为回退。
2. **数值化文本列**：`_coerce_numeric` 把 `GPA='3年2.29'→2.29`、`实践经验='4年'→4` 这类列转数值，使统计/可视化有可用数值列；自动跳过 `姓名/学号/ID` 等标识符及高基数列，避免误转。
3. **报告用清洗后概览**：`report_node` 从清洗后 df 计算"数据概况"，不再展示 76 列原始脏数据。
4. **结构性损坏检测与警告**：`_detect_structural_issue` 在原始表含大量 Unnamed 空列、且名义数值列（GPA 等）实际为文本时，明确警告"疑似合并表头导致列错位，建议改用已清洗数据"，而不再默默产出垃圾报告。
5. **统计/可视化基数过滤**：`_usable_cats` 只用 `2 ≤ nunique ≤ 50` 的分类列做分组/坐标轴，排除姓名/ID，避免 `学生0001 vs 学生0002`（p=1.0 噪声）和上千根柱的图。

> 结论：把分析对象换成 `data/clean/clean_career_data.csv` 即可得到正确、可读、有统计与图表的报告；原始 `data.csv` 则应回到 Excel 重新规范导出（拆分合并表头）后再分析。

---

## 8. 修复优先级路线图（参考）

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

## 9. 第三轮：运行时加固 + 亮点功能（2026-07-18 晚）

### 9.1 运行时硬伤（你本轮要求修复）

用"假 LLM 桩 + 真实数据"把整条流水线实跑，暴露并修复了 4 个运行时问题：

| 现象 | 根因 | 修复 |
|------|------|------|
| **流程直接跳到 report，跳过 clean/stats/viz**（干净数据 0 检验 0 图） | 旧 `_decide_action` 在"数据已干净/LLM 说 report"时不强制后续步骤，确定性兜底缺失 | 重写为**线性状态机**：clean→stats→viz→report 每种至少执行一次；且 LLM 失效（返回 None）时退化为确定性推进，**不再 0 统计 0 图** |
| **报告被截断到 500 字** | `report_node` 用 `generate_report` 返回的 `preview`（仅前 500 字符）+ 业务洞察，把清洗/统计/可视化章节全丢了 | `generate_report` 返回**完整报告文本** `report`；`report_node` 拼接完整文本；报告章节不再丢失 |
| **stats 节点空分组崩溃** | 某分组被 `dropna` 清空后 `run_test` 对空数组抛异常 | `stats_node` 跳过空组或样本 <3 的分组；`run_test` 返回 `error` 时也跳过 |
| **LLM 报错拖垮整条 Agent** | `analyze/clean/report` 节点的 `llm.invoke` 无兜底，网络/Key/限流异常直接冒泡导致流程中断 | 三个节点均加 `try/except`：**LLM 失效不崩溃**，analyze 退化为确定性路由、clean 退化为仅自动清洗、report 退化为无洞察说明，报告仍完整产出 |

> 实测：当前环境 DeepSeek API **连接失败（Connection error）**，但加固后 Agent 仍能跑出完整报告（含质量评分、统计、图表、相关性），验证了降级路径有效。

### 9.2 新增亮点功能（你要求"加一些亮点"）

1. **🟢 数据质量评分**（新增 `tools/quality.py`）
   - 从**完整性 / 唯一性 / 有效性**三维度算 0–100 综合分（权重 40/20/40），自动判定 `良好/一般/偏差`。
   - 报告新增「0. 数据质量评分」章节；Web UI 顶部新增「数据质量评分」指标卡。

2. **🔗 相关性分析 + 相关性热力图**（亮点）
   - `stats_node` 自动计算数值变量间 Pearson 相关，挑出 `|r|≥0.3` 的强相关 Top 对。
   - `visualizer` 新增 `heatmap` 类型（数值列 ≥2 时自动生成）。
   - 报告新增「3.5 相关性分析」表格。

3. **📊 可视化兜底增强**
   - 纯分类数据自动生成**频次图**（`count` 类型），不再出现"0 图"。
   - 数值化逻辑**优先提取浮点**（如 `GPA='3年2.29'→2.29`），并跳过日期/时间列，避免把日期当数字。

### 9.3 本轮改动文件

| 文件 | 改动 |
|------|------|
| `agent.py` | 重写 `_decide_action`（线性状态机 + LLM 失效降级）；`analyze/clean/report` 节点加 try/except；`stats_node` 加空分组防护 + 相关性计算；`viz_node` 加热力图/频次图兜底；`report_node` 用完整报告 + 数据质量评分；`_coerce_numeric` 优先浮点 + 跳过日期列 |
| `tools/reporter.py` | 返回完整 `report`；新增「数据质量评分」「相关性分析」章节 |
| `tools/quality.py` | **新增** 数据质量评分模块 |
| `tools/visualizer.py` | 新增 `heatmap` / `count` 图表类型 |
| `tools/__init__.py` | 导出 `quality_score` / `quality_label` |
| `app.py` | 结果区新增「数据质量评分 / 数据规模 / 统计检验 / 图表」指标卡 |
| `tests/test_highlights.py` | **新增** 质量评分、数值化、相关性单测 |

### 9.4 验证

- 单测 **40/40 通过**（含新增 `test_highlights.py` 5 条）。
- **端到端探针**跑通三份真实数据：
  - `clean_career_data.csv`：质量分 100，6 组检验，3 张图（bar/box/heatmap）。
  - `sample_sales.csv`：质量分 99.8，6 组检验 + 2 对强相关，3 张图（地区×销售额 / box / heatmap）。
  - `raw/data.csv`：质量分 99.9（清洗后），结构性损坏警告仍在，频次图兜底。
- 真实 API 不可达时，降级路径仍能产出完整报告（已验证）。

### 9.5 给你的建议（后续可做的亮点/打磨）

1. **多文件/多 Sheet 批量分析**：一次上传多个 CSV/Excel，批量产出对比报告。
2. **结构化 LLM 输出**：用 `llm.with_structured_output(...)`（Pydantic）替代 JSON 文本解析，更稳。
3. **交互式图表**：用 Plotly 替代静态 PNG，报告内可悬停/缩放；并支持把报告导出为 HTML/PDF。
4. **异常值/缺失值自动标注到原表**：输出"已标注问题样本"的 CSV 方便回填。
5. **数据画像卡（auto-EDA）**：一键生成字段分布、Top 类别、缺失热力图的总览页。
6. **安全收尾**：轮换 `.env` 明文 Key（P0-3）；产物文件名加时间戳避免互相覆盖（P2-2）。

---

## 10. 第四轮：乱码根治 + 坏文件自动改用干净数据（2026-07-18 晚）

### 10.1 现象（用户实际运行输出）
- 报告「数据概况」字段名全是 `å§å` 这类乱码（应为「姓名」）。
- 统计为 **0 组检验**（只因分析的是坏文件，无任何数值列）。
- Agent 分析了 `data/raw/data.csv`（6198×76，合并表头导出的坏文件），而用户已清洗好的 `data/clean/clean_career_data.csv`（1000×11）完全没被用上。

### 10.2 根因
1. **乱码根因（app.py 上传解码）**：`data/raw/data.csv` 含少量坏字节，严格 `utf-8` 解码失败；app.py 原解码循环 `[utf-8, gbk, gb2312, latin-1]` 一路回退到 **`latin-1`**（UTF-8 字节被当 Latin-1 解码）→ 表头全部乱码，并写进了 `_tmp_upload.csv` 被 Agent 读到。
   - 注意：`tools/loader.read_df` 本身用 `errors="replace"` 能正确解码，所以 CLI 路径无乱码，仅 Web 上传路径有此 bug。
2. **0 检验根因**：坏文件清洗后只剩 8 个带乱码表头的列、GPA 是文本，无任何数值列 → 统计/相关性全部为 0。

### 10.3 修复
| 文件 | 改动 |
|------|------|
| `app.py` | 重写上传解码循环：优先 `utf-8`（`errors="replace"` 容错坏字节），其次 `gbk/gb18030`，**绝不回退 latin-1**；并新增「智能数据源」——检测到上传文件结构性损坏时，自动改用 `data/clean/` 中的干净数据，UI 同步切换并提示 |
| `agent.py` | 新增 `_is_structurally_damaged()`（判断合并表头/列错位：无用列≥30%、列名含 `?`/`·`/`、`、或全文本无数值列）、`_find_clean_source()`（在 `data/clean/` 择优找干净 CSV）、`_resolve_best_source()`；`load_node` 接入该逻辑，**切换后更新 `filepath`**，使后续 clean/stats/viz/report 全部读到干净数据 |
| `tools/statistician.py` | 修复检验结论空括号：`无显著差异（）` → `无显著差异（p=0.xxxx，未达 0.05 显著性水平）`；显著时正常显示星号 |
| `tests/test_highlights.py` | 新增 4 条智能数据源单测（损坏判定 / 干净判定 / 找干净文件 / 自动切换） |

### 10.4 验证
- 单测 **44/44 通过**（新增 4 条智能数据源测试）。
- **端到端（桩 LLM 跑真实坏文件 `data/raw/data.csv`）**：
  - 自动检测到结构性损坏 → 切换至 `clean_career_data.csv`；
  - 加载为 **1000×11，列名无乱码**（姓名/专业背景/…）；
  - **6 组检验**、**3 张图**（bar/box/heatmap）全部产出；
  - 报告结论文案正常：`无显著差异（p = 0.4950，未达 0.05 显著性水平）`。
- 兼容性：直接上传干净文件（或 CLI 指向 `clean_career_data.csv`）时，`_is_structurally_damaged` 返回 False，**不会误切换**。

### 10.5 这一轮带来的「亮点」
- 🤖 **智能数据源选择**：Agent 能识别「上传的是坏文件」并自动改用语义正确的干净数据，对终端用户是无感且省心的体验——可写进 README 作为核心能力点。

---

## 11. 第五轮：图表加载修复 + 多格式报告导出（2026-07-18 晚）

### 11.1 现象（用户反馈）
- 用干净数据 `data/clean/clean_career_data.csv` 跑通了完整流程（1000×11、6 检验、3 图），但 **Web 端图表加载不出来**：报告预览里「4. 可视化」显示成 `bar bar 图` `box box 图` 这种替代文字。
- 用户希望增加 **报告导出自选格式** 的功能。

### 11.2 根因
1. **图表显示为文字**：报告里用了 Markdown 图片语法 `![bar](chart_bar.png)`，但 **Streamlit 的 `st.markdown()` 默认不渲染 Markdown 图片**（出于安全考虑会转义），只显示 alt 文本，于是 `![bar](...)` + 下一行 `*bar 图*` 图注拼成了「bar bar 图」。
2. **工作目录漂移**：图表用相对路径 `chart_bar.png` 保存到当前工作目录；若 `streamlit run app.py` 的启动目录与 app.py 所在目录不同，`os.listdir(".")` 就找不到图表文件。

### 11.3 修复
| 文件 | 改动 |
|------|------|
| `tools/visualizer.py` | 新增 `OUTPUTS_DIR`（项目根 `outputs/` 绝对路径）、`ensure_outputs_dir()`、`resolve_chart_path()`；`create_chart` 把文件名解析到 outputs/ 绝对路径再保存，返回值含 `file`(绝对) 与 `name`(basename) |
| `tools/reporter.py` | 可视化章节图片引用改用相对路径 `outputs/xxx.png`（可移植）；`generate_report` 返回值新增 `charts` 字段（图表绝对路径清单） |
| `agent.py` | `AnalysisState` 新增 `chart_files` 字段；`report_node` 把图表清单写入 state；`analyze()` 初始 state 与返回值均带上 `chart_files` |
| `app.py` | ① 新增 `_render_report_with_images()`：按图片引用把报告拆段，文本段 `st.markdown`、图片段 `st.image()` **内联渲染**，不再显示「bar bar 图」；② 图表 tab 从 `OUTPUTS_DIR` 读取（绝对路径，不受 CWD 影响）；③ 指标卡图表计数改读 `OUTPUTS_DIR` |
| `tools/exporter.py`（新） | 多格式导出器：`to_markdown` / `to_html`（图片 base64 内嵌，自包含单文件）/ `to_pdf`（xhtml2pdf，纯 Python 无原生依赖）/ `to_docx`（python-docx，图片内嵌、表格支持）；`SUPPORTED` 字典标记各格式可用性；统一入口 `export_report(report, path, fmt, chart_files)` |
| `tools/__init__.py` | 导出 `OUTPUTS_DIR` / `ensure_outputs_dir` / `export_report` / `EXPORT_SUPPORTED` |
| `tests/test_highlights.py` | +4 条单测：markdown 导出、HTML base64 内嵌、DOCX 含图、图表落 outputs/ 绝对路径 |

### 11.4 多格式导出说明
| 格式 | 后端 | 特点 |
|------|------|------|
| Markdown | 内置 | 纯文本，可再编辑 |
| HTML | `markdown` 库 | **图片 base64 内嵌，单文件自包含**，可直接浏览器打开、便于分发 |
| PDF | `xhtml2pdf` | 适合打印分发；经 HTML 转换，纯 Python 无原生依赖 |
| Word | `python-docx` | 可在 Word/WPS 中继续编辑，图片与表格均内嵌 |

UI：下载 tab 用 `st.radio` 让用户选格式，按 `EXPORT_SUPPORTED` 自动启停按钮，文件名带时间戳 `analysis_report_YYYYMMDD_HHMMSS.<ext>` 避免互相覆盖。

### 11.5 验证
- 单测 **48/48 通过**（新增 4 条导出/图表路径测试）。
- 端到端（桩 LLM 跑 `clean_career_data.csv`）：3 张图全部落到 `outputs/`、报告含图片引用、四种导出全部成功——MD 2KB / HTML 153KB（含 base64 图）/ PDF 154KB / DOCX 129KB。
- 报告预览不再出现「bar bar 图」，图片直接内联显示；图表 tab 从 `outputs/` 正常加载。
- 无残留临时文件。

### 11.6 这一轮带来的「亮点」
- 📤 **一键多格式导出**：MD / HTML（自包含）/ PDF / Word，覆盖「再编辑 / 浏览器查看 / 打印分发 / Word 协作」四种典型场景，是面向终端用户的核心交付能力。
- 🖼️ **内联图表渲染**：报告预览图文混排，不再有「图加载不出来」的体验断点。
- 📁 **专用 outputs/ 目录**：图表产物集中管理，不再散落项目根，工作目录漂移也不再影响读取。

---

## 12. 第六轮：Web 状态持久化修复（2026-07-18 晚）

### 12.1 现象
用户反馈：**在 Web 端点聊天框或别的按钮时，整个页面跳回"未分析前"状态**——分析结果、报告、图表、追问历史全部消失。

### 12.2 根因
原 `app.py` 把所有"分析→结果展示→追问"全塞进一个块：
```python
if uploaded and analyze_btn:  # ← 守门条件用 widget 状态
    ... 跑分析、渲染结果、聊天 ...
```
而 **Streamlit 每次交互（点聊天、点 tab）都会从头重跑整个脚本**。`analyze_btn` 是个 widget 状态，重跑时会重置为 False → 整个块不执行 → 用户看到初始界面。

### 12.3 修复（app.py 状态管理重构）
1. **session_state 初始化**：顶部一次性声明 10 个键（`analysis_done` / `final_report` / `chart_paths` / `analysis_log` / `cleaned_df` / `issues_summary` / `quality` / `chat_history` / `uploaded_name` / `tmp_path`）。
2. **新文件检测 → 重置**：上传文件名变化时清空所有分析相关 state，避免新旧结果混淆。
3. **分析执行块与结果展示块拆开**：
   - 分析执行块：`if uploaded and analyze_btn and not st.session_state.analysis_done`，跑完后**把全部结果写入 session_state** 并置 `analysis_done = True`。
   - 结果展示块：`if uploaded and st.session_state.analysis_done`，**完全独立于 `analyze_btn`**，从 session_state 读取并渲染——任何后续交互（点 tab / 输入聊天 / 切换 sidebar）都不会让它消失。
4. **聊天区移入持久化块**：`chat_history` 存于 `st.session_state.chat_history`，跨脚本重跑保持。
5. **初始状态补一友好提示**：若已分析但当前无文件上传，给"✅ 上次分析结果已保留"提示，避免用户以为结果丢了。

### 12.4 验证
- 单测 **52/52 通过**（新增 4 条 session_state 结构单测：默认值完整 / 结果区由 `analysis_done` 守门 / 新文件检测重置 / 分析完成时全量保存）。
- 端到端探针：跑 `clean_career_data.csv`，3 图落 `outputs/`、报告 1246 字、状态正确写入。
- 修复后行为：用户上传→分析→点聊天框→点 tab→切换 sidebar，**结果始终在**；只有上传新文件才会清空旧结果。

### 12.5 给用户的提示
- 上传**新文件**才会重置分析结果；同一文件下所有交互（追问、切换 tab、下载）结果都保留。
- 若想清空当前结果，刷新页面即可（session_state 是会话级存储）。

---

## 13. 第七轮：星见雅主题（2026-07-18 晚）

### 13.1 用户需求
为 Web 页面换一套有颜值的主题，举例"星见雅"——绝区零中的冰系女仆角色。选定为「只换星见雅一套 + 加点装饰元素」。

### 13.2 视觉设计
**主色板**（冰紫暗调）：
- 背景：深紫黑 `#0F0E1A` + `#1A1828` 渐变 + 双侧辐射紫光
- 强调色：冰紫 `#9D8DF1` / 浅紫 `#B19CD9` / 冰蓝 `#7FC8F8`
- 文字：浅银 `#E8E6F0` / 弱化 `#9C9AAB`

**装饰元素**：
- 标题渐变文字（紫→蓝）+ 紫光下划线带
- Subheader 前置 ❄ 冰晶字符
- 步骤卡片：玻璃态 + 悬浮时左移 3px + 紫光阴影加强
- 指标卡：渐变数字 + 紫光玻璃背景
- 按钮：紫色渐变 + hover 发光 + 浮起 1px
- Tab：选中态底部紫光下划线
- 滚动条：紫渐变
- 聊天气泡：玻璃态卡片
- 进度条：紫蓝渐变
- 引用块：紫边 + 紫底

### 13.3 改动
- `app.py`：
  - `<style>` 段重写（350 行 → 完整主题化）
  - 标题改为「❄ 星见雅 · Data Analysis Agent」+ 副标题「❄ 冰系分析 · 数据之美 · 上传即洞察」
  - `page_icon` 从 📊 改为 ❄
  - `page_title` 加「星见雅」标记

### 13.4 验证
- 编译干净；52 项单测全过；端到端探针（clean_career_data.csv）跑通：3 图落 outputs/、报告 1246 字。
- 主题标记（星见雅/9D8DF1/B19CD9/7FC8F8）共 24 处全部生效。

### 13.5 后续可扩展
- 加 favicon ❄ SVG（当前浏览器自动用 emoji）
- 做"主题切换器"框架：把样式抽到 `themes/xingjianya.py`，侧边栏下拉选主题
- 加更多角色主题（如「星核」「莱特」「简」等绝区零角色，配对应色板）
