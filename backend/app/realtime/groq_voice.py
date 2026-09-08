import io
import struct
import wave
from typing import Literal

from groq import AsyncGroq
from pydantic import BaseModel, ConfigDict

from app.config import Settings

VoiceIntent = Literal[
    "SEND_PAYMENT_LINK",
    "PROMISE_TO_PAY",
    "CALL_LATER",
    "DISPUTE",
    "OPT_OUT",
    "HUMAN_TRANSFER",
    "UNKNOWN",
]


class GroqVoiceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: VoiceIntent
    due_date: str | None
    callback_at: str | None
    reason: str | None
    confirmation_question: str


def mulaw_sample(value: int) -> int:
    value = ~value & 0xFF
    sign = value & 0x80
    exponent = (value >> 4) & 0x07
    mantissa = value & 0x0F
    sample = ((mantissa << 3) + 0x84) << exponent
    sample -= 0x84
    return -sample if sign else sample


def mulaw_energy(audio: bytes) -> float:
    if not audio:
        return 0
    return sum(abs(mulaw_sample(value)) for value in audio) / len(audio)


def mulaw_to_wav(audio: bytes) -> bytes:
    pcm = b"".join(struct.pack("<h", mulaw_sample(value)) for value in audio)
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(pcm)
    return output.getvalue()


class GroqVoicePipeline:
    def __init__(self, settings: Settings):
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        self.settings = settings
        self.client = AsyncGroq(api_key=settings.groq_api_key)

    async def transcribe(self, mulaw_audio: bytes) -> str:
        result = await self.client.audio.transcriptions.create(
            file=("turn.wav", mulaw_to_wav(mulaw_audio)),
            model=self.settings.groq_stt_model,
            response_format="json",
        )
        return result.text.strip()

    async def decide(self, transcript: str) -> GroqVoiceDecision:
        prompt = f"""Classify this payment-recovery call utterance: {transcript!r}
Return one allowed intent. Use PROMISE_TO_PAY only with a clear future ISO date.
Use CALL_LATER only with a clear ISO datetime. Never request or repeat OTP, PIN,
CVV, card details, UPI PIN, passwords, or private banking information.
Write a short natural Hinglish confirmation question before any action."""
        result = await self.client.chat.completions.create(
            model=self.settings.groq_primary_model,
            messages=[{"role": "user", "content": prompt}],
            reasoning_effort="low",
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "voice_decision",
                    "strict": True,
                    "schema": GroqVoiceDecision.model_json_schema(),
                },
            },
        )
        content = result.choices[0].message.content
        if not content:
            raise ValueError("Groq returned no voice decision")
        return GroqVoiceDecision.model_validate_json(content)

    async def synthesize(self, text: str) -> bytes:
        response = await self.client.audio.speech.create(
            model=self.settings.groq_tts_model,
            voice=self.settings.groq_tts_voice,
            input=text,
            response_format="mulaw",
            sample_rate=8000,
        )
        return await response.read()


def tool_for_decision(decision: GroqVoiceDecision) -> tuple[str, dict] | None:
    mapping = {
        "SEND_PAYMENT_LINK": ("send_payment_link", {}),
        "PROMISE_TO_PAY": ("record_promise", {"due_date": decision.due_date}),
        "CALL_LATER": ("schedule_callback", {"when": decision.callback_at}),
        "DISPUTE": ("open_dispute", {"reason": decision.reason or "Customer dispute"}),
        "OPT_OUT": ("opt_out", {}),
        "HUMAN_TRANSFER": (
            "human_transfer",
            {"reason": decision.reason or "Customer request"},
        ),
    }
    tool = mapping.get(decision.intent)
    if not tool or any(value is None for value in tool[1].values()):
        return None
    return tool


def safe_result_message(result: dict) -> str:
    if result.get("ok"):
        return "Done. Aapki request securely record ho gayi hai. Thank you."
    reason = str(result.get("blocked_by", "POLICY"))
    return f"Sorry, main ye action complete nahi kar sakti. Reason: {reason.replace('_', ' ').lower()}. A human can help you."
