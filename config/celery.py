"""Celery configuration for Stud'Insight project."""

import os

from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("studinsight")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Periodic tasks for peer review session cleanup (NFR-S7 anonymity guarantee)
app.conf.beat_schedule = {
    "cleanup-expired-peer-review-sessions": {
        "task": "backend_django.grading.tasks.cleanup_expired_peer_review_sessions_async",
        "schedule": crontab(hour="*/6"),  # Every 6 hours
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery configuration."""
    print(f"Request: {self.request!r}")
