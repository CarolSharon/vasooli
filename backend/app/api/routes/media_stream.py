import asyncio
import json

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.database import SessionLocal
from app.models import RecoveryCase, VoiceSession
from app.realtime.guarded_actions import execute_voice_tool
from app.realtime.tools import VOICE_TOOLS

router = APIRouter(tags=["voice-media"])
SYSTEM_PROMPT = """You are Vasooli, a polite AI payment recovery assistant. Speak briefly in natural Hinglish unless English is requested. Never shame or threaten. Never request card numbers, CVV, OTP, UPI PIN, bank passwords, or mandate PIN. Never invent discounts or payment status. Confirm once before proposing a tool. Only send an existing link, record a clear future promise date, schedule a callback, open a dispute, opt out, or request human help. Keep the call under three minutes."""


@router.websocket("/api/twilio/media")
async def twilio_media_stream(twilio_ws: WebSocket):
    await twilio_ws.accept()
    if not settings.openai_api_key:
        await twilio_ws.close(code=1013, reason="Realtime service not configured")
        return
    db, stream_sid, case_id, voice_session = SessionLocal(), None, None, None
    try:
        async with websockets.connect(
            f"wss://api.openai.com/v1/realtime?model={settings.openai_realtime_model}",
            additional_headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        ) as openai_ws:
            await openai_ws.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "type": "realtime",
                            "model": settings.openai_realtime_model,
                            "instructions": SYSTEM_PROMPT,
                            "output_modalities": ["audio"],
                            "audio": {
                                "input": {
                                    "format": {"type": "audio/pcmu"},
                                    "turn_detection": {"type": "server_vad"},
                                },
                                "output": {
                                    "format": {"type": "audio/pcmu"},
                                    "voice": settings.openai_realtime_voice,
                                },
                            },
                            "tools": VOICE_TOOLS,
                            "tool_choice": "auto",
                            "max_output_tokens": 300,
                        },
                    }
                )
            )

            async def twilio_to_openai():
                nonlocal stream_sid, case_id, voice_session
                async for raw in twilio_ws.iter_text():
                    event = json.loads(raw)
                    if event["event"] == "start":
                        stream_sid = event["start"]["streamSid"]
                        raw_case_id = (
                            event["start"].get("customParameters", {}).get("case_id")
                        )
                        case_id = (
                            int(raw_case_id)
                            if raw_case_id and raw_case_id.isdigit()
                            else None
                        )
                        case = db.get(RecoveryCase, case_id)
                        if not case:
                            await twilio_ws.close(code=1008)
                            return
                        voice_session = VoiceSession(
                            case_id=case.id,
                            twilio_call_sid=event["start"].get("callSid"),
                            status="CONNECTED",
                        )
                        db.add(voice_session)
                        db.commit()
                        await openai_ws.send(
                            json.dumps(
                                {
                                    "type": "response.create",
                                    "response": {
                                        "instructions": f"Greet the customer. Outstanding amount is ₹{case.amount_paise / 100:.2f}. Ask how you can help."
                                    },
                                }
                            )
                        )
                    elif event["event"] == "media":
                        await openai_ws.send(
                            json.dumps(
                                {
                                    "type": "input_audio_buffer.append",
                                    "audio": event["media"]["payload"],
                                }
                            )
                        )
                    elif event["event"] == "stop":
                        return

            async def openai_to_twilio():
                nonlocal voice_session
                async for raw in openai_ws:
                    event = json.loads(raw)
                    kind = event.get("type", "")
                    if kind == "response.output_audio.delta" and stream_sid:
                        await twilio_ws.send_json(
                            {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": event["delta"]},
                            }
                        )
                    elif kind in {
                        "conversation.item.input_audio_transcription.completed",
                        "response.output_audio_transcript.done",
                    }:
                        transcript = event.get("transcript", "")
                        if voice_session and transcript:
                            voice_session.transcript += (
                                (
                                    "CUSTOMER: "
                                    if kind.startswith("conversation.")
                                    else "AGENT: "
                                )
                                + transcript
                                + "\n"
                            )
                            db.commit()
                    elif kind == "response.function_call_arguments.done" and case_id:
                        case = db.get(RecoveryCase, case_id)
                        try:
                            arguments = json.loads(event.get("arguments") or "{}")
                        except json.JSONDecodeError:
                            arguments = {}
                        result = execute_voice_tool(
                            db, case=case, name=event["name"], arguments=arguments
                        )
                        if voice_session:
                            voice_session.final_intent = event["name"]
                            db.commit()
                        await openai_ws.send(
                            json.dumps(
                                {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": event["call_id"],
                                        "output": json.dumps(result),
                                    },
                                }
                            )
                        )
                        await openai_ws.send(json.dumps({"type": "response.create"}))
                    elif kind == "input_audio_buffer.speech_started" and stream_sid:
                        await twilio_ws.send_json(
                            {"event": "clear", "streamSid": stream_sid}
                        )

            await asyncio.gather(twilio_to_openai(), openai_to_twilio())
    except WebSocketDisconnect:
        pass
    finally:
        if voice_session:
            voice_session.status = "COMPLETED"
            db.commit()
        db.close()
