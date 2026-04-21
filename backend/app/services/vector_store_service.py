"""ChromaDB vector storage helpers for product comments."""

from __future__ import annotations

from typing import Any

import requests
from sqlalchemy.orm import Session

from app.config import EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL
from app.db.database import get_chromadb_client
from app.models import Comment, Product
from app.utils.logger import logger


class VectorStoreService:
    """负责评论向量写入、补索引和语义检索。"""

    COLLECTION_NAME = "product_comments"

    @classmethod
    def _embed_texts(cls, texts: list[str]) -> list[list[float]]:
        """调用远程 Embedding API，将一批评论文本编码成向量。"""
        if not texts:
            return []

        if not EMBEDDING_API_KEY:
            raise RuntimeError("EMBEDDING_API_KEY is not configured")

        response = requests.post(
            cls._build_embedding_request_url(),
            headers={
                "Authorization": f"Bearer {EMBEDDING_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": EMBEDDING_MODEL,
                "input": texts,
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or []
        if not isinstance(data, list) or not data:
            raise RuntimeError("Embedding API returned empty data")

        sorted_items = sorted(data, key=lambda item: int(item.get("index", 0)))
        embeddings: list[list[float]] = []
        for item in sorted_items:
            embedding = item.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                raise RuntimeError("Embedding API returned invalid embedding payload")
            embeddings.append([float(value) for value in embedding])

        if len(embeddings) != len(texts):
            raise RuntimeError("Embedding API returned unexpected embedding count")

        logger.info(
            "Remote embeddings generated: model={} text_count={} endpoint={}",
            EMBEDDING_MODEL,
            len(texts),
            cls._build_embedding_request_url(),
        )
        return embeddings

    @staticmethod
    def _build_embedding_request_url() -> str:
        """拼接远程 Embedding 接口地址。"""
        return f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings"

    @classmethod
    def _get_collection(cls) -> Any:
        """获取评论向量集合，不存在时自动创建。"""
        client = get_chromadb_client()
        return client.get_or_create_collection(
            name=cls.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def _build_metadata(product: Product, comment: Comment) -> dict[str, Any]:
        """构造写入 ChromaDB 的评论元数据。"""
        comment_time = comment.comment_time.isoformat() if comment.comment_time else None
        return {
            "product_id": int(product.id),
            "source": product.source,
            "external_product_id": product.external_product_id,
            "score": comment.score,
            "dimension": comment.dimension,
            "comment_time": comment_time,
        }

    @classmethod
    def upsert_product_comments(
        cls,
        db: Session,
        product_id: int,
        comments: list[Comment] | None = None,
    ) -> int:
        """将指定商品评论写入向量库，并更新向量化标记。"""
        product = db.query(Product).filter(Product.id == product_id).first()
        if product is None:
            logger.warning("Skip vector upsert because product does not exist: product_id={}", product_id)
            return 0

        db.flush()
        comment_items = comments or db.query(Comment).filter(
            Comment.product_id == product_id,
            Comment.content.isnot(None),
        ).all()
        comment_items = [item for item in comment_items if item.content and str(item.content).strip()]
        if not comment_items:
            logger.info("Skip vector upsert because no comments are available: product_id={}", product_id)
            return 0

        try:
            collection = cls._get_collection()
            embeddings = cls._embed_texts([item.content for item in comment_items])
        except Exception as exc:
            logger.warning("Vector upsert skipped because vector dependencies are unavailable: {}", exc)
            return 0

        collection.upsert(
            ids=[str(item.id) for item in comment_items],
            documents=[item.content for item in comment_items],
            metadatas=[cls._build_metadata(product, item) for item in comment_items],
            embeddings=embeddings,
        )
        for item in comment_items:
            item.is_vectorized = True
        logger.info(
            "Vector store upsert completed: product_id={} comment_count={}",
            product_id,
            len(comment_items),
        )
        return len(comment_items)

    @classmethod
    def ensure_product_vectorized(cls, db: Session, product_id: int) -> int:
        """为未向量化的评论补写向量索引。"""
        pending_comments = db.query(Comment).filter(
            Comment.product_id == product_id,
            Comment.is_vectorized.is_(False),
            Comment.content.isnot(None),
        ).all()
        if not pending_comments:
            return 0
        return cls.upsert_product_comments(db, product_id, pending_comments)

    @classmethod
    def delete_product_comments(cls, product_id: int) -> int:
        """删除指定商品在向量库中的历史评论索引。"""
        try:
            collection = cls._get_collection()
            collection.delete(where={"product_id": int(product_id)})
        except Exception as exc:
            logger.warning("Vector delete skipped because vector dependencies are unavailable: {}", exc)
            return 0
        logger.info("Vector store comments deleted: product_id={}", product_id)
        return 1

    @classmethod
    def query_product_comments(
        cls,
        db: Session,
        product_id: int,
        queries: list[str],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """按商品过滤后执行语义检索，并返回去重后的证据评论。"""
        del db
        normalized_queries = [item.strip() for item in queries if item and item.strip()]
        if not normalized_queries:
            return []

        try:
            collection = cls._get_collection()
            query_embeddings = cls._embed_texts(normalized_queries)
        except Exception as exc:
            logger.warning("Vector retrieval skipped because vector dependencies are unavailable: {}", exc)
            return []

        result = collection.query(
            query_embeddings=query_embeddings,
            n_results=limit,
            where={"product_id": int(product_id)},
            include=["documents", "metadatas", "distances"],
        )

        evidence_by_key: dict[str, dict[str, Any]] = {}
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        distances = result.get("distances") or []

        for query_index, document_list in enumerate(documents):
            metadata_list = metadatas[query_index] if query_index < len(metadatas) else []
            distance_list = distances[query_index] if query_index < len(distances) else []
            for item_index, content in enumerate(document_list or []):
                metadata = metadata_list[item_index] if item_index < len(metadata_list) else {}
                distance = distance_list[item_index] if item_index < len(distance_list) else None
                similarity = cls._distance_to_similarity(distance)
                key = f"{content}|{metadata.get('dimension')}|{metadata.get('score')}"
                candidate = {
                    "content": content,
                    "score": metadata.get("score"),
                    "dimension": metadata.get("dimension"),
                    "similarity": similarity,
                }
                existing = evidence_by_key.get(key)
                if existing is None or float(candidate["similarity"]) > float(existing["similarity"]):
                    evidence_by_key[key] = candidate

        evidence = sorted(
            evidence_by_key.values(),
            key=lambda item: float(item.get("similarity") or 0),
            reverse=True,
        )[:limit]
        logger.info(
            "Vector retrieval completed: product_id={} query_count={} evidence_count={}",
            product_id,
            len(normalized_queries),
            len(evidence),
        )
        return evidence

    @staticmethod
    def _distance_to_similarity(distance: Any) -> float:
        """把 ChromaDB 距离值转换为更直观的相似度分数。"""
        if distance is None:
            return 0.0
        try:
            numeric_distance = float(distance)
        except (TypeError, ValueError):
            return 0.0
        return round(max(0.0, 1.0 - numeric_distance), 4)
