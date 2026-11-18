"""建立 AP Planner 基础数据库结构。

Revision ID: 20260906_0001
Revises:
"""
from typing import Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260906_0001"
down_revision: Optional[str] = None
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def _create_index(name: str, table: str, columns: list[str], unique: bool = False) -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {item["name"] for item in inspector.get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(), nullable=False),
            sa.Column("password", sa.String(), nullable=False),
            sa.Column("email", sa.String(), nullable=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("current_grade_term", sa.String(length=9), nullable=False),
        )
    else:
        user_columns = {item["name"] for item in inspector.get_columns("users")}
        if "email" not in user_columns:
            op.add_column("users", sa.Column("email", sa.String(), nullable=True))
    _create_index("ix_users_id", "users", ["id"])
    _create_index("ix_users_username", "users", ["username"], unique=True)

    table_specs = [
        (
            "gpas",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
                sa.Column("grade_term", sa.String(length=9)),
                sa.Column("weighted_gpa", sa.Float()),
                sa.Column("unweighted_gpa", sa.Float()),
            ],
        ),
        (
            "ap_plans",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
                sa.Column("course", sa.String()),
                sa.Column("score", sa.Integer()),
            ],
        ),
        (
            "standard_tests",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
                sa.Column("test_type", sa.String(length=8)),
                sa.Column("score", sa.Float()),
            ],
        ),
        (
            "sat_act",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
                sa.Column("test_type", sa.String(length=3)),
                sa.Column("score", sa.Integer()),
            ],
        ),
        (
            "background_projects",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
                sa.Column("project_type", sa.String()),
                sa.Column("project_name", sa.String()),
                sa.Column("description", sa.String()),
            ],
        ),
        (
            "profiles",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
                sa.Column("data", sa.JSON(), nullable=False),
            ],
        ),
        (
            "ai_plan_history",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
                sa.Column("question", sa.String()),
                sa.Column("answer", sa.String()),
                sa.Column("source", sa.String()),
                sa.Column("created_at", sa.DateTime()),
            ],
        ),
    ]

    for table_name, columns in table_specs:
        if table_name not in tables:
            op.create_table(table_name, *columns)
        _create_index(f"ix_{table_name}_id", table_name, ["id"])
        _create_index(f"ix_{table_name}_user_id", table_name, ["user_id"], unique=table_name == "profiles")

    # 旧版数据库没有外键；批量模式兼容 SQLite 并保留现有数据。
    inspector = sa.inspect(op.get_bind())
    for table_name, _ in table_specs:
        foreign_keys = inspector.get_foreign_keys(table_name)
        has_user_foreign_key = any(
            foreign_key.get("constrained_columns") == ["user_id"]
            and foreign_key.get("referred_table") == "users"
            for foreign_key in foreign_keys
        )
        if not has_user_foreign_key:
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.create_foreign_key(
                    f"fk_{table_name}_user_id_users",
                    "users",
                    ["user_id"],
                    ["id"],
                    ondelete="CASCADE",
                )


def downgrade() -> None:
    for table_name in [
        "ai_plan_history",
        "profiles",
        "background_projects",
        "sat_act",
        "standard_tests",
        "ap_plans",
        "gpas",
        "users",
    ]:
        op.drop_table(table_name)
