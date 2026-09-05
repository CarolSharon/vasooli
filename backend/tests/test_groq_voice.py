import struct

from app.realtime.groq_voice import (
    GroqVoiceDecision,
    mulaw_energy,
    mulaw_to_wav,
    safe_result_message,
    tool_for_decision,
)


def decision(intent, **updates):
    values = {
        "intent": intent,
        "due_date": None,
        "callback_at": None,
        "reason": None,
        "confirmation_question": "Please confirm",
    }
    values.update(updates)
    return GroqVoiceDecision(**values)


def test_mulaw_silence_has_low_energy():
    assert mulaw_energy(bytes([0xFF] * 160)) == 0


def test_mulaw_audio_converts_to_pcm_wav():
    output = mulaw_to_wav(bytes([0xFF, 0x7F] * 80))
    assert output.startswith(b"RIFF") and output[8:12] == b"WAVE"
    assert struct.unpack("<I", output[24:28])[0] == 8000


def test_payment_link_maps_to_guarded_tool():
    assert tool_for_decision(decision("SEND_PAYMENT_LINK")) == (
        "send_payment_link",
        {},
    )


def test_promise_without_date_is_not_executable():
    assert tool_for_decision(decision("PROMISE_TO_PAY")) is None


def test_promise_with_date_maps_to_guarded_tool():
    assert tool_for_decision(decision("PROMISE_TO_PAY", due_date="2026-09-11")) == (
        "record_promise",
        {"due_date": "2026-09-11"},
    )


def test_unknown_intent_never_maps_to_action():
    assert tool_for_decision(decision("UNKNOWN")) is None


def test_blocked_result_does_not_claim_success():
    message = safe_result_message({"ok": False, "blocked_by": "OPT_OUT"})
    assert message.startswith("Sorry") and "opt out" in message.lower()
