"""SQLAlchemy ORM models for SporeDB cloud tier.

All models include ``tenant_id`` for multi-tenant isolation.
Imports ``Role`` and ``BatchLifecycle`` from existing SporeDB modules
to avoid enum duplication.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from uuid_utils import uuid7


def _uuid7_str() -> str:
    """Generate a UUIDv7 as a string for use as a primary key default."""
    return str(uuid7())


def _utcnow() -> datetime:
    """Return timezone-aware UTC now, matching batch.py convention."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for all cloud tier SQLAlchemy models."""

    pass


class Tenant(Base):
    """A tenant (organisation) in the multi-tenant cloud tier."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid7_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    s3_prefix: Mapped[str] = mapped_column(String(255), unique=True, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # Relationships
    users: Mapped[list[CloudUser]] = relationship(back_populates="tenant")
    batches: Mapped[list[CloudBatch]] = relationship(back_populates="tenant")
    audit_entries: Mapped[list[AuditIndex]] = relationship(back_populates="tenant")


class CloudUser(Base):
    """A user within a tenant, with role-based access control."""

    __tablename__ = "cloud_users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_cloud_users_tenant_email"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid7_str)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="editor")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # Relationships
    tenant: Mapped[Tenant] = relationship(back_populates="users")


class CloudBatch(Base):
    """A bioprocess batch owned by a tenant."""

    __tablename__ = "cloud_batches"
    __table_args__ = (Index("ix_cloud_batches_tenant_id", "tenant_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid7_str)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    lifecycle: Mapped[str] = mapped_column(
        String(50), nullable=False, default="planned"
    )
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=_utcnow
    )

    # Relationships
    tenant: Mapped[Tenant] = relationship(back_populates="batches")


class AuditIndex(Base):
    """Index of audit trail entries for fast lookups by tenant and time range."""

    __tablename__ = "audit_index"
    __table_args__ = (
        Index("ix_audit_index_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid7_str)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # Cryptographic columns for 21 CFR Part 11 compliance
    old_value_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True, default=""
    )
    new_value_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True, default=""
    )
    previous_entry_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True, default=""
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    signature: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    public_key_pem: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Relationships
    tenant: Mapped[Tenant] = relationship(back_populates="audit_entries")


class RefreshToken(Base):
    """Tracks refresh token lifecycle for revocation and one-time use."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_jti", "jti", unique=True),
        Index("ix_refresh_tokens_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid7_str)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cloud_users.id"), nullable=False
    )
    jti: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    family_id: Mapped[str] = mapped_column(String(36), nullable=False)
    replaced_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
