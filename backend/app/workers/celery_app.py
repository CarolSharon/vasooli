from celery import Celery

from app.config import settings

celery_app = Celery(
    "vasooli",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.beat_schedule = {
    "check-overdue-promises-every-5-minutes": {
        "task": "check_overdue_promises",
        "schedule": 300.0,
    }
}

celery_app.conf.update(
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task
def health_task() -> dict[str, str]:
    return {"status": "ok"}
