import uuid
from datetime import datetime
from typing import List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """User account entity storing profile, current onboarding/copy state, and interaction timestamps."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    phone_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    profession: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    niche: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    brand_handle: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    format_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    sub_intent: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    current_step: Mapped[str] = mapped_column(
        String(50),
        default="ASK_ONBOARDING",
        nullable=False,
    )
    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False,
    )

    # Relationships
    messages: Mapped[List["MessageHistory"]] = relationship(
        "MessageHistory",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="MessageHistory.created_at",
    )


class MessageHistory(Base):
    """Relational message history logging conversational turns and formats."""

    __tablename__ = "message_history"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # 'user', 'assistant'
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    format_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="messages",
    )


# Additional compound indexes for query efficiency
Index("ix_message_history_user_created", MessageHistory.user_id, MessageHistory.created_at)


class KnowledgeChunk(Base):
    """Stores chunked copywriting knowledge documents with vector embeddings for RAG."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    niche: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    format_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    doc_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,  # 'framework', 'hook', 'objection', 'playbook'
        index=True,
    )
    embedding: Mapped[List[float]] = mapped_column(
        Vector(768),  # Google Gemini text-embedding-004 is 768-dim
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False,
    )

