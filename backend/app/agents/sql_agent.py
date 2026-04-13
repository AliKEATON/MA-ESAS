"""DuckDB-backed SQL agent for comment aggregation."""

from __future__ import annotations

from typing import Any

import duckdb
import pandas as pd
from sqlalchemy.orm import Session

from app.models import Comment
from app.utils.logger import logger


class SQLAgent:
    """负责使用 DuckDB 对评论数据做统计聚合。"""

    @staticmethod
    def aggregate_comments(
        db: Session,
        product_id: int,
        route_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """聚合指定商品的评论，生成更结构化的统计结果。"""
        comments = db.query(Comment).filter(Comment.product_id == product_id).all()
        if not comments:
            return {
                "total_count": 0,
                "avg_score": 0,
                "low_score_count": 0,
                "bad_rate": 0,
                "score_distribution": {score: 0 for score in range(1, 6)},
                "dimension_stats": {},
                "focus_dimension_stats": {},
            }

        rows = [
            {
                "score": item.score,
                "dimension": item.dimension or "未分类",
                "dimension_score": item.dimension_score if item.dimension_score is not None else item.score,
            }
            for item in comments
        ]
        comments_df = pd.DataFrame(rows)
        conn = duckdb.connect(":memory:")
        try:
            conn.register("comments_df", comments_df)
            base_stats = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_count,
                    ROUND(AVG(score), 2) AS avg_score,
                    SUM(CASE WHEN score <= 2 THEN 1 ELSE 0 END) AS low_score_count,
                    ROUND(AVG(CASE WHEN score <= 2 THEN 1.0 ELSE 0.0 END), 4) AS bad_rate
                FROM comments_df
                """
            ).fetchone()

            score_rows = conn.execute(
                """
                SELECT score, COUNT(*) AS count
                FROM comments_df
                GROUP BY score
                ORDER BY score
                """
            ).fetchall()
            score_distribution = {score: 0 for score in range(1, 6)}
            for score, count in score_rows:
                score_distribution[int(score)] = int(count)

            dimension_rows = conn.execute(
                """
                SELECT
                    dimension,
                    COUNT(*) AS comment_count,
                    ROUND(AVG(score), 2) AS avg_score,
                    ROUND(AVG(CASE WHEN score <= 2 THEN 1.0 ELSE 0.0 END), 4) AS bad_rate
                FROM comments_df
                GROUP BY dimension
                ORDER BY comment_count DESC, dimension ASC
                """
            ).fetchall()
            dimension_stats = {
                str(dimension): {
                    "comment_count": int(comment_count),
                    "avg_score": float(avg_score or 0),
                    "bad_rate": float(bad_rate or 0),
                }
                for dimension, comment_count, avg_score, bad_rate in dimension_rows
            }

            focus_dimension_stats: dict[str, Any] = {}
            for dimension in (route_plan or {}).get("focus_dimensions", []):
                if dimension in dimension_stats:
                    focus_dimension_stats[dimension] = dimension_stats[dimension]

            stats = {
                "total_count": int(base_stats[0] or 0),
                "avg_score": float(base_stats[1] or 0),
                "low_score_count": int(base_stats[2] or 0),
                "bad_rate": float(base_stats[3] or 0),
                "score_distribution": score_distribution,
                "dimension_stats": dimension_stats,
                "focus_dimension_stats": focus_dimension_stats,
            }
            logger.info(
                "SQL agent aggregated comments: product_id={} total_count={} focus_dimensions={}",
                product_id,
                stats["total_count"],
                list(focus_dimension_stats.keys()),
            )
            return stats
        finally:
            conn.close()
