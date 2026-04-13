"""RAG-style evidence retrieval for analysis comments."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Comment
from app.utils.logger import logger


class RAGAgent:
    """负责为分析任务检索更相关的评论证据。"""

    @staticmethod
    def retrieve_evidence(
        db: Session,
        product_id: int,
        question: str,
        route_plan: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """按问题和路由计划检索指定商品的相关评论证据。"""
        comments = db.query(Comment).filter(Comment.product_id == product_id).all()
        if not comments:
            return []

        keywords = RAGAgent._build_keywords(question, route_plan or {})
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
            {
                "content": comment.content,
                "score": comment.score,
                "dimension": comment.dimension,
                "similarity": round(score, 4),
            }
            for score, comment in scored_items[:limit]
        ]
        logger.info(
            "RAG agent retrieved evidence: product_id={} evidence_count={} keywords={}",
            product_id,
            len(evidence),
            keywords,
        )
        return evidence

    @staticmethod
    def _build_keywords(question: str, route_plan: dict[str, Any]) -> list[str]:
        """从问题和路由计划中提取检索关键词。"""
        keywords: list[str] = []
        for dimension in route_plan.get("focus_dimensions", []):
            if dimension and dimension != "综合":
                keywords.append(str(dimension))

        for query in route_plan.get("rag_queries", []):
            for token in re.split(r"[\s,，。！？!?.、]+", str(query)):
                cleaned = token.strip()
                if cleaned and len(cleaned) >= 2 and cleaned not in keywords:
                    keywords.append(cleaned)

        normalized_question = re.sub(r"[\s,，。！？!?.、]+", " ", question)
        for token in normalized_question.split():
            cleaned = token.strip()
            if cleaned and len(cleaned) >= 2 and cleaned not in keywords:
                keywords.append(cleaned)
        return keywords

    @staticmethod
    def _score_comment(comment: Comment, keywords: list[str]) -> float:
        """根据关键词命中和评论特征计算相关性分数。"""
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
