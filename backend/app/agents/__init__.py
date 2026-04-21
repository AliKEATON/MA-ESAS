"""app.agents package.

This package now uses the new multi-agent collaboration architecture.
Current key modules:
- state.py         Shared state definitions for LangGraph multi-agent workflow
- workflow.py      New multi-agent workflow orchestration
- router_agent.py  Router/planner agent
- sql_agent.py     Structured statistics agent
- rag_agent.py     Comment semantic analysis agent
- visual_agent.py  Visualization generation agent
- answer_agent.py  Answer aggregation agent
- master_agent.py  Final validation agent
"""
