"""RAG Agent：围绕评论证据做检索规划、证据收集与洞察总结。"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.agents.llm import LLMUnavailableError, invoke_structured_output
from app.models import Comment
from app.schemas.agent_protocol import RAGAgentResult, RAGEvidenceItem, RAGQueryPlan
from app.services.vector_store_service import VectorStoreService
from app.utils.logger import logger


class RAGAgent:
    """商品评论语义分析 Agent，负责证据检索与语义洞察输出。"""

    _KNOWN_DIMENSIONS = ("物流", "质量", "售后", "综合", "包装", "价格", "服务")

    # 先规划检索 query，再基于 query 拉取证据，可提高语义检索稳定性。
    QUERY_PLAN_PROMPT = """
你是商品评论语义分析专家 rag_agent 的检索规划器。

你的职责：
1. 根据用户问题、路由意图和已有统计结论，生成用于评论向量检索的查询列表。
2. 查询只服务于“找证据”，而不是直接生成结论。
3. 输出必须严格符合 RAGQueryPlan 结构。

必须遵守：
- queries 第一项应尽量保留用户原问题的核心表达。
- 可以补充 1-3 个更聚焦的检索查询，例如某个维度、某类吐槽、某类体验问题。
- 如果 route_reason 或 sql_result_description 已经提示了重点维度或重点问题，可以把它们改写成更适合检索评论证据的查询。
- 查询应尽量短、具体、可用于召回评论，不要写成长句分析结论。
- 不要直接输出“差评率是多少”“请给我总结原因”这类结论式问句，优先输出“物流吐槽”“质量做工问题”“售后体验问题”这类证据导向查询。
- 不要生成与商品评论无关的查询。
- 不要输出 markdown，不要输出额外解释。
"""

    SYSTEM_PROMPT = """
你是商品评论语义分析专家 rag_agent。

你的职责：
1. 基于用户问题和已检索到的评论证据，总结评论语义层面的原因与洞察。
2. 不要生成最终面向用户的完整回答，只生成 RAGAgentResult。
3. evidence 字段必须只保留输入中提供的证据，不得编造新的评论内容。
4. insight 必须是简洁中文，总结用户最关心的评论原因、体验反馈或集中问题。
5. insight_points 必须输出 2-4 条可被下游 answer_agent 直接消费的短结论；如果有效证据不足，可以少于 2 条，但不能编造。

必须遵守：
- queries 应保留实际使用的检索查询。
- evidence 只能来自输入中的 candidate_evidence。
- insight 只基于 evidence 做归纳，不得脱离证据推断具体数字或结论。
- insight_points 只能基于 evidence 和 insight 提炼，优先总结“主要问题维度、典型原因、体验反馈、证据不足提示”。
- insight_points 每条都要是短句，不要写成长段，不要写成面向用户的整段回答。
- 如果证据不足，要在 insight 中明确说明，而不是编造结论。
- 输出必须严格符合 RAGAgentResult 结构。
- 不要输出 markdown，不要输出额外解释。
"""

    @staticmethod
    def run(
        db: Session,
        product_id: int,
        question: str,
        analysis_targets: list[str] | None = None,
        route_reason: str | None = None,
        response_style: str | None = None,
        sql_result_description: str | None = None,
        limit: int = 5,
    ) -> RAGAgentResult:
        """执行评论语义检索主流程并输出标准 RAG 结果。"""
        # 先判断是否存在评论数据，避免无意义地进入向量检索与总结阶段。
        comments = db.query(Comment).filter(Comment.product_id == product_id).all()
        if not comments:
            return RAGAgentResult(
                queries=[question.strip()],
                evidence=[],
                insight="当前没有可用评论，无法生成评论语义洞察。",
                insight_points=[],
            )

        analysis_targets = analysis_targets or []
        VectorStoreService.ensure_product_vectorized(db, product_id)
        queries = RAGAgent._build_vector_queries(
            question=question,
            analysis_targets=analysis_targets,
            route_reason=route_reason,
            response_style=response_style,
            sql_result_description=sql_result_description,
        )
        vector_evidence = VectorStoreService.query_product_comments(
            db=db,
            product_id=product_id,
            queries=queries,
            limit=limit,
        )
        if vector_evidence:
            evidence = [RAGEvidenceItem(**item) for item in vector_evidence]
            evidence = RAGAgent._rerank_evidence_by_intent(
                evidence=evidence,
                question=question,
                analysis_targets=analysis_targets,
                route_reason=route_reason,
                sql_result_description=sql_result_description,
                queries=queries,
                limit=limit,
            )
            logger.info(
                "RAG agent used vector retrieval: product_id={} evidence_count={}",
                product_id,
                len(evidence),
            )
            return RAGAgent._llm_summarize(
                question=question,
                queries=queries,
                evidence=evidence,
                route_reason=route_reason,
                response_style=response_style,
                sql_result_description=sql_result_description,
            )

        keywords = RAGAgent._build_keywords(question, analysis_targets)
        scored_items: list[tuple[float, Comment]] = []
        for comment in comments:
            score = RAGAgent._score_comment(comment, keywords)
            scored_items.append((score, comment))

        scored_items.sort(
            key=lambda item: (
                item[0],
                item[1].score if item[1].score is not None else 0,
                item[1].created_at,
            ),
            reverse=True,
        )
        evidence = [
            RAGEvidenceItem(
                content=comment.content,
                score=comment.score,
                dimension=comment.dimension,
                similarity=round(score, 4),
            )
            for score, comment in scored_items[:limit]
        ]
        evidence = RAGAgent._rerank_evidence_by_intent(
            evidence=evidence,
            question=question,
            analysis_targets=analysis_targets,
            route_reason=route_reason,
            sql_result_description=sql_result_description,
            queries=queries,
            limit=limit,
        )
        logger.info(
            "RAG agent used keyword fallback retrieval: product_id={} evidence_count={} keywords={}",
            product_id,
            len(evidence),
            keywords,
        )
        return RAGAgent._llm_summarize(
            question=question,
            queries=queries,
            evidence=evidence,
            route_reason=route_reason,
            response_style=response_style,
            sql_result_description=sql_result_description,
        )

    @staticmethod
    def _build_vector_queries(
        question: str,
        analysis_targets: list[str],
        route_reason: str | None = None,
        response_style: str | None = None,
        sql_result_description: str | None = None,
    ) -> list[str]:
        """先由大模型规划检索 query，再在失败时回退到规则生成。"""
        payload = {
            "question": question,
            "analysis_targets": analysis_targets,
            "route_reason": route_reason,
            "response_style": response_style,
            "sql_result_description": sql_result_description,
        }
        try:
            plan = invoke_structured_output(
                system_prompt=RAGAgent.QUERY_PLAN_PROMPT,
                payload=payload,
                schema=RAGQueryPlan,
                temperature=0.2,
            )
            queries = [query.strip() for query in plan.queries if query.strip()]
            return queries or [question.strip()]
        except LLMUnavailableError as exc:
            logger.warning("RAGAgent query planning falling back to deterministic queries: {}", exc)
        except Exception as exc:
            logger.exception("RAGAgent query planning failed, fallback enabled: {}", exc)
        queries = [question.strip()]
        for target in analysis_targets:
            normalized = str(target).strip()
            if normalized and normalized not in queries:
                queries.append(normalized)
        return queries

    @staticmethod
    def _llm_summarize(
        question: str,
        queries: list[str],
        evidence: list[RAGEvidenceItem],
        route_reason: str | None = None,
        response_style: str | None = None,
        sql_result_description: str | None = None,
    ) -> RAGAgentResult:
        """基于已检索证据生成结构化评论洞察。"""
        payload = {
            "question": question,
            "queries": queries,
            "route_reason": route_reason,
            "response_style": response_style,
            "sql_result_description": sql_result_description,
            "candidate_evidence": [item.model_dump() for item in evidence],
            "requirements": {
                "max_evidence_count": len(evidence),
                "must_keep_evidence_verbatim": True,
            },
        }
        try:
            result = invoke_structured_output(
                system_prompt=RAGAgent.SYSTEM_PROMPT,
                payload=payload,
                schema=RAGAgentResult,
                temperature=0.2,
            )
            if not result.evidence:
                result.evidence = evidence
            result.insight_points = RAGAgent._normalize_insight_points(
                insight_points=result.insight_points,
                insight=result.insight,
            )
            return result
        except LLMUnavailableError as exc:
            logger.warning("RAGAgent falling back to rule-based insight: {}", exc)
        except Exception as exc:
            logger.exception("RAGAgent structured generation failed, fallback enabled: {}", exc)
        fallback_insight = RAGAgent._build_insight(evidence)
        return RAGAgentResult(
            queries=queries,
            evidence=evidence,
            insight=fallback_insight,
            insight_points=RAGAgent._normalize_insight_points(
                insight_points=[],
                insight=fallback_insight,
            ),
        )

    @staticmethod
    def _build_keywords(question: str, analysis_targets: list[str]) -> list[str]:
        """在向量检索失效时，从问题和路由目标中提取关键词。"""
        # 关键词兜底仅用于召回排序，不承担最终分析结论生成。
        keywords: list[str] = []
        for target in analysis_targets:
            cleaned_target = str(target).strip()
            if cleaned_target and cleaned_target not in keywords:
                keywords.append(cleaned_target)
        normalized_question = re.sub(r"[\s,，。！？!?.、]+", " ", question)
        for token in normalized_question.split():
            cleaned = token.strip()
            if cleaned and len(cleaned) >= 2 and cleaned not in keywords:
                keywords.append(cleaned)
        return keywords

    @staticmethod
    def _score_comment(comment: Comment, keywords: list[str]) -> float:
        """对评论做简单关键词打分，用于关键词兜底排序。"""
        content = comment.content or ""
        dimension = comment.dimension or ""
        score = 0.0
        for keyword in keywords:
            if keyword in content:
                score += 1.2
            if keyword and keyword == dimension:
                score += 1.5
        if comment.score is not None and comment.score <= 2:
            score += 0.2
        return score

    @staticmethod
    def _build_insight(evidence: list[RAGEvidenceItem]) -> str:
        """在大模型不可用时，根据证据构造兜底语义洞察。"""
        if not evidence:
            return "未检索到足够相关的评论证据。"
        dimension_counter: dict[str, int] = {}
        for item in evidence:
            dimension = item.dimension or "未分类"
            dimension_counter[dimension] = dimension_counter.get(dimension, 0) + 1
        top_dimension = max(dimension_counter.items(), key=lambda item: item[1])[0]
        return f"从检索到的评论语义看，当前用户反馈主要集中在 {top_dimension} 相关问题。"

    @staticmethod
    def _normalize_insight_points(insight_points: list[str], insight: str) -> list[str]:
        """对洞察结论点做最小收敛，保证下游 answer_agent 可稳定消费。"""
        normalized_points: list[str] = []
        seen: set[str] = set()
        for point in insight_points:
            compact_point = " ".join(str(point).split())
            if not compact_point or compact_point in seen:
                continue
            normalized_points.append(compact_point)
            seen.add(compact_point)
            if len(normalized_points) >= 4:
                return normalized_points

        if normalized_points:
            return normalized_points

        compact_insight = " ".join(str(insight).split())
        if compact_insight and compact_insight not in seen:
            normalized_points.append(compact_insight)
        return normalized_points[:4]

    @staticmethod
    def _rerank_evidence_by_intent(
        evidence: list[RAGEvidenceItem],
        question: str,
        analysis_targets: list[str],
        route_reason: str | None,
        sql_result_description: str | None,
        queries: list[str],
        limit: int,
    ) -> list[RAGEvidenceItem]:
        """按问题意图重排证据，减少与当前问题无关的评论混入 LLM 视野。"""
        if not evidence:
            return []

        intent = RAGAgent._infer_evidence_intent(
            question=question,
            analysis_targets=analysis_targets,
            route_reason=route_reason,
            sql_result_description=sql_result_description,
            queries=queries,
        )
        scored_items = [
            (RAGAgent._score_evidence_for_intent(item, intent), index, item)
            for index, item in enumerate(evidence)
        ]
        scored_items.sort(key=lambda row: (row[0], -row[1]), reverse=True)
        return [item for _, _, item in scored_items[:limit]]

    @staticmethod
    def _infer_evidence_intent(
        question: str,
        analysis_targets: list[str],
        route_reason: str | None,
        sql_result_description: str | None,
        queries: list[str],
    ) -> dict[str, object]:
        """从问题、路由原因和统计提示中提取最小意图画像。"""
        text_parts = [
            question,
            route_reason or "",
            sql_result_description or "",
            " ".join(analysis_targets),
            " ".join(queries),
        ]
        joined_text = " ".join(text_parts)
        lower_text = joined_text.lower()

        wants_negative = any(
            marker in joined_text for marker in ("差评", "吐槽", "问题", "抱怨", "不足", "缺点", "负面")
        ) or any("bad_review" in str(target) for target in analysis_targets)
        wants_positive = any(
            marker in joined_text for marker in ("好评", "优点", "满意", "亮点", "推荐", "正面")
        )

        target_dimensions = {
            dimension
            for dimension in RAGAgent._KNOWN_DIMENSIONS
            if dimension in joined_text
        }
        if "dimension_stats" in analysis_targets and "维度" in joined_text:
            target_dimensions.update(
                dimension
                for dimension in RAGAgent._KNOWN_DIMENSIONS
                if dimension in (sql_result_description or "")
            )

        return {
            "wants_negative": wants_negative and not wants_positive,
            "wants_positive": wants_positive and not wants_negative,
            "target_dimensions": target_dimensions,
            "keyword_text": lower_text,
        }

    @staticmethod
    def _score_evidence_for_intent(item: RAGEvidenceItem, intent: dict[str, object]) -> float:
        """结合维度、情感和文本命中情况为证据打分。"""
        score = float(item.similarity or 0)
        content = (item.content or "").lower()
        dimension = item.dimension or ""
        numeric_score = float(item.score) if item.score is not None else None

        target_dimensions = intent.get("target_dimensions", set())
        if isinstance(target_dimensions, set) and target_dimensions:
            if dimension in target_dimensions:
                score += 0.35
            elif dimension:
                score -= 0.08

        keyword_text = str(intent.get("keyword_text", ""))
        if dimension and dimension.lower() in keyword_text:
            score += 0.12
        if keyword_text and any(token in content for token in ("物流", "质量", "售后", "做工", "发货", "配送", "客服")):
            hit_count = sum(1 for token in ("物流", "质量", "售后", "做工", "发货", "配送", "客服") if token in keyword_text and token in content)
            score += min(0.18, hit_count * 0.06)

        if numeric_score is not None:
            if intent.get("wants_negative"):
                if numeric_score <= 2:
                    score += 0.28
                elif numeric_score >= 4:
                    score -= 0.18
            elif intent.get("wants_positive"):
                if numeric_score >= 4:
                    score += 0.22
                elif numeric_score <= 2:
                    score -= 0.12

        return round(score, 4)
