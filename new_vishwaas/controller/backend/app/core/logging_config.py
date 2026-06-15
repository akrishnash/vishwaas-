"""
Configure application logging.

Set VISHWAAS_LOG_JSON=true to emit JSON lines suitable for log aggregators
(Loki, ELK, Splunk). Default: human-readable plain-text format.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging() -> None:
    """Call once at startup before any log messages are emitted."""
    use_json = os.environ.get("VISHWAAS_LOG_JSON", "").lower() in ("true", "1", "yes")
    from app.core.config import settings
    level = logging.DEBUG if settings.debug else logging.INFO

    if use_json:
        try:
            from pythonjsonlogger import jsonlogger

            class _VishwaasFormatter(jsonlogger.JsonFormatter):
                def add_fields(self, log_record, record, message_dict):
                    super().add_fields(log_record, record, message_dict)
                    log_record["service"] = "vishwaas-controller"
                    log_record["level"] = record.levelname

            formatter: logging.Formatter = _VishwaasFormatter(
                fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        except ImportError:
            use_json = False

    if not use_json:
        formatter = logging.Formatter(
            "%(asctime)s,%(msecs)03d %(levelname)-5s %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root.addHandler(stdout_handler)

    # Rotating file handler so /system-logs can serve recent controller logs
    log_file = getattr(settings, "log_file", "") or ""
    if not log_file:
        log_file = os.environ.get("VISHWAAS_LOG_FILE", "./logs/controller.log")
    try:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        root.addHandler(fh)
    except (OSError, PermissionError):
        pass
