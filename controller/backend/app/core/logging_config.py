"""
Configure application logging.

Set VISHWAAS_LOG_JSON=true to emit JSON lines suitable for log aggregators
(Loki, ELK, Splunk). Default: human-readable plain-text format.
"""
import logging
import os
import sys


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
            # python-json-logger not installed; fall back to plain text silently
            use_json = False

    if not use_json:
        formatter = logging.Formatter(
            "%(asctime)s,%(msecs)03d %(levelname)-5s %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
