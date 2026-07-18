---
name: data-analysis-workflow
description: 数据分析全流程。使用 LangGraph Agent 驱动，LLM 在每一步动态决策"下一步该做什么"，取代固定流水线。
version: 2.0
---

# 数据分析全流程（LangGraph 驱动）

## 一句话

> 不再是 A→B→C 固定流水线。LangGraph 让 LLM 在每一步检查数据后动态决策下一步。

## 架构

```
用户：分析 data.csv
    │
    ▼
┌────────────────────────────────────┐
│         LangGraph 决策引擎          │
│                                    │
│   ┌──────────┐                    │
│   │ analyze  │ ← LLM 每步都在思考    │
│   └────┬─────┘                    │
│        │                          │
│   ┌────┼────┬────┬────┬────┐      │
│   ▼    ▼    ▼    ▼    ▼    ▼      │
│ load clean stats viz report DONE  │
│   │    │    │    │    │            │
│   └────┴────┴────┴────┘            │
│        │                          │
│   回到 analyze（循环）              │
└────────────────────────────────────┘
    │
    ▼
📄 analysis_report.md
```

## 文件结构

```
data-analysis-workflow/
├── SKILL.md           ← 本文件
├── agent.py           ← LangGraph 决策引擎（核心）
├── tools/             ← 工具层
│   ├── loader.py      ← 数据加载 + 编码检测
│   ├── cleaner.py     ← 问题诊断 + 清洗执行
│   ├── statistician.py ← 假设检验 + 效应量
│   ├── visualizer.py  ← 图表生成
│   └── reporter.py    ← 报告输出
├── requirements.txt
└── .env.example
```

## 执行规则

当用户说"分析数据"时：

### 第一步：确认文件
```
使用 load_data() 加载文件，自动检测编码和分隔符。
用 inspect_data() 生成数据摘要，传给 LLM 分析。
```

### 第二步：LangGraph Agent 接管
```
运行 agent.py → analyze()，Agent 自动循环：
  analyze  →  LLM 检查数据，决定下一步
     │
     ├── "列名拼错、有异常值" → clean
     ├── "数据干净" → stats
     ├── "统计完成" → viz
     ├── "全部完成" → report
     └── 每步执行完 → 回到 analyze 再次判断
```

### 第三步：交付
```
生成 analysis_report.md + 图表文件，返回给用户。
```

## 与旧架构的区别

| | 旧架构 | 新架构（LangGraph） |
|------|------|------|
| 路线 | A→B→C 固定顺序 | LLM 动态决策 |
| 异常 | 报错/跳过 | LLM 发现 → 自动清洗 |
| 方法选择 | 写死 t 检验 | LLM 判断用什么方法 |
| 图表类型 | 写死柱状图 | LLM 根据数据特征选择 |

## 依赖

```bash
pip install langgraph langchain-openai pandas scipy matplotlib python-dotenv
```

## 环境变量

复制 `.env.example` → `.env`，填入 DeepSeek 或 OpenAI key。
