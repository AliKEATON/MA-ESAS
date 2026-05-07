## 1. 文档定位

本文档描述的是当前后端系统的**真实实现**，不是早期草案，也不是理想化设计图。

当前分析链路的核心特征是：

- 统一消息入口
- 任务化分析执行
- LangGraph 串联前置数据节点与多 Agent 节点
- 最终由服务层统一落库和对外返回结果

需要特别说明：

- `resolve_product_context` 和 `ensure_product_data` 虽然不属于“LLM Agent”，但它们已经是工作流中的正式节点
- `router_agent` 现在只负责路由，不再负责产出 `analysis_targets`
- `sql_agent` 现在自主分析用户问题并选择受控统计工具
- `visual_agent` 已移除模板兜底，只依赖大模型生成图表 DSL

---

## 2. 整体工作流总览

当前工作流主链路如下：

```text
resolve_product_context
-> ensure_product_data
-> router_agent
-> sql_agent（按路由需要执行）
-> rag_agent（按路由需要执行）
-> visual_agent（按路由需要执行）
-> answer_agent
-> master_agent
-> finalize
```

其中：

- 前两个节点负责准备上下文和数据
- 中间三个 Agent 负责统计、检索和可视化
- `answer_agent` 负责整合结果并生成候选回答
- `master_agent` 负责最终审查，必要时触发局部重试
- `finalize` 只负责标记工作流结束

服务层在工作流结束后继续做两件事：

- 把结果写入 `analysis_reports`
- 把结果封装为前端可消费协议

---

## 3. `resolve_product_context`

### 3.1 职责

`resolve_product_context` 的职责不是重新解析商品，而是：

- 确认这次任务到底有没有商品上下文
- 校验商品上下文是否可信
- 输出标准化 `ProductContext`

它是工作流里的第一个节点，代码位置：

- [workflow.py](D:/学业/大四/毕业设计/MA-ESAS-1/backend/app/agents/workflow.py)

### 3.2 输入

它主要读取：

- `task.product_id`
- `task.product`
- `runtime.product_resolved_from`

这里的商品初步绑定，已经在任务创建前由服务层做过一次：

- 消息中有商品链接则优先解析
- 没有链接时可回退到会话绑定商品

### 3.3 处理逻辑

它会依次做以下校验：

1. `task.product_id` 是否存在
2. `task.product` 是否存在
3. `task.product.id` 是否等于 `task.product_id`
4. `product_resolved_from` 是否是合法来源：
   - `message_link`
   - `bound_product`
   - `none`

如果没有商品，则不会报错，而是返回“无商品上下文”。

如果存在明显矛盾，例如：

- `product_id` 有值但商品实体缺失
- `resolved_from` 不是合法枚举值

则会直接抛错，因为这说明任务数据本身已经不可信。

### 3.4 输出

输出是 `ProductContext`，核心字段包括：

- `has_product`
- `source`
- `external_product_id`
- `product_id`
- `resolved_from`

### 3.5 作用总结

它的本质作用是：

**给整条工作流做一次“商品上下文是否合法”的入场检查。**

---

## 4. `ensure_product_data`

### 4.1 职责

`ensure_product_data` 的职责是：

- 在已有商品上下文的前提下
- 检查评论数据是否可用
- 检查向量数据是否可用
- 必要时触发爬虫或补做向量化

代码位置：

- [workflow.py](D:/学业/大四/毕业设计/MA-ESAS-1/backend/app/agents/workflow.py)

### 4.2 输入

它主要依赖：

- `product_context`
- `db`
- `should_crawl_fn`
- `crawl_product_fn`
- `ensure_vector_ready_fn`

这些函数能力由服务层注入，来源在：

- [analysis_service.py](D:/学业/大四/毕业设计/MA-ESAS-1/backend/app/services/analysis_service.py)

### 4.3 处理逻辑

处理过程分三段：

#### 第一段：判断有没有商品

如果出现以下任一情况：

- `product_context is None`
- `has_product = false`
- `product_id is None`

则直接返回：

- `data_ready = false`
- `vector_ready = false`
- `data_issue = "no_product_context"`

#### 第二段：判断是否需要重爬

如果有商品：

1. 重新按 `product_id` 查询商品
2. 校验商品实体存在
3. 调 `should_crawl_fn(product)` 判断是否需要重新抓取

当前重爬规则是：

- 从未抓取过 -> 需要重爬
- 距离上次抓取超过 3 天 -> 需要重爬
- 否则复用缓存评论数据

如果需要重爬，则调用：

- `CrawlerService.crawl_product(...)`

#### 第三段：检查评论和向量是否可用

在评论数据层面：

- 统计当前商品评论数
- 如果评论数为 0，则 `data_ready = false`

在向量数据层面：

- 调 `ensure_vector_ready_fn(db, product_id)`
- 如果评论已有但向量未完成，则补做向量化

### 4.4 输出

输出是 `DataContext`，核心字段包括：

- `data_ready`
- `used_cache`
- `crawler_triggered`
- `vector_ready`
- `last_crawled_at`
- `comment_count`
- `data_issue`

### 4.5 作用总结

它的本质作用是：

**把“有没有数据”和“数据能不能分析”这件事，在工作流前面一次性说清楚。**

---

## 5. `router_agent`

### 5.1 职责

`router_agent` 当前只负责：

- 判断是否需要 SQL 统计
- 判断是否需要 RAG 检索
- 判断是否需要可视化
- 给出回答风格

它**不再**负责产出 `analysis_targets`。

代码位置：

- [router_agent.py](D:/学业/大四/毕业设计/MA-ESAS-1/backend/app/agents/router_agent.py)

### 5.2 输入

输入主要是：

- `question`
- `product_context`
- `data_context`

### 5.3 正常路径

优先走大模型，输出 `RouteDecision`。

大模型需要判断：

- `need_sql`
- `need_rag`
- `need_visual`
- `response_style`
- `reason`

### 5.4 fallback 规则

如果大模型不可用，则走本地关键词规则。

#### 无商品上下文

直接关闭所有分析能力：

- `need_sql = false`
- `need_rag = false`
- `need_visual = false`

#### 可视化判断

如果问题里包含以下词之一，则启用 `need_visual`：

- 可视化
- 图
- 图表
- 分布
- 趋势
- 占比
- 柱状图
- 折线图
- 饼图

#### RAG 判断

如果问题里包含以下词之一，则启用 `need_rag`：

- 原因
- 为什么
- 评价
- 评论
- 吐槽
- 体验
- 问题
- 差评
- 优点
- 缺点

#### SQL 判断

如果问题里包含以下词之一，则启用 `need_sql`：

- 评分
- 差评
- 均分
- 占比
- 数量
- 分布
- 统计
- rate
- score

### 5.5 输出

输出是 `RouteDecision`：

- `need_sql`
- `need_rag`
- `need_visual`
- `response_style`
- `reason`

### 5.6 作用总结

它的职责边界现在非常清晰：

**只决定“哪些能力要不要执行”，不决定 SQL 具体统计什么。**

---

## 6. `sql_agent`

### 6.1 职责

`sql_agent` 的职责是：

- 根据用户问题自主选择统计工具
- 执行受控统计
- 产出结构化指标 `metrics`

代码位置：

- [sql_agent.py](D:/学业/大四/毕业设计/MA-ESAS-1/backend/app/agents/sql_agent.py)

### 6.2 输入

输入只有：

- `db`
- `product_id`
- `question`

它不再接收 `analysis_targets`。

### 6.3 可用统计工具

当前受控工具固定为 5 个：

- `score_summary`
- `score_distribution`
- `bad_review_rate`
- `bad_review_distribution`
- `dimension_stats`

这意味着：

- SQL Agent 不是自由写 SQL
- 只能在白名单统计工具范围内做受控分析

### 6.4 工作流程

#### 第一步：大模型规划工具调用

它会把：

- 用户问题
- 商品 ID
- 可用工具列表

交给大模型，让模型自主判断应调用哪些工具。

#### 第二步：清洗工具调用

模型输出后，系统会做硬校验：

- 工具名必须在白名单中
- 去重
- 强制注入 `product_id`

#### 第三步：读取评论数据

从 MySQL 读取当前商品评论，并转成 DataFrame。

#### 第四步：DuckDB 执行统计

把评论 DataFrame 注册到 DuckDB 内存库，然后逐个执行受控统计工具。

能产出的指标包括：

- 评分概览
- 评分分布
- 差评率
- 差评维度分布
- 各维度统计

#### 第五步：大模型总结描述

工具执行完后，再让大模型基于 `metrics` 生成：

- `description`

### 6.5 当前失败行为

当前 `sql_agent` 已移除 fallback。

所以：

- 工具规划失败 -> 空统计
- 摘要生成失败 -> 空统计

不会再走本地确定性工具映射，也不会再走本地摘要模板。

### 6.6 输出

输出是 `SQLAgentResult`：

- `tool_calls`
- `metrics`
- `description`

### 6.7 作用总结

它的本质角色是：

**整条链路中的统计指标生产者。**

`visual_agent` 能画什么图，首先受限于 `sql_agent` 产出了什么指标。

---

## 7. `rag_agent`

### 7.1 职责

`rag_agent` 的职责是：

- 从评论中检索证据
- 对证据做语义总结
- 产出“为什么”的解释材料

代码位置：

- [rag_agent.py](D:/学业/大四/毕业设计/MA-ESAS-1/backend/app/agents/rag_agent.py)

### 7.2 输入

输入包括：

- `db`
- `product_id`
- `question`

### 7.3 工作流程

#### 第一步：构造检索 query

先把用户问题转成一个 query 列表：

- 原始问题本身
- 根据关键词扩展的子 query

例如：

- 问差评原因 -> 会补差评相关 query
- 问物流/售后/质量 -> 会补对应维度 query

#### 第二步：确保评论已向量化

调用：

- `VectorStoreService.ensure_product_vectorized(...)`

如果评论还没有向量化，则先补做向量化。

#### 第三步：优先做向量检索

调用：

- `VectorStoreService.query_product_comments(...)`

从当前商品评论向量里检索相似证据。

#### 第四步：关键词 fallback

如果向量检索没有拿到结果，则退回 MySQL 评论表做关键词匹配检索。

所以当前 RAG 检索策略是：

- 向量检索优先
- 关键词检索兜底

#### 第五步：大模型总结 insight

拿到证据后，再让大模型总结：

- `insight`
- `insight_points`

#### 第六步：总结失败 fallback

如果大模型失败，则走本地 fallback：

- 保留 evidence
- 用模板生成保守 insight

### 7.4 输出

输出是 `RAGAgentResult`：

- `evidence`
- `insight`
- `insight_points`

### 7.5 作用总结

它的本质角色是：

**评论证据检索与语义归纳节点。**

---

## 8. `visual_agent`

### 8.1 职责

`visual_agent` 的职责是：

- 根据 SQL 指标生成图表 DSL
- 做结构和数据校验
- 输出前端可直接渲染的图表协议

代码位置：

- [visual_agent.py](D:/学业/大四/毕业设计/MA-ESAS-1/backend/app/agents/visual_agent.py)

### 8.2 输入

输入主要是：

- `question`
- `sql_result.metrics`

### 8.3 它依赖哪些指标

当前只认这些 SQL 指标：

- `score_summary`
- `score_distribution`
- `bad_review_rate`
- `bad_review_distribution`
- `dimension_stats`

如果这些指标都没有，则直接返回空图表。

### 8.4 工作流程

#### 第一步：让大模型生成图表方案

把：

- 用户问题
- SQL 指标

交给大模型，让它输出 `VisualAgentResult`。

允许的图表类型有：

- `bar`
- `line`
- `pie`
- `scatter`
- `radar`
- `stacked_bar`

#### 第二步：结构校验

系统先检查图表结构是否合法：

- 饼图数据结构是否正确
- 坐标轴图是否有 `x_axis`
- 系列长度是否和轴对齐

#### 第三步：数据落地校验

再检查图里的数值是否真的来自 SQL 指标，而不是模型编造：

- 分布轴图会回查真实分布值
- 饼图会校验每个扇区的 `name/value`
- 维度图会校验每个维度统计值

只保留“结构合法且数据真实”的图。

### 8.5 当前失败行为

当前 `visual_agent` 已移除模板兜底。

所以：

- 大模型失败 -> 空图表
- 输出结构不合法 -> 空图表
- 数据校验失败 -> 空图表

### 8.6 输出

输出是 `VisualAgentResult`：

- `charts`

### 8.7 作用总结

它的本质角色是：

**可视化 DSL 生成与校验节点。**

---

## 9. `answer_agent`

### 9.1 职责

`answer_agent` 的职责是：

- 汇总 SQL/RAG/Visual 的已有结果
- 生成面向用户的候选回答草稿

代码位置：

- [answer_agent.py](D:/学业/大四/毕业设计/MA-ESAS-1/backend/app/agents/answer_agent.py)

### 9.2 输入

输入包括：

- `question`
- `route_decision`
- `sql_result`
- `rag_result`
- `visual_result`

### 9.3 工作流程

#### 正常路径

优先走大模型，把这些结果一起交给 LLM，总结成：

- `answer`
- `answer_points`

要求模型：

- 直接回答问题
- 不复述流程
- 不编造统计值、评论证据、图表内容

#### fallback 路径

如果大模型失败，则走本地整合：

1. 先提炼关键结论点
2. 再按 `response_style` 组织成回答文本

当前 fallback 会优先利用：

- `sql_result.description`
- `rag_result.insight_points`
- `visual_result.charts`

如果完全没有可用结论点，则返回中性提示：

- 当前未产出足够分析结果，建议稍后重试或补充更明确的问题信息

### 9.4 输出

输出是 `AnswerDraft`：

- `answer`
- `answer_points`

### 9.5 作用总结

它的本质角色是：

**分析结果的统一汇总节点。**

---

## 10. `master_agent`

### 10.1 职责

`master_agent` 的职责是：

- 审查候选回答是否可交付
- 判断是否需要局部重试
- 判断达到上限后是否允许降级交付

代码位置：

- [master_agent.py](D:/学业/大四/毕业设计/MA-ESAS-1/backend/app/agents/master_agent.py)

### 10.2 输入

输入包括：

- `question`
- `route_decision`
- `answer_text`
- `answer_points`
- `visual_result`
- `retry_count`
- `max_retry`

### 10.3 工作流程

#### 正常路径

优先走大模型，让模型判断：

- 是否已经答题
- 结论点是否足够
- 如果用户需要图表，图表是否齐备

最终输出 `MasterDecision`。

#### fallback 路径

如果大模型失败，则走本地规则：

1. 如果缺图表 -> 缺失项加入 `visual_result`
2. 如果没答题或答非所问 -> 缺失项加入 `answer`
3. 如果结论点过弱或为空 -> 缺失项加入 `answer_points`

如果没有缺失，则：

- `decision = pass`

如果有缺失且还没达到上限，则：

- `decision = retry`
- `retry_from = visual_agent` 或 `answer_agent`

如果已经达到上限，则：

- `decision = fallback_pass`
- 允许带缺失降级交付

### 10.4 重试上限如何控制

当前重试上限不是由模型生成的，而是由工作流硬编码默认值提供：

- `retry_count` 初始为 `0`
- `max_retry` 默认是 `1`

大模型会看到这两个值，但上限本身来自工作流状态。

### 10.5 输出

输出是 `MasterDecision`：

- `decision`
- `reason`
- `missing_items`
- `retry_from`

### 10.6 作用总结

它的本质角色是：

**候选回答的最终审查节点。**

---

## 11. `finalize`

### 11.1 职责

`finalize` 的职责很简单：

- 把工作流标记为结束

代码位置：

- [workflow.py](D:/学业/大四/毕业设计/MA-ESAS-1/backend/app/agents/workflow.py)

### 11.2 处理逻辑

它只做两件事：

1. 更新任务步骤为 `finalize`
2. 把进度设为 `100` 并标记完成

它不负责：

- 生成最终回答
- 拼装最终前端协议
- 落库 `analysis_reports`

### 11.3 作用总结

它的本质角色是：

**工作流结束标记节点。**

---

## 12. 服务层最终封装

工作流结束后，真正的结果封装在服务层完成，位置在：

- [analysis_service.py](D:/学业/大四/毕业设计/MA-ESAS-1/backend/app/services/analysis_service.py)

### 12.1 `process_task()`

这是后台分析任务主入口：

- 创建工作流 runtime
- 调 `AnalysisWorkflow.run(...)`
- 拿到 `workflow_state`
- 调用 `_upsert_report_from_workflow(...)`

### 12.2 `_build_final_response()`

这是最终回答协议的组装位置。

它会从 `workflow_state` 提取：

- `answer_draft`
- `visual_result`
- `product_context`

组装成最终的 `final_response`。

### 12.3 `_upsert_report_from_workflow()`

这是工作流结果落库位置。

它会把这些内容统一写进 `analysis_reports.statistics_json`：

- `product_context`
- `data_context`
- `route_decision`
- `sql_result`
- `visual_result`
- `rag_result`
- `answer_draft`
- `master_decision`
- `final_response`
- `retry_count`

同时把 `evidence` 写入：

- `analysis_reports.evidence_json`

### 12.4 `get_task_result()`

这是对前端返回最终结果的位置。

它会从 `report.statistics_json` 里取出：

- `final_response`
- `route_decision`
- `sql_result`
- `visual_result`
- `rag_result`
- `answer_draft`
- `master_decision`

再封装成 API 返回结构。

### 12.5 服务层作用总结

也就是说：

- 工作流内只负责生产状态和中间结果
- 服务层负责最终协议组装、落库和 API 输出

---

## 13. 各 Agent 之间的依赖关系

### 13.1 前置依赖

- `ensure_product_data` 依赖 `resolve_product_context`
- `router_agent` 依赖 `product_context` 和 `data_context`

### 13.2 中间依赖

- `sql_agent` 依赖 `router_agent.need_sql`
- `rag_agent` 依赖 `router_agent.need_rag`
- `visual_agent` 依赖 `router_agent.need_visual`

### 13.3 强依赖关系

- `visual_agent` 强依赖 `sql_result.metrics`
- `answer_agent` 依赖 `sql_result`、`rag_result`、`visual_result`
- `master_agent` 依赖 `answer_draft` 和 `visual_result`

### 13.4 为什么 `visual_agent` 受 `sql_agent` 限制

因为 `visual_agent` 只能画 SQL 已经算出来的指标。

所以如果 `sql_agent` 没有产出：

- 时间序列指标
- 更细维度对比指标
- SKU/版本比较指标

那么 `visual_agent` 也不可能凭空画出对应图表。

---

## 14. 当前实现中的关键设计取舍

### 14.1 当前仍保留 fallback 的节点

- `router_agent`
- `rag_agent`
- `answer_agent`
- `master_agent`

这些节点在大模型失败时，仍会用本地规则或本地整合兜底。

### 14.2 已移除 fallback 的节点

- `sql_agent`
- `visual_agent`

这两个节点现在更严格：

- 失败时直接返回空统计或空图表
- 不再使用确定性模板保底

### 14.3 当前实现的优点

- 各节点职责边界比旧架构清晰
- 工作流状态可观测
- 各节点输出协议明确
- 服务层统一封装最终结果，对前端协议稳定

### 14.4 当前实现的限制

- `visual_agent` 能力受 `sql_agent` 指标范围限制
- `sql_agent`、`visual_agent` 现在更依赖大模型稳定性
- 爬虫链路当前仍依赖附着已登录 Chrome 才能稳定访问京东
- `master_agent` 的重试上限虽然有默认值，但在 LLM 路径上仍主要依赖模型遵守提示

---

## 15. 一句话总括

当前这套多 Agent 分析链路，本质上是：

**前置数据准备 -> 路由决策 -> 统计/检索/可视化 -> 回答整合 -> 最终审查 -> 服务层统一封装。**

其中：

- `sql_agent` 提供统计骨架
- `rag_agent` 提供评论证据
- `visual_agent` 提供图表表达
- `answer_agent` 把结果组织成候选回答
- `master_agent` 决定这份回答是否可以交付

最终结果不是在工作流里直接拼出来的，而是由服务层统一组装后返回前端。
