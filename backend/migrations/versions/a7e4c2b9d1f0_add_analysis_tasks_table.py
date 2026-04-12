"""add analysis_tasks table

Revision ID: a7e4c2b9d1f0
Revises: 4c2426863f07
Create Date: 2026-04-12 10:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7e4c2b9d1f0"
down_revision: Union[str, Sequence[str], None] = "4c2426863f07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("trigger_message_id", sa.BigInteger(), nullable=False),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "PROCESSING",
                "COMPLETED",
                "FAILED",
                name="analysistaskstatus",
            ),
            nullable=False,
        ),
        sa.Column("current_step", sa.String(length=50), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trigger_message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_tasks_conversation_id", "analysis_tasks", ["conversation_id"], unique=False)
    op.create_index("ix_analysis_tasks_product_id", "analysis_tasks", ["product_id"], unique=False)
    op.create_index("ix_analysis_tasks_status", "analysis_tasks", ["status"], unique=False)
    op.create_index("ix_analysis_tasks_task_id", "analysis_tasks", ["task_id"], unique=True)
    op.create_index("ix_analysis_tasks_trigger_message_id", "analysis_tasks", ["trigger_message_id"], unique=False)
    op.create_index("ix_analysis_tasks_user_id", "analysis_tasks", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_analysis_tasks_user_id", table_name="analysis_tasks")
    op.drop_index("ix_analysis_tasks_trigger_message_id", table_name="analysis_tasks")
    op.drop_index("ix_analysis_tasks_task_id", table_name="analysis_tasks")
    op.drop_index("ix_analysis_tasks_status", table_name="analysis_tasks")
    op.drop_index("ix_analysis_tasks_product_id", table_name="analysis_tasks")
    op.drop_index("ix_analysis_tasks_conversation_id", table_name="analysis_tasks")
    op.drop_table("analysis_tasks")
