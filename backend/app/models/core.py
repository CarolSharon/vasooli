from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_reference: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    preferred_language: Mapped[str] = mapped_column(String(20), default="en")
    timezone: Mapped[str] = mapped_column(String(100), default="Asia/Kolkata")
    whatsapp_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    voice_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    lifetime_value_paise: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "lifetime_value_paise >= 0",
            name="ck_customer_lifetime_value_nonnegative",
        ),
    )


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_reference: Mapped[str] = mapped_column(String(255), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    case_type: Mapped[str] = mapped_column(String(50))
    amount_paise: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(50))
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    root_cause: Mapped[str | None] = mapped_column(Text)
    risk_score: Mapped[float | None] = mapped_column(Float)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovered_amount_paise: Mapped[int] = mapped_column(Integer, default=0)
    payment_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    data_source: Mapped[str] = mapped_column(String(50))
    dataset_split: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint("amount_paise >= 0", name="ck_case_amount_nonnegative"),
        CheckConstraint("attempt_count >= 0", name="ck_case_attempts_nonnegative"),
        CheckConstraint(
            "recovered_amount_paise >= 0",
            name="ck_case_recovered_nonnegative",
        ),
        CheckConstraint(
            "risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 1)",
            name="ck_case_risk_score_range",
        ),
    )


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50))
    provider_event_id: Mapped[str] = mapped_column(String(255), unique=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(100))
    payment_status: Mapped[str | None] = mapped_column(String(50))
    amount_paise: Mapped[int | None] = mapped_column(Integer)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "amount_paise IS NULL OR amount_paise >= 0",
            name="ck_payment_event_amount_nonnegative",
        ),
    )


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("recovery_cases.id"))
    action_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50))
    channel: Mapped[str | None] = mapped_column(String(50))
    attempt_number: Mapped[int] = mapped_column(Integer)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    provider_reference: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "attempt_number >= 1",
            name="ck_recovery_action_attempt_positive",
        ),
    )


class DegradationIncident(Base):
    __tablename__ = "degradation_incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("recovery_cases.id"))
    incident_type: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(50), default="open")
    description: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class PromiseToPay(Base):
    __tablename__ = "promises_to_pay"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("recovery_cases.id"))
    promised_amount_paise: Mapped[int] = mapped_column(Integer)
    promised_date: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50))
    kept_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    broken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "promised_amount_paise >= 0",
            name="ck_promise_amount_nonnegative",
        ),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("recovery_cases.id"))
    actor: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(100))
    input_summary: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    policy_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # "metadata" is reserved by SQLAlchemy, so the Python attribute has a
    # different name while the database column is still named "metadata".
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
