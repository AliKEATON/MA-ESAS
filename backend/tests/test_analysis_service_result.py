from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.agents.answer_agent import AnswerAgent
from app.config import DEEPSEEK_API_KEY
from app.models.analysis_task import AnalysisTaskStatus
from app.schemas.agent_protocol import (
    ChartSeries,
    ChartSpec,
    DataContext,
    FinalAnalysisResponse,
    MasterDecision,
    MasterDecisionType,
    ProductContext,
    RAGAgentResult,
    ResponseStyle,
    RouteDecision,
    SQLAgentResult,
    SupportedChartType,
    VisualAgentResult,
    AnswerDraft,
)
from app.services.analysis_service import AnalysisService


def test_build_result_message_content_uses_new_sql_result_structure():
    task = SimpleNamespace(
        task_id="task-001",
        product=SimpleNamespace(external_product_id="SKU-001"),
    )
    report = SimpleNamespace(
        id=9,
        summary="这是一段摘要",
        statistics_json={
            "final_response": {"answer": "这是一段回答"},
            "sql_result": {
                "metrics": {
                    "score_summary": {
                        "total_count": 12,
                        "avg_score": 4.25,
                    }
                }
            },
        },
    )

    content = AnalysisService._build_result_message_content(task, report)

    assert "Task ID: task-001" in content
    assert "Total comments: 12" in content
    assert "Average score: 4.25" in content
    assert "Summary: 这是一段摘要" in content


def test_get_task_result_returns_sql_result_without_legacy_fields(monkeypatch):
    created_at = datetime.now(timezone.utc)
    task = SimpleNamespace(
        task_id="task-001",
        status=AnalysisTaskStatus.COMPLETED,
        progress=100,
        current_step="finalize",
        error_message=None,
        product=SimpleNamespace(
            id=88,
            source="jd",
            external_product_id="SKU-001",
            product_name="测试商品",
        ),
        report=SimpleNamespace(
            id=3,
            conversation_id=7,
            created_at=created_at,
            statistics_json={
                "product_context": {
                    "has_product": True,
                    "source": "jd",
                    "external_product_id": "SKU-001",
                    "product_id": 88,
                    "resolved_from": "bound_product",
                },
                "data_context": {
                    "data_ready": True,
                    "used_cache": True,
                    "crawler_triggered": False,
                    "vector_ready": True,
                    "last_crawled_at": "2026-04-19T08:00:00+00:00",
                },
                "final_response": {"answer": "这是最终回答", "charts": [], "meta": {"product_id": 88}},
                "route_decision": {"need_sql": True},
                "sql_result": {
                    "tool_calls": [{"tool": "get_bad_review_rate", "args": {"product_id": 88}}],
                    "metrics": {"bad_review_rate": 0.2},
                    "description": "该商品差评率约为20%。",
                },
                "visual_result": {"charts": []},
                "rag_result": {"queries": [], "evidence": [], "insight": "评论主要在吐槽物流。"},
                "answer_draft": {
                    "answer": "这是最终回答",
                    "answer_points": ["该商品差评率约为20%。"],
                },
                "master_decision": {
                    "decision": "pass",
                    "reason": "回答完整",
                    "missing_items": [],
                    "retry_from": None,
                },
                "retry_count": 1,
            },
            evidence_json=[
                {
                    "content": "物流太慢了",
                    "score": 1,
                    "dimension": "物流",
                    "similarity": 0.91,
                }
            ],
        ),
    )

    monkeypatch.setattr(AnalysisService, "get_task_by_task_id", lambda db, user_id, task_id: task)

    result = AnalysisService.get_task_result(db=None, user_id=1, task_id="task-001")

    assert result["result_ready"] is True
    assert result["sql_result"]["metrics"]["bad_review_rate"] == 0.2
    assert "sql_metrics" not in result
    assert "sql_description" not in result
    assert result["evidence"][0]["dimension"] == "物流"
    assert result["product_context"]["product_id"] == 88
    assert result["data_context"]["vector_ready"] is True
    assert result["master_decision"]["decision"] == "pass"
    assert result["retry_count"] == 1


def test_upsert_report_from_workflow_persists_full_workflow_state(monkeypatch):
    task = SimpleNamespace(
        id=5,
        task_id="task-002",
        user_id=1,
        product_id=88,
        conversation_id=7,
        report=None,
    )
    fake_db = SimpleNamespace(
        added=[],
        add=lambda obj: fake_db.added.append(obj),
        commit=lambda: None,
        refresh=lambda obj: None,
    )

    monkeypatch.setattr(AnalysisService, "_upsert_result_message", lambda db, task, report: None)

    workflow_state = {
        "product_context": ProductContext(
            has_product=True,
            source="jd",
            external_product_id="SKU-001",
            product_id=88,
            resolved_from="bound_product",
        ),
        "data_context": DataContext(
            data_ready=True,
            used_cache=True,
            crawler_triggered=False,
            vector_ready=True,
            last_crawled_at="2026-04-19T08:00:00+00:00",
        ),
        "route_decision": RouteDecision(
            need_sql=True,
            need_rag=True,
            need_visual=True,
            analysis_targets=["bad_review_rate", "bad_review_distribution"],
            response_style=ResponseStyle.PROFESSIONAL_ANALYSIS,
            reason="用户要求分析差评并结合图表说明。",
        ),
        "sql_result": SQLAgentResult(
            tool_calls=[{"tool": "get_bad_review_rate", "args": {"product_id": 88}}],
            metrics={"bad_review_rate": 0.2},
            description="该商品差评率约为20%。",
        ),
        "visual_result": VisualAgentResult(
            charts=[
                ChartSpec(
                    chart_id="chart_bad_review_distribution",
                    chart_type=SupportedChartType.PIE,
                    title="差评维度分布",
                    description="展示差评在不同维度上的占比。",
                    x_axis=[],
                    series=[ChartSeries(name="差评数量", data=[{"name": "物流", "value": 3}])],
                )
            ]
        ),
        "rag_result": RAGAgentResult(
            queries=["商品差评原因"],
            evidence=[
                {
                    "content": "物流太慢了",
                    "dimension": "物流",
                    "score": 1,
                    "similarity": 0.91,
                }
            ],
            insight="评论语义显示问题主要集中在物流。",
        ),
        "answer_draft": AnswerDraft(
            answer="这是最终回答",
            answer_points=["该商品差评率约为20%。"],
        ),
        "master_decision": MasterDecision(
            decision=MasterDecisionType.PASS,
            reason="回答完整",
            missing_items=[],
            retry_from=None,
        ),
        "retry_count": 1,
    }

    report = AnalysisService._upsert_report_from_workflow(fake_db, task, workflow_state)

    assert report.summary == "这是最终回答"
    assert report.statistics_json["product_context"]["product_id"] == 88
    assert report.statistics_json["data_context"]["vector_ready"] is True
    assert report.statistics_json["visual_result"]["charts"][0]["title"] == "差评维度分布"
    assert report.statistics_json["rag_result"]["insight"] == "评论语义显示问题主要集中在物流。"
    assert report.statistics_json["answer_draft"]["answer"] == "这是最终回答"
    assert report.statistics_json["master_decision"]["decision"] == "pass"
    assert report.statistics_json["retry_count"] == 1
    assert report.evidence_json[0]["dimension"] == "物流"
    assert report.statistics_json["final_response"]["answer"] == "这是最终回答"
    assert report.statistics_json["final_response"]["meta"]["product_id"] == 88


def test_build_final_response_uses_workflow_outputs():
    workflow_state = {
        "product_context": ProductContext(
            has_product=True,
            source="jd",
            external_product_id="SKU-001",
            product_id=88,
            resolved_from="bound_product",
        ),
        "sql_result": SQLAgentResult(
            tool_calls=[{"tool": "get_bad_review_rate", "args": {"product_id": 88}}],
            metrics={"bad_review_rate": 0.2},
            description="该商品差评率约为20%。",
        ),
        "visual_result": VisualAgentResult(
            charts=[
                ChartSpec(
                    chart_id="chart_bad_review_distribution",
                    chart_type=SupportedChartType.PIE,
                    title="差评维度分布",
                    description="展示差评在不同维度上的占比。",
                    x_axis=[],
                    series=[ChartSeries(name="差评数量", data=[{"name": "物流", "value": 3}])],
                )
            ]
        ),
        "rag_result": RAGAgentResult(
            queries=["商品差评原因"],
            evidence=[],
            insight="评论语义显示问题主要集中在物流。",
        ),
        "answer_draft": AnswerDraft(
            answer="这是最终回答",
            answer_points=["该商品差评率约为20%。"],
        ),
        "retry_count": 1,
    }

    final_response = AnalysisService._build_final_response(workflow_state)

    assert isinstance(final_response, FinalAnalysisResponse)
    assert final_response.answer == "这是最终回答"
    assert final_response.meta.product_id == 88
    assert final_response.meta.retry_count == 1
    assert final_response.meta.used_agents == [
        "router_agent",
        "sql_agent",
        "visual_agent",
        "rag_agent",
        "answer_agent",
        "master_agent",
    ]
    assert final_response.charts[0].title == "差评维度分布"


def test_process_task_marks_task_failed_and_records_error_message(monkeypatch):
    task = SimpleNamespace(
        task_id="task-failed-001",
        product_id=88,
        conversation_id=7,
        question="请分析差评原因",
        status=AnalysisTaskStatus.PENDING,
        current_step="rag_agent",
        progress=80,
    )

    class _FakeTaskQuery:
        """只为 process_task 提供任务查询结果。"""

        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return task

    class _FakeDb:
        """模拟最小数据库会话，供失败链路测试使用。"""

        def query(self, _model):
            return _FakeTaskQuery()

        def close(self):
            return None

    fake_db = _FakeDb()
    captured: dict[str, object] = {}

    def fake_set_task_state(db, target_task, **kwargs):
        """记录失败写回参数，验证异常会落到任务状态中。"""
        captured["db"] = db
        captured["task"] = target_task
        captured["kwargs"] = kwargs
        target_task.status = kwargs.get("status", target_task.status)
        target_task.current_step = kwargs.get("current_step", target_task.current_step)
        target_task.progress = kwargs.get("progress", target_task.progress)
        target_task.error_message = kwargs.get("error_message")
        return target_task

    monkeypatch.setattr("app.services.analysis_service.SessionLocal", lambda: fake_db)
    monkeypatch.setattr(
        "app.services.analysis_service.AnalysisWorkflow.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("向量检索失败")),
    )
    monkeypatch.setattr(AnalysisService, "_set_task_state", fake_set_task_state)
    monkeypatch.setattr(
        AnalysisService,
        "_upsert_failure_message",
        lambda db, target_task, message: captured.setdefault("failure_message", message),
    )

    AnalysisService.process_task("task-failed-001")

    assert captured["task"] is task
    assert captured["kwargs"]["status"] == AnalysisTaskStatus.FAILED
    assert captured["kwargs"]["current_step"] == "rag_agent"
    assert captured["kwargs"]["progress"] == 80
    assert captured["kwargs"]["error_message"] == "向量检索失败"
    assert captured["failure_message"] == "向量检索失败"


def test_failed_task_progress_and_result_expose_error_message(monkeypatch):
    task = SimpleNamespace(
        task_id="task-failed-002",
        status=AnalysisTaskStatus.FAILED,
        progress=80,
        current_step="rag_agent",
        error_message="向量检索失败",
        report=None,
    )

    monkeypatch.setattr(AnalysisService, "get_task_by_task_id", lambda db, user_id, task_id: task)

    progress = AnalysisService.get_task_progress(db=None, user_id=1, task_id="task-failed-002")
    result = AnalysisService.get_task_result(db=None, user_id=1, task_id="task-failed-002")

    assert progress["status"] == "failed"
    assert progress["current_step"] == "rag_agent"
    assert progress["error_message"] == "向量检索失败"
    assert result["result_ready"] is False
    assert result["status"] == "failed"
    assert result["current_step"] == "rag_agent"
    assert result["error_message"] == "向量检索失败"


@pytest.mark.skipif(not DEEPSEEK_API_KEY, reason="DEEPSEEK_API_KEY 未配置，跳过真实大模型测试")
def test_get_task_result_with_real_llm_answer_generation(monkeypatch):
    route_decision = RouteDecision(
        need_sql=True,
        need_rag=True,
        need_visual=True,
        analysis_targets=["bad_review_rate", "bad_review_distribution"],
        response_style=ResponseStyle.PROFESSIONAL_ANALYSIS,
        reason="用户要求分析差评并结合图表说明。",
    )
    sql_result = SQLAgentResult(
        tool_calls=[
            {"tool": "get_bad_review_rate", "args": {"product_id": 88}},
            {"tool": "get_bad_review_distribution", "args": {"product_id": 88}},
        ],
        metrics={
            "bad_review_rate": 0.2,
            "bad_review_distribution": {
                "物流": 3,
                "质量": 2,
            },
        },
        description="该商品差评率约为20%，差评主要集中在物流和质量维度。",
    )
    rag_result = RAGAgentResult(
        queries=["商品差评原因", "物流相关差评"],
        evidence=[
            {
                "content": "物流速度太慢，等了很久才到。",
                "dimension": "物流",
                "score": 1,
                "similarity": 0.91,
            },
            {
                "content": "做工一般，边角处理不够细致。",
                "dimension": "质量",
                "score": 2,
                "similarity": 0.88,
            },
        ],
        insight="评论语义显示，差评原因主要集中在物流时效和产品做工。",
    )
    visual_result = VisualAgentResult(
        charts=[
            ChartSpec(
                chart_id="chart_bad_review_distribution",
                chart_type=SupportedChartType.PIE,
                title="差评维度分布",
                description="展示差评在不同维度上的占比。",
                x_axis=[],
                series=[
                    ChartSeries(
                        name="差评数量",
                        data=[
                            {"name": "物流", "value": 3},
                            {"name": "质量", "value": 2},
                        ],
                    )
                ],
            )
        ]
    )

    answer_draft = AnswerAgent.run(
        question="请总结这个商品的差评情况，并结合图表说明。",
        route_decision=route_decision,
        sql_result=sql_result,
        rag_result=rag_result,
        visual_result=visual_result,
    )
    print("real_llm_answer_draft:", flush=True)
    print(answer_draft.model_dump_json(indent=2, exclude_none=True), flush=True)

    created_at = datetime.now(timezone.utc)
    task = SimpleNamespace(
        task_id="task-real-llm-001",
        status=AnalysisTaskStatus.COMPLETED,
        progress=100,
        current_step="finalize",
        error_message=None,
        product=SimpleNamespace(
            id=88,
            source="jd",
            external_product_id="SKU-REAL-001",
            product_name="真实测试商品",
        ),
        report=SimpleNamespace(
            id=11,
            conversation_id=17,
            created_at=created_at,
            statistics_json={
                "final_response": {
                    "answer": answer_draft.answer,
                    "charts": visual_result.model_dump()["charts"],
                    "meta": {
                        "product_id": 88,
                        "used_agents": ["router_agent", "sql_agent", "visual_agent", "rag_agent", "answer_agent"],
                        "retry_count": 0,
                    },
                },
                "route_decision": route_decision.model_dump(),
                "sql_result": sql_result.model_dump(),
            },
            evidence_json=rag_result.model_dump()["evidence"],
        ),
    )

    monkeypatch.setattr(AnalysisService, "get_task_by_task_id", lambda db, user_id, task_id: task)

    result = AnalysisService.get_task_result(db=None, user_id=1, task_id="task-real-llm-001")
    print("analysis_service_task_result:", flush=True)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str), flush=True)

    assert result["result_ready"] is True
    assert result["final_response"]["answer"] == answer_draft.answer
    assert result["product"]["product_id"] == 88
    assert result["sql_result"]["metrics"]["bad_review_rate"] == 0.2
