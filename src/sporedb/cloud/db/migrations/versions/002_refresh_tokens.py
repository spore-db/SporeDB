"""Add refresh_tokens table for JWT revocation tracking.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("cloud_users.id"), nullable=False
        ),
        sa.Column("jti", sa.String(36), unique=True, nullable=False),
        sa.Column("family_id", sa.String(36), nullable=False),
        sa.Column("replaced_by", sa.String(36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_refresh_tokens_jti", "refresh_tokens", ["jti"], unique=True)
    op.create_index("ix_refresh_tokens_user", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_jti", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
