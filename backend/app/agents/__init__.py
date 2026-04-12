"""
backend/app/agents 包
LangGraph 多智能体工作流，负责核心 AI 分析逻辑。

模块说明：
- workflow.py      LangGraph 工作流编排，定义节点与边
- router_agent.py  意图分类 Agent，判断用户问题需要哪种分析
- sql_agent.py     SQL 聚合 Agent，通过 DuckDB 执行数据统计
- rag_agent.py     RAG 检索 Agent，通过 ChromaDB 进行语义检索
- synthesizer.py   结果合成 Agent，整合 SQL 与 RAG 结果，调用 LLM 生成答案
"""
