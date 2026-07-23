import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .domain import SlideState


def _uuid() -> str:
    return str(uuid.uuid4())


def _public_id() -> str:
    return secrets.token_urlsafe(16)


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    credential_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    user: Mapped[User] = relationship()


class PasswordRecoveryCode(Base):
    __tablename__ = "password_recovery_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PasswordRecoveryAttempt(Base):
    __tablename__ = "password_recovery_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    client_key_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ip_key_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (
        CheckConstraint("sort_order >= 0", name="ck_folders_sort_order_nonnegative"),
        Index(
            "uq_folders_root_normalized_name",
            "normalized_name",
            unique=True,
            sqlite_where=text("parent_id IS NULL"),
        ),
        Index(
            "uq_folders_child_normalized_name",
            "parent_id",
            "normalized_name",
            unique=True,
            sqlite_where=text("parent_id IS NOT NULL"),
        ),
        Index("ix_folders_parent_order", "parent_id", "sort_order", "normalized_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("folders.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Slide(Base):
    __tablename__ = "slides"
    __table_args__ = (
        CheckConstraint("reserved_bytes >= 0", name="ck_slides_reserved_bytes_nonnegative"),
        CheckConstraint("derivative_bytes >= 0", name="ck_slides_derivative_bytes_nonnegative"),
        CheckConstraint(
            "derivative_file_count >= 0",
            name="ck_slides_derivative_file_count_nonnegative",
        ),
        CheckConstraint("sort_order >= 0", name="ck_slides_sort_order_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, default=_public_id, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    source_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    derivative_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    derivative_file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("folders.id", ondelete="SET NULL"), index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stain: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    organ_site: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    teaching_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    admin_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[SlideState] = mapped_column(
        Enum(
            SlideState,
            native_enum=False,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=SlideState.UPLOADING,
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    slide_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FolderShare(Base):
    __tablename__ = "folder_shares"
    __table_args__ = (
        Index(
            "uq_folder_shares_active_folder",
            "folder_id",
            unique=True,
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    folder_id: Mapped[str] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    public_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, default=lambda: secrets.token_urlsafe(32)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublicationGrant(Base):
    __tablename__ = "publication_grants"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('individual', 'folder')",
            name="ck_publication_grants_source_type",
        ),
        UniqueConstraint(
            "slide_id",
            "source_type",
            "source_id",
            name="uq_publication_grants_source",
        ),
        Index("ix_publication_grants_slide", "slide_id"),
        Index("ix_publication_grants_source", "source_type", "source_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slide_id: Mapped[str] = mapped_column(
        ForeignKey("slides.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slide_id: Mapped[str] = mapped_column(ForeignKey("slides.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="ingest")
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    slide: Mapped[Slide] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_action_created_at", "action", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(100))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
