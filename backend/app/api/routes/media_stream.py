import base64
import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.database import SessionLocal
from app.models import RecoveryCase, VoiceSession
from app.realtime.groq_voice import (
    GroqVoiceDecision,
    GroqVoicePipeline,
    mulaw_energy,
    safe_result_message,
    tool_for_decision,
)
from app.realtime.guarded_actions import execute_voice_tool

router = APIRouter(tags=["voice-media"])
SILENCE_THRESHOLD = 300
SILENCE_FRAMES = 35
MINIMUM_TURN_BYTES = 3200


async def send_audio(websocket: WebSocket, stream_sid: str, audio: bytes) -> None:
    for start in range(0, len(audio), 160):
        payload = base64.b64encode(audio[start : start + 160]).decode()
        await websocket.send_json(
            {"event": "media", "streamSid": stream_sid, "media": {"payload": payload}}
        )


def is_yes(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return normalized in {
        "yes",
        "yes please",
        "haan",
        "han",
        "ha",
        "theek hai",
        "okay",
        "ok",
    }


def is_no(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return normalized in {"no", "nahi", "nahin", "cancel", "mat karo"}


@router.websocket("/api/twilio/media")
async def twilio_media_stream(websocket: WebSocket):
    await websocket.accept()
    if settings.voice_ai_provider != "groq" or not settings.groq_api_key:
        await websocket.close(code=1013, reason="Groq voice is not configured")
        return

    database = SessionLocal()
    pipeline = GroqVoicePipeline(settings)
    stream_sid: str | None = None
    case: RecoveryCase | None = None
    voice_session: VoiceSession | None = None
    pending: GroqVoiceDecision | None = None
    turn_audio = bytearray()
    speech_started = False
    silence_frames = 0

    async def process_turn() -> None:
        nonlocal pending
        if not case or not voice_session or not stream_sid or not turn_audio:
            return
        transcript = await pipeline.transcribe(bytes(turn_audio))
        if not transcript:
            return
        voice_session.transcript += f"CUSTOMER: {transcript}\n"
        if pending and is_yes(transcript):
            tool = tool_for_decision(pending)
            result = (
                execute_voice_tool(database, case=case, name=tool[0], arguments=tool[1])
                if tool
                else {"ok": False, "blocked_by": "INCOMPLETE_REQUEST"}
            )
            reply = safe_result_message(result)
            voice_session.final_intent = pending.intent
            pending = None
        elif pending and is_no(transcript):
            pending = None
            reply = "Theek hai, action cancel kar diya. Aur kaise help kar sakti hoon?"
        else:
            decision = await pipeline.decide(transcript)
            tool = tool_for_decision(decision)
            if tool:
                pending = decision
                reply = decision.confirmation_question
            else:
                reply = (
                    "Main payment link, future payment date, callback, dispute, "
                    "opt-out, ya human agent mein help kar sakti hoon."
                )
        voice_session.transcript += f"AGENT: {reply}\n"
        database.commit()
        await send_audio(websocket, stream_sid, await pipeline.synthesize(reply))

    try:
        async for raw in websocket.iter_text():
            event = json.loads(raw)
            if event.get("event") == "start":
                stream_sid = event["start"]["streamSid"]
                raw_id = event["start"].get("customParameters", {}).get("case_id", "")
                case = (
                    database.get(RecoveryCase, int(raw_id))
                    if raw_id.isdigit()
                    else None
                )
                if not case:
                    await websocket.close(code=1008, reason="Case not found")
                    return
                voice_session = VoiceSession(
                    case_id=case.id,
                    twilio_call_sid=event["start"].get("callSid"),
                    status="CONNECTED",
                )
                database.add(voice_session)
                database.commit()
                greeting = "Namaste. Main Vasooli AI assistant hoon. Main aapki payment recovery mein kaise help kar sakti hoon?"
                voice_session.transcript += f"AGENT: {greeting}\n"
                database.commit()
                await send_audio(
                    websocket, stream_sid, await pipeline.synthesize(greeting)
                )
            elif event.get("event") == "media":
                chunk = base64.b64decode(event["media"]["payload"])
                energy = mulaw_energy(chunk)
                if energy >= SILENCE_THRESHOLD:
                    speech_started = True
                    silence_frames = 0
                elif speech_started:
                    silence_frames += 1
                if speech_started:
                    turn_audio.extend(chunk)
                if (
                    silence_frames >= SILENCE_FRAMES
                    and len(turn_audio) >= MINIMUM_TURN_BYTES
                ):
                    await process_turn()
                    turn_audio.clear()
                    speech_started = False
                    silence_frames = 0
            elif event.get("event") == "stop":
                break
    except WebSocketDisconnect:
        pass
    finally:
        if voice_session:
            voice_session.status = "COMPLETED"
            voice_session.ended_at = datetime.now(timezone.utc)
            database.commit()
        database.close()
