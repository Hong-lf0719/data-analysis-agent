# report-generation Demo

## 方法：TDD for Skills

## RED 阶段（无 Skill）

**素材来源：** 之前的报告生成中的问题

**7 个错误：**
1. 报告缺章节（缺数据来源、方法论、局限性）
2. 中间产物和最终报告混在一起
3. 没有标注生成时间、Skill 版本
4. 没问用户要什么格式
5. 图表和文字分离
6. 缺少可导航的目录
7. 没有列出所有文件路径

## GREEN 阶段（加载 Skill）

**7/7 流程全部通过：**
- 先让选格式（A~E）
- 列 9 章结构让用户确认
- 封面含标题、时间、数据源、5 个 Skill 列表
- 目录含锚点跳转链接
- 图文捆绑，每图紧跟解读
- 交付 8 个文件完整清单

## RED 发现（新错误）

Agent 从错误来源取了结论：H3 的 r=−0.45 来自 visualization 报告，
而非 statistical-analysis 的正确结果（r=−0.02）。

## REFACTOR

第 3 步"收集分析产出"加数据来源优先级：
统计检验结果以 statistical-analysis 为准；
同一个数值出现在多个来源 → statistical-analysis 优先。
