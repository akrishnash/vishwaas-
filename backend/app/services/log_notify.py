"""Helpers: write audit log and create notification."""
from app.persistence.models import Log, Notification
from app.domain.enums import LogEventType, NotificationType


def log_event(db, event_type: LogEventType, description: str):
    db.add(Log(event_type=event_type, description=description))


def notify(db, type: NotificationType, message: str):
    db.add(Notification(type=type, message=message, is_read=0))
