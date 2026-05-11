"""Initial cloud tier schema: tenants, users, batches, audit index.

Revision ID: 0001
Revises: None
Create Date: 2026-04-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- tenants ---
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("s3_prefix", sa.String(255), nullable=True, unique=True),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- cloud_users ---
    op.create_table(
        "cloud_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "role", sa.String(50), nullable=False, server_default=sa.text("'editor'")
        ),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("tenant_id", "email", name="uq_cloud_users_tenant_email"),
    )

    # --- cloud_batches ---
    op.create_table(
        "cloud_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "lifecycle",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'planned'"),
        ),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cloud_batches_tenant_id", "cloud_batches", ["tenant_id"])

    # --- audit_index ---
    op.create_table(
        "audit_index",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_audit_index_tenant_created", "audit_index", ["tenant_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_audit_index_tenant_created", table_name="audit_index")
    op.drop_table("audit_index")
    op.drop_index("ix_cloud_batches_tenant_id", table_name="cloud_batches")
    op.drop_table("cloud_batches")
    op.drop_table("cloud_users")
    op.drop_table("tenants")
