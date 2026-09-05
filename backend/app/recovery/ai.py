import json

from groq import Groq
from openai import OpenAI

from app.config import Settings
from app.recovery.fallback import deterministic_diagnosis
from app.recovery.schemas import AIDecision, RecoveryCase

SYSTEM_INSTRUCTIONS = """
You diagnose revenue-recovery cases.
Return only the requested structured decision.
Requirements:
- Never claim money was recovered.
- Never override consent, opt-outs, retry limits, quiet hours,
  invoice disputes, or mandate status.
- If evidence is insufficient, require human review.
- Never request an OTP, PIN, CVV, password, or full card number.
- Choose only one proposed action from the provided schema.
""".strip()


class DecisionService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.groq_client = (
            Groq(api_key=settings.groq_api_key) if settings.groq_api_key else None
        )
        self.openai_client = (
            OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        )

    def choose_model(self, case: RecoveryCase) -> str:
        high_value = case.amount_paise >= self.settings.high_value_threshold_paise
        if high_value or case.is_ambiguous or case.invoice_disputed:
            return (
                self.settings.groq_escalation_model
                if self.settings.groq_enabled
                else self.settings.openai_escalation_model
            )
        return (
            self.settings.groq_primary_model
            if self.settings.groq_enabled
            else self.settings.openai_primary_model
        )

    def diagnose(self, case: RecoveryCase) -> tuple[AIDecision, str, bool]:
        selected_model = self.choose_model(case)
        if self.settings.groq_enabled and self.groq_client is not None:
            return self._diagnose_with_groq(case, selected_model)
        if not self.settings.openai_enabled or self.openai_client is None:
            return deterministic_diagnosis(case), selected_model, True
        try:
            reasoning_effort = (
                "medium"
                if selected_model == self.settings.openai_escalation_model
                else "low"
            )
            response = self.openai_client.responses.parse(
                model=selected_model,
                reasoning={"effort": reasoning_effort},
                instructions=SYSTEM_INSTRUCTIONS,
                input=json.dumps(case.model_dump(mode="json")),
                text_format=AIDecision,
            )
            if response.output_parsed is None:
                raise ValueError("No parsed structured decision returned")
            return response.output_parsed, selected_model, False
        except Exception:  # noqa: BLE001 - deterministic fallback is intentional.
            return deterministic_diagnosis(case), selected_model, True

    def _diagnose_with_groq(
        self, case: RecoveryCase, selected_model: str
    ) -> tuple[AIDecision, str, bool]:
        try:
            response = self.groq_client.chat.completions.create(
                model=selected_model,
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                    {
                        "role": "user",
                        "content": json.dumps(case.model_dump(mode="json")),
                    },
                ],
                reasoning_effort=(
                    "medium"
                    if selected_model == self.settings.groq_escalation_model
                    else "low"
                ),
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "recovery_decision",
                        "strict": True,
                        "schema": AIDecision.model_json_schema(),
                    },
                },
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Groq returned no decision")
            return AIDecision.model_validate_json(content), selected_model, False
        except Exception:  # noqa: BLE001 - fallback keeps recovery deterministic.
            return deterministic_diagnosis(case), selected_model, True
