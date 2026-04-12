"""align existing tables with task model

Revision ID: b3f91d6e4a2c
Revises: a7e4c2b9d1f0
Create Date: 2026-04-12 11:10:00.000000

"""

from __future__ import annotations

import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3f91d6e4a2c"
down_revision: Union[str, Sequence[str], None] = "a7e4c2b9d1f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PRODUCT_PATTERNS = [
    re.compile(r"https?://(?:item\.)?jd\.com/(\d+)\.html"),
    re.compile(r"https?://(?:item\.)?taobao\.com/(?:item\.htm\?id=|auction/auction\.jhtml\?item_id=)(\d+)"),
    re.compile(r"https?://(?:detail\.)?tmall\.com/item\.htm\?id=(\d+)"),
    re.compile(r"https?://(?:www\.)?amazon\.cn/(?:dp|gp/product)/([A-Z0-9]+)"),
]


def _extract_external_product_id(url: str | None) -> str | None:
    if not url:
        return None
    for pattern in PRODUCT_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def _drop_fk_for_column(inspector, table_name: str, column_name: str) -> None:
    for fk in inspector.get_foreign_keys(table_name):
        if column_name in fk.get("constrained_columns", []):
            op.drop_constraint(fk["name"], table_name, type_="foreignkey")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. 先补 products 新字段，允许后续数据迁移。
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(sa.Column("external_product_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("last_crawl_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

    product_rows = bind.execute(
        sa.text("SELECT id, product_url, created_at FROM products ORDER BY id")
    ).mappings()
    for row in product_rows:
        external_product_id = _extract_external_product_id(row["product_url"]) or f"legacy-{row['id']}"
        bind.execute(
            sa.text(
                """
                UPDATE products
                SET external_product_id = :external_product_id,
                    updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
                WHERE id = :product_id
                """
            ),
            {"external_product_id": external_product_id, "product_id": row["id"]},
        )

    # 2. 合并旧结构下可能因 user_id 产生的重复商品。
    product_rows = bind.execute(
        sa.text(
            """
            SELECT id, source, external_product_id
            FROM products
            ORDER BY id
            """
        )
    ).mappings()
    canonical_ids: dict[tuple[str, str], int] = {}
    for row in product_rows:
        key = (row["source"], row["external_product_id"])
        if key not in canonical_ids:
            canonical_ids[key] = row["id"]
            continue

        canonical_id = canonical_ids[key]
        duplicate_id = row["id"]

        # 先删除会因合并而冲突的评论记录。
        canonical_source_ids = {
            comment_row["source_comment_id"]
            for comment_row in bind.execute(
                sa.text(
                    """
                    SELECT source_comment_id
                    FROM comments
                    WHERE product_id = :canonical_id
                      AND source_comment_id IS NOT NULL
                    """
                ),
                {"canonical_id": canonical_id},
            ).mappings()
        }
        if canonical_source_ids:
            duplicate_comments = bind.execute(
                sa.text(
                    """
                    SELECT id, source_comment_id
                    FROM comments
                    WHERE product_id = :duplicate_id
                      AND source_comment_id IS NOT NULL
                    """
                ),
                {"duplicate_id": duplicate_id},
            ).mappings()
            duplicate_comment_ids = [
                comment_row["id"]
                for comment_row in duplicate_comments
                if comment_row["source_comment_id"] in canonical_source_ids
            ]
            for comment_id in duplicate_comment_ids:
                bind.execute(
                    sa.text("DELETE FROM comments WHERE id = :comment_id"),
                    {"comment_id": comment_id},
                )

        bind.execute(
            sa.text("UPDATE comments SET product_id = :canonical_id WHERE product_id = :duplicate_id"),
            {"canonical_id": canonical_id, "duplicate_id": duplicate_id},
        )
        bind.execute(
            sa.text("UPDATE conversations SET product_id = :canonical_id WHERE product_id = :duplicate_id"),
            {"canonical_id": canonical_id, "duplicate_id": duplicate_id},
        )
        bind.execute(
            sa.text("UPDATE analysis_reports SET product_id = :canonical_id WHERE product_id = :duplicate_id"),
            {"canonical_id": canonical_id, "duplicate_id": duplicate_id},
        )
        bind.execute(
            sa.text("UPDATE analysis_tasks SET product_id = :canonical_id WHERE product_id = :duplicate_id"),
            {"canonical_id": canonical_id, "duplicate_id": duplicate_id},
        )
        bind.execute(
            sa.text("DELETE FROM products WHERE id = :duplicate_id"),
            {"duplicate_id": duplicate_id},
        )

    # 3. 调整 products 表到共享商品结构。
    _drop_fk_for_column(inspector, "products", "user_id")
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_index("ix_products_user_id")
        batch_op.alter_column(
            "status",
            new_column_name="crawl_status",
            existing_type=sa.Enum("PENDING", "CRAWLING", "COMPLETED", "FAILED", name="productstatus"),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "crawled_at",
            new_column_name="last_crawled_at",
            existing_type=sa.DateTime(),
            existing_nullable=True,
        )
        batch_op.drop_column("user_id")
        batch_op.alter_column("external_product_id", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)
        batch_op.create_index(
            "ix_products_source_external_product_id",
            ["source", "external_product_id"],
            unique=True,
        )

    # 4. comments 增加 updated_at。
    with op.batch_alter_table("comments") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
    bind.execute(sa.text("UPDATE comments SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"))
    with op.batch_alter_table("comments") as batch_op:
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)

    # 5. conversations 重命名商品绑定字段。
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.alter_column(
            "product_id",
            new_column_name="bound_product_id",
            existing_type=sa.BigInteger(),
            existing_nullable=True,
        )
        batch_op.create_index("ix_conversations_bound_product_id", ["bound_product_id"], unique=False)

    # 6. messages 新增 message_type，并扩展 role 枚举。
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(
            sa.Column(
                "message_type",
                sa.Enum(
                    "CHAT",
                    "ANALYSIS_REQUEST",
                    "ANALYSIS_RESULT",
                    "SYSTEM_NOTICE",
                    name="messagetype",
                ),
                nullable=True,
                server_default="CHAT",
            )
        )
        batch_op.alter_column(
            "role",
            existing_type=sa.Enum("USER", "ASSISTANT", name="messagerole"),
            type_=sa.Enum("USER", "ASSISTANT", "SYSTEM", name="messagerole"),
            existing_nullable=False,
        )
    bind.execute(sa.text("UPDATE messages SET message_type = COALESCE(message_type, 'CHAT')"))
    with op.batch_alter_table("messages") as batch_op:
        batch_op.alter_column("message_type", existing_type=sa.Enum("CHAT", "ANALYSIS_REQUEST", "ANALYSIS_RESULT", "SYSTEM_NOTICE", name="messagetype"), nullable=False, server_default=None)
        batch_op.create_index("ix_messages_message_type", ["message_type"], unique=False)

    # 7. analysis_reports 扩展为任务结果结构。
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.add_column(sa.Column("analysis_task_id", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("statistics_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("evidence_json", sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            "fk_analysis_reports_analysis_task_id",
            "analysis_tasks",
            ["analysis_task_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_analysis_reports_analysis_task_id", ["analysis_task_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.drop_index("ix_analysis_reports_analysis_task_id")
        batch_op.drop_constraint("fk_analysis_reports_analysis_task_id", type_="foreignkey")
        batch_op.drop_column("evidence_json")
        batch_op.drop_column("statistics_json")
        batch_op.drop_column("analysis_task_id")

    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_index("ix_messages_message_type")
        batch_op.drop_column("message_type")
        batch_op.alter_column(
            "role",
            existing_type=sa.Enum("USER", "ASSISTANT", "SYSTEM", name="messagerole"),
            type_=sa.Enum("USER", "ASSISTANT", name="messagerole"),
            existing_nullable=False,
        )

    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_index("ix_conversations_bound_product_id")
        batch_op.alter_column(
            "bound_product_id",
            new_column_name="product_id",
            existing_type=sa.BigInteger(),
            existing_nullable=True,
        )

    with op.batch_alter_table("comments") as batch_op:
        batch_op.drop_column("updated_at")

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_index("ix_products_source_external_product_id")
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.alter_column(
            "crawl_status",
            new_column_name="status",
            existing_type=sa.Enum("PENDING", "CRAWLING", "COMPLETED", "FAILED", name="productstatus"),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "last_crawled_at",
            new_column_name="crawled_at",
            existing_type=sa.DateTime(),
            existing_nullable=True,
        )
        batch_op.drop_column("updated_at")
        batch_op.drop_column("last_crawl_error")
        batch_op.drop_column("external_product_id")
