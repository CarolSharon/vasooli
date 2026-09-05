import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from redis import Redis
from sqlalchemy import text

from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.media_stream import router as media_stream_router
from app.api.routes.razorpay import router as razorpay_router
from app.api.routes.razorpay_webhooks import router as razorpay_webhook_router
from app.api.routes.twilio import router as twilio_router
from app.api.routes.voice import router as voice_router
from app.api.webhooks import router as webhook_router
from app.config import settings
from app.database import engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]

app = FastAPI(
    title="Vasooli API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
app.include_router(razorpay_router)
app.include_router(razorpay_webhook_router)
app.include_router(twilio_router)
app.include_router(voice_router)
app.include_router(media_stream_router)
app.include_router(dashboard_router)
app.mount(
    "/audio",
    StaticFiles(directory=PROJECT_ROOT / "backend/app/static/audio"),
    name="audio",
)


@app.get("/health")
def health():
    postgresql = "connected"
    redis_status = "connected"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - report failures in the health response.
        postgresql = "disconnected"

    redis_client = Redis.from_url(settings.redis_url)
    try:
        redis_client.ping()
    except Exception:  # noqa: BLE001 - report failures in the health response.
        redis_status = "disconnected"
    finally:
        redis_client.close()

    development = json.loads(
        (PROJECT_ROOT / "data/splits/development.json").read_text(encoding="utf-8")
    )["case_count"]
    held_out = json.loads(
        (PROJECT_ROOT / "data/splits/held_out.json").read_text(encoding="utf-8")
    )["case_count"]
    return {
        "status": "ok",
        "service": "vasooli-api",
        "postgresql": postgresql,
        "redis": redis_status,
        "dataset": {
            "cases": development + held_out,
            "development": development,
            "held_out": held_out,
            "locked": True,
        },
    }
