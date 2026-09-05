import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Provenance(str, enum.Enum):
    RAZORPAY_TEST = "RAZORPAY_TEST"
    SYNTHETIC = "SYNTHETIC"
    DERIVED = "DERIVED"
    LLM_INFERRED = "LLM_INFERRED"
    SIMULATED_OUTCOME = "SIMULATED_OUTCOME"


class ProviderEvent(Base):
    __tablename__ = "provider_events"
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_status: Mapped[str] = mapped_column(String(30), default="RECEIVED")
    case_id: Mapped[int | None] = mapped_column(
        ForeignKey("recovery_cases.id"), index=True
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_provider_event"),
        Index("ix_provider_event_case_type", "case_id", "event_type"),
    )


class ProviderReference(Base):
    __tablename__ = "provider_references"
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    case_id: Mapped[int] = mapped_column(
        ForeignKey("recovery_cases.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_reference_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provenance: Mapped[Provenance] = mapped_column(Enum(Provenance), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "reference_type",
            "provider_reference_id",
            name="uq_provider_reference",
        ),
    )


class CommunicationEvent(Base):
    __tablename__ = "communication_events"
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    case_id: Mapped[int] = mapped_column(
        ForeignKey("recovery_cases.id"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(50))
    body: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class VoiceSession(Base):
    __tablename__ = "voice_sessions"
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    case_id: Mapped[int] = mapped_column(
        ForeignKey("recovery_cases.id"), nullable=False, index=True
    )
    twilio_call_sid: Mapped[str | None] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(40), default="CREATED")
    final_intent: Mapped[str | None] = mapped_column(String(50))
    transcript: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
