from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Provenance(StrEnum):
    RAZORPAY_TEST = "RAZORPAY_TEST"
    SYNTHETIC = "SYNTHETIC"
    DERIVED = "DERIVED"
    LLM_INFERRED = "LLM_INFERRED"
    SIMULATED_OUTCOME = "SIMULATED_OUTCOME"


class CaseType(StrEnum):
    CONTROL_SUCCESS = "control_success"
    PAYMENT_FAILURE = "payment_failure"
    CHECKOUT_ABANDONMENT = "checkout_abandonment"
    SUBSCRIPTION_FAILURE = "subscription_failure"
    B2B_INVOICE = "b2b_invoice"
    PROMISE_TO_PAY = "promise_to_pay"


class DatasetSplit(StrEnum):
    DEVELOPMENT = "development"
    HELD_OUT = "held_out"


class FieldValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | int | float | bool | None
    provenance: Provenance


class DatasetCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    customer_id: str
    case_type: CaseType
    amount_paise: int = Field(ge=0)
    currency: str = "INR"
    status: str
    failure_reason: str | None
    payment_method: str | None
    attempt_count: int = Field(ge=0)
    occurred_at: datetime
    dataset_split: DatasetSplit | None = None

    contact_consent: bool
    whatsapp_consent: bool
    voice_consent: bool
    opted_out: bool
    already_refunded: bool
    alternate_payment_found: bool
    invoice_disputed: bool
    mandate_active: bool | None

    historical_failures: int = Field(ge=0)
    subscription_age_months: int = Field(ge=0)
    lifetime_value_paise: int = Field(ge=0)
    preferred_language: str
    timezone: str

    expected_policy: str
    simulated_outcome: str

    source_event_id: str | None
    field_provenance: dict[str, Provenance]
