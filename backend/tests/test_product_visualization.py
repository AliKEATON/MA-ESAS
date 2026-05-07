from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from app.services.analysis_service import AnalysisService


class _FakeProductQuery:
    """模拟商品查询结果。"""

    def __init__(self, product):
        self._product = product

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._product


class _FakeCommentQuery:
    """模拟评论数量与评论列表查询。"""

    def __init__(self, comments):
        self._comments = comments

    def filter(self, *_args, **_kwargs):
        return self

    def count(self):
        return len(self._comments)

    def all(self):
        return self._comments


class _FakeDb:
    """按模型类型返回模拟查询对象。"""

    def __init__(self, product, comments):
        self._product = product
        self._comments = comments

    def query(self, model):
        model_name = getattr(model, "__name__", "")
        if model_name == "Product":
            return _FakeProductQuery(self._product)
        if model_name == "Comment":
            return _FakeCommentQuery(self._comments)
        raise AssertionError(f"Unsupported model query: {model_name}")


def _build_comment(*, score: int, dimension: str, content: str, comment_time: datetime):
    return SimpleNamespace(
        score=score,
        dimension=dimension,
        dimension_score=score,
        content=content,
        comment_time=comment_time,
    )


def test_get_product_visualization_returns_not_found_when_product_missing():
    fake_db = _FakeDb(product=None, comments=[])

    result = AnalysisService.get_product_visualization(
        fake_db,
        user_id=1,
        product_url="https://item.jd.com/1001.html",
    )

    assert result["exists"] is False
    assert result["has_data"] is False
    assert result["product"] is None
    assert result["charts"] == []


def test_get_product_visualization_returns_structured_metrics_when_comments_exist():
    product = SimpleNamespace(
        id=88,
        source="jd",
        external_product_id="1000001",
        product_url="https://item.jd.com/1000001.html",
        product_name="测试商品",
    )
    comments = [
        _build_comment(
            score=5,
            dimension="质量",
            content="做工扎实，速度快，日常使用很稳定。",
            comment_time=datetime(2026, 1, 5, 10, 0, 0),
        ),
        _build_comment(
            score=2,
            dimension="物流",
            content="发货速度太慢，包装也一般。",
            comment_time=datetime(2026, 2, 8, 12, 0, 0),
        ),
        _build_comment(
            score=4,
            dimension="售后",
            content="售后响应及时，处理问题比较顺畅。",
            comment_time=datetime(2026, 3, 2, 9, 30, 0),
        ),
    ]
    fake_db = _FakeDb(product=product, comments=comments)

    result = AnalysisService.get_product_visualization(
        fake_db,
        user_id=1,
        product_url="https://item.jd.com/1000001.html",
    )

    assert result["exists"] is True
    assert result["has_data"] is True
    assert result["product"]["product_id"] == 88
    assert result["overview"]["total_count"] == 3
    assert result["overview"]["avg_score"] == 3.67
    assert "summary_text" in result["overview"]
    assert result["dimension_analysis"]["best_dimension"] is not None
    assert isinstance(result["risk_analysis"]["high_risk_dimensions"], list)
    assert result["suggestions"]["recommendation_level"] in {"推荐购买", "谨慎购买", "不推荐"}
    assert len(result["charts"]) >= 4
    assert "score_summary" in result["raw_metrics"]
