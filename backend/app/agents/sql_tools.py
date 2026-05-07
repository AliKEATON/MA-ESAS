"""SQL Agent 统计工具集合：负责评论数据加载与受控统计实现。"""

from __future__ import annotations

from typing import Any

import duckdb
import pandas as pd
from sqlalchemy.orm import Session

from app.models import Comment


class SQLMetricsTools:
    """封装 SQL Agent 使用的评论统计工具。"""

    @staticmethod
    def load_comments_df(db: Session, product_id: int) -> pd.DataFrame:
        """载入指定商品评论为 DataFrame，供受控统计工具执行。"""
        comments = db.query(Comment).filter(Comment.product_id == product_id).all()
        if not comments:
            return pd.DataFrame(columns=["score", "dimension", "dimension_score", "content", "comment_time"])

        return pd.DataFrame(
            [
                {
                    "score": item.score,
                    "dimension": item.dimension or "未分类",
                    "dimension_score": item.dimension_score if item.dimension_score is not None else item.score,
                    "content": item.content or "",
                    "comment_time": item.comment_time,
                }
                for item in comments
            ]
        )

    @staticmethod
    def get_score_summary(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        """统计商品评论总量、平均分和低分评论数量。"""
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_count,
                ROUND(AVG(score), 2) AS avg_score,
                SUM(CASE WHEN score <= 2 THEN 1 ELSE 0 END) AS low_score_count
            FROM comments_df
            """
        ).fetchone()
        return {
            "score_summary": {
                "total_count": int(row[0] or 0),
                "avg_score": float(row[1] or 0),
                "low_score_count": int(row[2] or 0),
            }
        }

    @staticmethod
    def get_score_distribution(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        """统计 1 到 5 分的整体评分分布。"""
        rows = conn.execute(
            """
            SELECT score, COUNT(*) AS count
            FROM comments_df
            GROUP BY score
            ORDER BY score
            """
        ).fetchall()
        distribution = {score: 0 for score in range(1, 6)}
        for score, count in rows:
            distribution[int(score)] = int(count)
        return {"score_distribution": distribution}

    @staticmethod
    def get_bad_review_rate(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        """统计差评在全部评论中的占比。"""
        row = conn.execute(
            """
            SELECT ROUND(AVG(CASE WHEN score <= 2 THEN 1.0 ELSE 0.0 END), 4) AS bad_review_rate
            FROM comments_df
            """
        ).fetchone()
        return {"bad_review_rate": float(row[0] or 0)}

    @staticmethod
    def get_positive_review_rate(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        """统计好评数量及其在全部评论中的占比。"""
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_count,
                SUM(CASE WHEN score >= 4 THEN 1 ELSE 0 END) AS positive_count,
                ROUND(AVG(CASE WHEN score >= 4 THEN 1.0 ELSE 0.0 END), 4) AS positive_rate
            FROM comments_df
            """
        ).fetchone()
        return {
            "positive_review_rate": {
                "total_count": int(row[0] or 0),
                "positive_count": int(row[1] or 0),
                "positive_rate": float(row[2] or 0),
            }
        }

    @staticmethod
    def get_score_band_distribution(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        """按好评、中评、差评三个分段汇总评论数量。"""
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN score >= 4 THEN 1 ELSE 0 END) AS positive_count,
                SUM(CASE WHEN score = 3 THEN 1 ELSE 0 END) AS neutral_count,
                SUM(CASE WHEN score <= 2 THEN 1 ELSE 0 END) AS negative_count
            FROM comments_df
            """
        ).fetchone()
        return {
            "score_band_distribution": {
                "positive": int(row[0] or 0),
                "neutral": int(row[1] or 0),
                "negative": int(row[2] or 0),
            }
        }

    @staticmethod
    def get_dimension_stats(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        """统计各分析维度的评论量、均分和差评情况。"""
        rows = conn.execute(
            """
            SELECT
                dimension,
                COUNT(*) AS comment_count,
                ROUND(AVG(score), 2) AS avg_score,
                ROUND(AVG(CASE WHEN score <= 2 THEN 1.0 ELSE 0.0 END), 4) AS bad_review_rate,
                SUM(CASE WHEN score <= 2 THEN 1 ELSE 0 END) AS bad_review_count
            FROM comments_df
            GROUP BY dimension
            ORDER BY comment_count DESC, dimension ASC
            """
        ).fetchall()
        return {
            "dimension_stats": {
                str(dimension): {
                    "comment_count": int(comment_count),
                    "avg_score": float(avg_score or 0),
                    "bad_review_rate": float(bad_review_rate or 0),
                    "bad_review_count": int(bad_review_count or 0),
                }
                for dimension, comment_count, avg_score, bad_review_rate, bad_review_count in rows
            }
        }

    @staticmethod
    def get_bad_review_distribution(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        """提取各维度下的差评数量分布。"""
        dimension_stats = SQLMetricsTools.get_dimension_stats(conn).get("dimension_stats", {})
        return {
            "bad_review_distribution": {
                dimension: values["bad_review_count"]
                for dimension, values in dimension_stats.items()
                if values["bad_review_count"] > 0
            }
        }

    @staticmethod
    def get_dimension_rankings(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        """按评论量、平均分和差评率输出维度排序。"""
        dimension_stats = SQLMetricsTools.get_dimension_stats(conn).get("dimension_stats", {})

        def _ranking(metric_field: str, reverse: bool = True) -> list[dict[str, Any]]:
            ordered = sorted(
                dimension_stats.items(),
                key=lambda item: (item[1][metric_field], item[0]),
                reverse=reverse,
            )
            return [
                {"dimension": dimension, metric_field: values[metric_field]}
                for dimension, values in ordered
            ]

        return {
            "dimension_rankings": {
                "by_comment_count": _ranking("comment_count", reverse=True),
                "by_avg_score": _ranking("avg_score", reverse=True),
                "by_bad_review_rate": _ranking("bad_review_rate", reverse=True),
            }
        }

    @staticmethod
    def get_monthly_score_trend(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        """按月份统计评论量、均分和差评率趋势。"""
        rows = conn.execute(
            """
            SELECT
                strftime(comment_time, '%Y-%m') AS month,
                COUNT(*) AS comment_count,
                ROUND(AVG(score), 2) AS avg_score,
                ROUND(AVG(CASE WHEN score <= 2 THEN 1.0 ELSE 0.0 END), 4) AS bad_review_rate,
                SUM(CASE WHEN score <= 2 THEN 1 ELSE 0 END) AS bad_review_count
            FROM comments_df
            WHERE comment_time IS NOT NULL
            GROUP BY 1
            ORDER BY 1
            """
        ).fetchall()
        return {
            "monthly_score_trend": [
                {
                    "month": str(month),
                    "comment_count": int(comment_count or 0),
                    "avg_score": float(avg_score or 0),
                    "bad_review_rate": float(bad_review_rate or 0),
                    "bad_review_count": int(bad_review_count or 0),
                }
                for month, comment_count, avg_score, bad_review_rate, bad_review_count in rows
            ]
        }

    @staticmethod
    def get_dimension_score_distribution(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        """统计各维度内部的评分分布情况。"""
        rows = conn.execute(
            """
            SELECT dimension, score, COUNT(*) AS count
            FROM comments_df
            GROUP BY dimension, score
            ORDER BY dimension ASC, score ASC
            """
        ).fetchall()
        distribution: dict[str, dict[str, int]] = {}
        for dimension, score, count in rows:
            dimension_key = str(dimension)
            score_distribution = distribution.setdefault(
                dimension_key,
                {str(index): 0 for index in range(1, 6)},
            )
            score_distribution[str(int(score))] = int(count or 0)
        return {"dimension_score_distribution": distribution}

    @staticmethod
    def get_dimension_coverage(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        """统计每个维度被评论覆盖的数量。"""
        dimension_stats = SQLMetricsTools.get_dimension_stats(conn).get("dimension_stats", {})
        return {
            "dimension_coverage": {
                dimension: values["comment_count"]
                for dimension, values in dimension_stats.items()
            }
        }

    @staticmethod
    def get_comment_length_stats(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        """统计评论长度的均值、中位数和长短评论规模。"""
        row = conn.execute(
            """
            SELECT
                ROUND(AVG(length(content)), 2) AS avg_length,
                median(length(content)) AS median_length,
                SUM(CASE WHEN length(content) >= 50 THEN 1 ELSE 0 END) AS long_comment_count,
                SUM(CASE WHEN length(content) < 20 THEN 1 ELSE 0 END) AS short_comment_count,
                COUNT(*) AS total_count
            FROM comments_df
            """
        ).fetchone()
        return {
            "comment_length_stats": {
                "avg_length": float(row[0] or 0),
                "median_length": float(row[1] or 0),
                "long_comment_count": int(row[2] or 0),
                "short_comment_count": int(row[3] or 0),
                "total_count": int(row[4] or 0),
            }
        }

    @staticmethod
    def get_low_score_dimension_pairs(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        """统计低分评论最集中的维度及其数量。"""
        rows = conn.execute(
            """
            SELECT dimension, COUNT(*) AS bad_count
            FROM comments_df
            WHERE score <= 2
            GROUP BY dimension
            ORDER BY bad_count DESC, dimension ASC
            """
        ).fetchall()
        return {
            "low_score_dimension_pairs": [
                {"dimension": str(dimension), "bad_count": int(bad_count or 0)}
                for dimension, bad_count in rows
            ]
        }

    @staticmethod
    def get_dimension_polarization(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        """统计各维度高低分占比，判断是否存在两极分化。"""
        rows = conn.execute(
            """
            SELECT
                dimension,
                ROUND(AVG(score), 2) AS avg_score,
                ROUND(AVG(CASE WHEN score >= 4 THEN 1.0 ELSE 0.0 END), 4) AS high_score_ratio,
                ROUND(AVG(CASE WHEN score <= 2 THEN 1.0 ELSE 0.0 END), 4) AS low_score_ratio
            FROM comments_df
            GROUP BY dimension
            ORDER BY dimension ASC
            """
        ).fetchall()
        result: dict[str, Any] = {}
        for dimension, avg_score, high_score_ratio, low_score_ratio in rows:
            high_ratio = float(high_score_ratio or 0)
            low_ratio = float(low_score_ratio or 0)
            result[str(dimension)] = {
                "avg_score": float(avg_score or 0),
                "high_score_ratio": high_ratio,
                "low_score_ratio": low_ratio,
                "polarization_index": round(high_ratio + low_ratio, 4),
            }
        return {"dimension_polarization": result}
