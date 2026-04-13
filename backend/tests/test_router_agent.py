from __future__ import annotations

from app.main import app
from app.models import AnalysisTask, Comment, Conversation, Message, Product, User
from app.models.analysis_task import AnalysisTaskStatus
from app.models.conversation import MessageRole, MessageType
from app.models.product import ProductStatus
from app.agents.rag_agent import RAGAgent
from app.agents.router_agent import RouterAgent
from app.services.analysis_service import AnalysisService


def test_router_agent_routes_negative_review_question() -> None:
    """差评类问题应被路由到负面评价分析模式。"""
    plan = RouterAgent.route_question("请分析这款耳机的差评，尤其是物流和售后问题。")

    assert plan["analysis_mode"] == "negative_review"
    assert "物流" in plan["focus_dimensions"]
    assert "售后" in plan["focus_dimensions"]
    assert "重点维度聚合" in plan["sql_tasks"]


def test_router_agent_routes_value_assessment_question() -> None:
    """值不值得买类问题应被路由到性价比评估模式。"""
    plan = RouterAgent.route_question("这款产品现在还值得买吗？重点看看价格和质量。")

    assert plan["analysis_mode"] == "value_assessment"
    assert "价格" in plan["focus_dimensions"]
    assert "质量" in plan["focus_dimensions"]
    assert "性价比评估" in plan["sql_tasks"]


def test_analysis_report_contains_router_plan(client) -> None:
    """基础分析报告应把路由计划写入 statistics_json。"""
    db = app.state.testing_sessionmaker()
    try:
        user = User(username="router_user", email="router@example.com", hashed_password="hashed")
        db.add(user)
        db.flush()

        product = Product(
            source="jd",
            external_product_id="1001",
            product_url="https://item.jd.com/1001.html",
            product_name="测试商品",
            crawl_status=ProductStatus.COMPLETED,
        )
        db.add(product)
        db.flush()

        conversation = Conversation(user_id=user.id, bound_product_id=product.id, title="路由测试")
        db.add(conversation)
        db.flush()

        message = Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="请分析这款商品的差评，重点看质量问题。",
            message_type=MessageType.ANALYSIS_REQUEST,
        )
        db.add(message)
        db.flush()

        task = AnalysisTask(
            task_id="router-task-1",
            user_id=user.id,
            conversation_id=conversation.id,
            product_id=product.id,
            trigger_message_id=message.id,
            question=message.content,
            status=AnalysisTaskStatus.PROCESSING,
            current_step="synthesizer",
            progress=90,
        )
        db.add(task)
        db.flush()

        db.add(
            Comment(
                product_id=product.id,
                content="质量一般，耳罩容易开裂。",
                score=2,
                dimension="质量",
                dimension_score=2,
                source_comment_id="comment-1",
            )
        )
        db.commit()
        db.refresh(task)

        route_plan = AnalysisService._build_router_plan(task.question)
        evidence = RAGAgent.retrieve_evidence(
            db=db,
            product_id=product.id,
            question=task.question,
            route_plan=route_plan,
        )
        report = AnalysisService._upsert_basic_report(db, task, route_plan, evidence)

        assert report.statistics_json["router_plan"]["analysis_mode"] == "negative_review"
        assert "质量" in report.statistics_json["router_plan"]["focus_dimensions"]
        assert "重点维度：质量。" in report.summary
        assert "结论：本次属于差评分析" in report.summary
        assert report.charts_config["score_distribution"]["title"] == "评分分布"
        assert report.charts_config["dimension_avg_score"]["xAxis"] == ["质量"]
        assert report.charts_config["dimension_bad_rate"]["series"] == [100.0]
    finally:
        db.close()
