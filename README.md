# 📊 Data Analysis Agent

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> 🤖 **LLM 驱动的数据分析 Agent** — 上传数据，Agent 自动清洗、统计检验、可视化、生成报告。
>
> 基于 LangGraph 构建，LLM 在每一步动态决策"下一步该做什么"，而非固定流水线。

---

## ⚡ 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env  # 填入 API key（支持 DeepSeek / OpenAI / 任何兼容 API）

# CLI 模式
python agent.py data/sample_sales.csv

# Web UI 模式
streamlit run app.py

# Docker 一键部署
docker compose up web
```

---

## 🧠 核心能力

| 能力 | 说明 |
|------|------|
| 🔄 动态决策 | LangGraph 驱动，每步按数据状态智能路由，非固定流水线 |
| 🔍 智能加载 | 自动检测编码/分隔符；坏文件自动切换干净数据源 |
| 🧹 LLM 驱动清洗 | AI 自主决策清洗策略，非硬编码规则 |
| 📊 自动统计分析 | 正态性检验 → 自动选 t-test / Mann-Whitney，含效应量 |
| 📈 可视化 | 根据数据特征自动选择图表（柱状/箱线/分布/热力图） |
| 🟢 数据质量评分 | 0–100 综合分，从完整性/唯一性/有效性维度评估 |
| 📝 报告生成 | 结构化报告 + LLM 业务洞察，支持多轮追问 |
| 📤 多格式导出 | Markdown / HTML（图片内嵌）/ PDF / Word |
| 🛡️ 健壮降级 | LLM 不可用时仍走确定性流程产出完整报告 |
| 🐳 Docker 部署 | 一行命令启动 |

---

## 🏗️ 架构

```
用户：分析 data.csv
    │
    ▼
┌──────────────────────────────────┐
│   LangGraph 决策引擎（agent.py）   │
│                                  │
│   analyze ← LLM 每步动态决策      │
│      │                           │
│   load → clean → stats → viz     │
│      │              → report     │
│      └── 循环直到完成 ──┘         │
└──────────────────────────────────┘
    │
    ▼
📄 分析报告 + 📊 图表
```

---

## 📁 项目结构

```
data-analysis-agent/
├── agent.py            ← LangGraph 决策引擎
├── app.py              ← Streamlit Web UI
├── tools/              ← 工具层（加载/清洗/统计/可视化/报告/导出）
├── skills/             ← SKILL.md 校验规则（779 行）
├── tests/              ← 单元测试（59 个用例）
├── data/samples/       ← 示例数据
├── deploy/             ← Dockerfile + docker-compose
└── .env.example        ← API Key 配置模板
```

---

## 🧪 测试

```bash
python -m pytest tests/ -v
# 59 tests, 100% pass
```

---

## 📄 License

MIT
