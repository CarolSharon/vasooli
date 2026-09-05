"""Validated recovery workflow contracts."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CaseType(StrEnum):
    PAYMENT_FAILURE = "payment_failure"
    CHECKOUT_ABANDONMENT = "checkout_abandonment"
    SUBSCRIPTION_FAILURE = "subscription_failure"
    B2B_INVOICE = "b2b_invoice"
    MANDATE_RETRY = "mandate_retry"
    VOICE_RECOVERY = "voice_recovery"
    PROMISE_TO_PAY = "promise_to_pay"


class CaseStatus(StrEnum):
    AT_RISK = "at_risk"
    SCHEDULED = "scheduled"
    BLOCKED = "blocked"
    ESCALATED = "escalated"
    RECOVERED = "recovered"
    CLOSED = "closed"


class ActionType(StrEnum):
    RETRY_PAYMENT = "retry_payment"
    SEND_PAYMENT_LINK = "send_payment_link"
    SEND_REMINDER = "send_reminder"
    REQUEST_REAUTHORIZATION = "request_reauthorization"
    OFFER_ALTERNATIVE_METHOD = "offer_alternative_method"
    PLACE_VOICE_CALL = "place_voice_call"
    RECORD_PROMISE = "record_promise"
    PAUSE_RETRIES = "pause_retries"
    ESCALATE_HUMAN = "escalate_human"
    NO_ACTION = "no_action"


class PolicyResult(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    DELAY = "delay"
    ESCALATE = "escalate"


class RecoveryCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    case_type: CaseType
    customer_id: str
    amount_paise: int = Field(ge=0)
    currency: str = "INR"
    status: CaseStatus = CaseStatus.AT_RISK
    failure_reason: str | None = None
    payment_method: str | None = None
    bank: str | None = None
    attempt_count: int = Field(default=0, ge=0)
    reminder_count: int = Field(default=0, ge=0)
    voice_call_count: int = Field(default=0, ge=0)
    attempted_at: datetime | None = None
    last_contact_at: datetime | None = None
    contact_consent: bool = True
    whatsapp_consent: bool = True
    voice_consent: bool = False
    opted_out: bool = False
    payment_confirmed: bool = False
    already_refunded: bool = False
    order_cancelled: bool = False
    mandate_active: bool | None = None
    invoice_disputed: bool = False
    requested_discount_paise: int = Field(default=0, ge=0)
    promise_date: date | None = None
    promised_amount_paise: int | None = Field(default=None, ge=0)
    preferred_language: str = "en-IN"
    customer_timezone: str = "Asia/Kolkata"
    is_ambiguous: bool = False
    metadata: dict = Field(default_factory=dict)


class AIDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root_cause: str
    confidence: float = Field(ge=0, le=1)
    proposed_action: ActionType
    retry_delay_hours: int | None = Field(default=None, ge=0, le=720)
    channel: str | None = None
    reason_summary: str
    requires_human_review: bool = False
    missing_information: list[str] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    result: PolicyResult
    code: str
    reason: str
    next_allowed_at: datetime | None = None
    requires_human_review: bool = False


class WorkflowResult(BaseModel):
    case: RecoveryCase
    ai_decision: AIDecision
    policy_decision: PolicyDecision
    selected_model: str
    used_fallback: bool
    action_id: str | None = None
    audit_event_ids: list[int] = Field(default_factory=list)


class DegradationRequest(BaseModel):
    payment_method: str
    bank: str | None = None
    window_minutes: int = Field(default=15, ge=1, le=1440)
    baseline_failure_rate: float = Field(ge=0, le=1)
    current_failure_rate: float = Field(ge=0, le=1)
    affected_amount_paise: int = Field(ge=0)


class PromiseRequest(BaseModel):
    case_id: str
    promised_amount_paise: int = Field(gt=0)
    promise_date: date
    source: str = "customer_message"


class VoiceTurnRequest(BaseModel):
    case_id: str
    customer_utterance: str
