# 📊 Data Analysis Agent

[![Tests](https://github.com/Hong-lf0719/data-analysis-agent/actions/workflows/test.yml/badge.svg)](https://github.com/Hong-lf0719/data-analysis-agent/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> 🤖 **LLM 驱动的数据分析 Agent** — 上传数据，Agent 自动清洗、统计检验、可视化、生成报告。
>
> 基于 LangGraph 构建，LLM 在每一步动态决策"下一步该做什么"，而非固定流水线。

---

## 🎬 效果演示

```bash
$ daa data/sample_sales.csv

============================================
LangGraph 数据分析 Agent | data/sample_sales.csv
============================================

📂 [加载] data/sample_sales.csv
   发现 5 个问题

🧠 [分析-1] 数据已加载，发现5个问题，先清洗
   决策: clean

🧹 [清洗]
   LLM 决定执行 3 个清洗操作
      → drop_outliers: 利润率值800000超出合理范围
      → rename: electronics 应统一为电子产品
      → fillna: 销售额缺失值用中位数填充
   清洗后: 37→36 行

🧠 [分析-2] 数据已清洗干净，进入统计分析
   决策: stats

🔬 [统计]
   地区→销售额: 华东 vs 华南 无显著差异
   地区→利润率: 华北 vs 华南 存在显著差异(p=0.03)

🧠 [分析-3] 统计完成，可视化
   决策: viz

📈 [可视化]
   生成 2 张图表

🧠 [分析-4] 全部完成，生成报告
   决策: report

📝 [报告]
## 业务洞察
- 华东地区销售额最高，平均 18.5 万/月
- 家居用品利润率(44%)显著高于电子产品(31%)
- 建议：重点拓展华东家电市场，Q4 有明显的季节性增长

✅ 报告已生成: analysis_report.md
```

---

## ⚡ 快速开始

### 安装

```bash
pip install -r requirements.txt
```

### 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 API key（支持 DeepSeek / OpenAI / 任何 OpenAI 兼容 API）
```

`.env` 内容：
```
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

### 运行

```bash
# CLI 模式（支持追问）
python agent.py data/sample_sales.csv
# 分析完成后可以继续追问

# Web UI 模式
pip install streamlit
streamlit run app.py
# 浏览器打开 http://localhost:8501
```

### Docker 一键部署

```bash
# Web UI
docker compose up web

# CLI 模式
docker compose run --rm cli data/sample_sales.csv
```

---

## 🧠 核心能力

| 能力 | 说明 |
|------|------|
| 🔍 智能加载 | 自动检测编码（UTF-8/GBK）、分隔符（逗号/制表符）；坏文件（合并表头/列错位）自动改用 `data/clean/` 中的干净数据 |
| 🧹 LLM 驱动清洗 | AI 自主决策如何清洗（非硬编码规则） |
| 📊 自动统计分析 | 正态性检验 → 自动选 t-test / Mann-Whitney，含效应量；自动相关性分析 |
| 🟢 数据质量评分 | 从完整性/唯一性/有效性算 0–100 综合分，报告与 UI 同步展示 |
| 📈 可视化 | 根据数据特征自动选择图表（柱状/箱线/分布/频次/相关性热力图） |
| 🔗 相关性分析 | 自动挑出强相关变量对并生成热力图 |
| 📝 报告生成 | 结构化 Markdown 报告（含质量评分、统计、相关性、可视化）+ LLM 业务洞察 |
| 📤 多格式导出 | 一键导出 Markdown / HTML（图片内嵌自包含）/ PDF / Word，适合分发与编辑 |
| 🖼️ 内联图表 | 报告预览里图片直接内联渲染，图表统一存 `outputs/` 目录 |
| 🛡️ 健壮降级 | LLM 不可用（网络/Key 问题）时仍走确定性流程产出完整报告 |
| 🔄 动态决策 | LangGraph 驱动，每步根据数据状态智能路由 |
| 💬 多轮对话 | 分析完成后可追问（"只看华东""为什么利润率高？"） |
| 🌐 Web UI | Streamlit 界面：拖拽上传 → 一键分析 → 聊天追问 |
| 🐳 Docker 支持 | 一行命令部署 |

---

## 🏗️ 架构

```
用户：分析 data.csv
    │
    ▼
┌────────────────────────────────────┐
│     LangGraph 决策引擎（agent.py）   │
│                                    │
│   ┌──────────┐                    │
│   │ analyze  │ ← LLM 每步检查数据   │
│   └────┬─────┘    动态决策下一步     │
│        │                          │
│   ┌────┼────┬────┬────┬────┐      │
│   ▼    ▼    ▼    ▼    ▼    ▼      │
│ load clean stats viz report DONE  │
│   │    │    │    │    │            │
│   └────┴────┴────┴────┘            │
│        │                          │
│   回到 analyze（循环直到完成）       │
└────────────────────────────────────┘
    │
    ▼
📄 analysis_report.md + 📊 chart_*.png
```

---

## 📁 项目结构

```
data-analysis-agent/
├── agent.py           ← LangGraph 决策引擎（核心）
├── app.py             ← Streamlit Web UI
├── tools/             ← 工具层
│   ├── loader.py      ← 数据加载 + 编码检测
│   ├── cleaner.py     ← 问题诊断 + LLM 驱动清洗
│   ├── statistician.py ← 假设检验 + 效应量
│   ├── visualizer.py  ← 图表生成
│   └── reporter.py    ← 报告输出
├── tests/             ← 单元测试（59个用例）
│   └── fixtures/      ← 测试数据
├── data/
│   ├── samples/       ← 示例数据
│   ├── raw/           ← 原始数据
│   └── clean/         ← 清洗后数据
├── docs/              ← 文档归档
├── Dockerfile         ← Docker 镜像
├── docker-compose.yml ← 一键部署
├── pyproject.toml     ← pip 包配置
└── .env.example       ← API Key 配置模板
```

---

## 🧪 运行测试

```bash
pip install pytest pytest-cov
python -m pytest tests/ -v --cov=tools

# 59 tests, 100% pass
```

---

## 📄 License

MIT
