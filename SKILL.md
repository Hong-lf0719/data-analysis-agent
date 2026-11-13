---
name: data-analysis-skill
description: 让任何支持 Skill 的 agent 自动完成「数据加载 → 清洗 → 统计检验 → 可视化 → 报告生成」全流程数据分析。上传 CSV/Excel，agent 用 LangGraph 在每一步动态决策下一步，产出结构化报告 + 图表 + 多格式导出（Markdown/HTML/PDF/Word）。
version: 3.0
author: Hong-lf0719
---

# 数据分析 Skill（Data Analysis Skill）

> 一句话：**上传数据，自动完成 加载 → 清洗 → 统计 → 可视化 → 报告 全流程。**

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API key（支持 DeepSeek / OpenAI / 任何兼容 API）
cp .env.example .env   # 填入 DEEPSEEK_API_KEY 或 OPENAI_API_KEY

# 3. 跑一个示例
python agent.py data/samples/sample_sales.csv
```

产出：`analysis_report.md` + PNG 图表若干（含正态性检验、假设检验、效应量）。

## 能力清单

| 阶段 | 能力 | 说明 |
|------|------|------|
| 加载 | 智能编码/分隔符检测 | 自动识别 GBK/UTF-8、逗号/制表符 |
| 清洗 | LLM 驱动清洗 | AI 自主决策清洗策略，非硬编码规则 |
| 统计 | 假设检验 + 效应量 | 正态性检验 → 自动选 t-test / Mann-Whitney，含效应量 |
| 可视化 | 自动选图 | 根据数据特征选柱状/箱线/分布/热力图 |
| 报告 | 结构化 + 业务洞察 | 质量评分 0-100 + LLM 业务解读，支持多轮追问 |
| 导出 | 4 种格式 | Markdown / HTML（图片内嵌）/ PDF / Word |

## 目录结构

```
data-analysis-skill/
├── SKILL.md              ← 本文件（skill 入口）
├── agent.py              ← LangGraph 决策引擎（核心）
├── app.py                ← Streamlit Web UI
├── skills/               ← 6 个子 skill 定义（workflow + 加载/清洗/统计/可视化/报告）
├── tools/                ← 工具层（loader/cleaner/statistician/visualizer/reporter）
├── examples/             ← 示例数据 + 示例报告（一眼看懂输出）
├── tests/                ← 单元测试
└── requirements.txt
```

> **入口说明**：本文件（仓库根目录 `SKILL.md`）是**唯一的 skill 包入口**。
> `skills/` 下是 6 个**可被单独加载的子 skill 定义**（各自带 frontmatter 与独立 name），
> 属于子技能库，不是包入口——加载器请以根目录 `SKILL.md` 为准。

## 示例输出

见 `examples/README.md`，含一份真实跑通的 `analysis_report.md` 样例。
