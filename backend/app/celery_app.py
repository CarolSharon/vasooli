from app.tasks import promises as _promises  # noqa: F401
from app.workers.celery_app import celery_app

__all__ = ["celery_app"]
