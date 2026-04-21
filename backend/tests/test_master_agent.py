from __future__ import annotations

import pytest

from app.agents.llm import LLMUnavailableError
from app.agents.master_agent import MasterAgent
from app.agents.workflow import AnalysisWorkflow
from app.config import DEEPSEEK_API_KEY
from app.schemas.agent_protocol import (
    AnswerDraft,
    ChartSeries,
    ChartSpec,
    MasterDecision,
    MasterDecisionType,
    ResponseStyle,
    RouteDecision,
    SupportedChartType,
    VisualAgentResult,
)


def _build_route_decision(*, need_visual: bool = False) -> RouteDecision:
    return RouteDecision(
        need_sql=True,
        need_rag=False,
        need_visual=need_visual,
        analysis_targets=["bad_review_rate"],
        response_style=ResponseStyle.PROFESSIONAL_ANALYSIS,
        reason="?? master_agent ??",
    )


def test_master_agent_run_passes_question_and_answer_points_to_llm(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        assert payload["question"] == "????????????????"
        assert payload["answer_text"] == "??????"
        assert payload["answer_points"] == ["??1", "??2"]
        return MasterDecision(
            decision=MasterDecisionType.PASS,
            reason="????",
            missing_items=[],
            retry_from=None,
        )

    monkeypatch.setattr("app.agents.master_agent.invoke_structured_output", fake_invoke_structured_output)

    result = MasterAgent.run(
        question="????????????????",
        route_decision=_build_route_decision(),
        answer_text="??????",
        answer_points=["??1", "??2"],
    )

    assert result.decision == MasterDecisionType.PASS
    assert result.missing_items == []


def test_master_agent_fallback_marks_empty_answer_points_as_missing(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        raise LLMUnavailableError("force fallback")

    monkeypatch.setattr("app.agents.master_agent.invoke_structured_output", fake_invoke_structured_output)

    result = MasterAgent.run(
        question="????????????????",
        route_decision=_build_route_decision(),
        answer_text="??????",
        answer_points=[],
        retry_count=0,
        max_retry=1,
    )

    assert result.decision == MasterDecisionType.RETRY
    assert result.retry_from is not None
    assert result.retry_from.value == "answer_agent"
    assert "answer_points" in result.missing_items


def test_master_agent_fallback_marks_weak_answer_points_as_missing(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        raise LLMUnavailableError("force fallback")

    monkeypatch.setattr("app.agents.master_agent.invoke_structured_output", fake_invoke_structured_output)

    result = MasterAgent.run(
        question="????????????????",
        route_decision=_build_route_decision(),
        answer_text="??????",
        answer_points=["??", "???"],
        retry_count=0,
        max_retry=1,
    )

    assert result.decision == MasterDecisionType.RETRY
    assert result.retry_from is not None
    assert result.retry_from.value == "answer_agent"
    assert "answer_points" in result.missing_items


def test_master_agent_fallback_marks_off_topic_answer_as_missing(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        raise LLMUnavailableError("force fallback")

    monkeypatch.setattr("app.agents.master_agent.invoke_structured_output", fake_invoke_structured_output)

    result = MasterAgent.run(
        question="analyze logistics issues",
        route_decision=_build_route_decision(),
        answer_text="generic summary only",
        answer_points=["specific evidence point"],
        retry_count=0,
        max_retry=1,
    )

    assert result.decision == MasterDecisionType.RETRY
    assert result.retry_from is not None
    assert result.retry_from.value == "answer_agent"
    assert "answer" in result.missing_items


def test_workflow_master_agent_passes_question_and_answer_points(monkeypatch):
    def fake_run(*, question, route_decision, answer_text, answer_points, visual_result, retry_count, max_retry):
        assert question == "?????????"
        assert answer_text == "??????"
        assert answer_points == ["??1", "??2"]
        assert retry_count == 0
        assert max_retry == 1
        return MasterDecision(
            decision=MasterDecisionType.PASS,
            reason="????",
            missing_items=[],
            retry_from=None,
        )

    monkeypatch.setattr("app.agents.workflow.MasterAgent.run", fake_run)

    result = AnalysisWorkflow._master_agent(
        {
            "user_message": "?????????",
            "route_decision": _build_route_decision(),
            "answer_draft": AnswerDraft(
                answer="??????",
                answer_points=["??1", "??2"],
            ),
            "retry_count": 0,
            "max_retry": 1,
        }
    )

    assert result["master_decision"].decision == MasterDecisionType.PASS


@pytest.mark.skipif(not DEEPSEEK_API_KEY, reason="DEEPSEEK_API_KEY ?????????????")
def test_master_agent_with_real_llm():
    visual_result = VisualAgentResult(
        charts=[
            ChartSpec(
                chart_id="chart_bad_review_distribution",
                chart_type=SupportedChartType.PIE,
                title="??????",
                description="????????????????",
                x_axis=[],
                series=[
                    ChartSeries(
                        name="????",
                        data=[
                            {"name": "??", "value": 3},
                            {"name": "??", "value": 2},
                        ],
                    )
                ],
            )
        ]
    )

    result = MasterAgent.run(
        question="?????????????????????",
        route_decision=_build_route_decision(need_visual=True),
        answer_text="????????20%??????????????????????????????",
        answer_points=[
            "?????20%",
            "????????????",
            "??????????",
        ],
        visual_result=visual_result,
        retry_count=0,
        max_retry=1,
    )
    print("real_llm_master_agent_result:", flush=True)
    print(result.model_dump_json(indent=2, exclude_none=True), flush=True)

    assert isinstance(result.decision, MasterDecisionType)
    assert isinstance(result.reason, str)
    assert result.reason.strip()
