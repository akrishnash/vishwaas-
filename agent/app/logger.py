"""
VISHWAAS Agent - Centralized logging.

Logs to /var/log/vishwaas-agent.log when run as service.
Falls back to stderr when log path not writable (e.g. during install).

Set VISHWAAS_AGENT_LOG_JSON=true to emit JSON lines for log aggregators.
"""

import logging
import os
import sys
from pathlib import Path

# Default log path for production; overridable via env
LOG_PATH = os.environ.get("VISHWAAS_AGENT_LOG", "/var/log/vishwaas-agent.log")
# Set VISHWAAS_AGENT_DEBUG=1 to get DEBUG logs on stderr (and file) for debugging
DEBUG_MODE = os.environ.get("VISHWAAS_AGENT_DEBUG", "").strip() in ("1", "true", "yes")
# Set VISHWAAS_AGENT_LOG_JSON=true for structured JSON output
JSON_MODE = os.environ.get("VISHWAAS_AGENT_LOG_JSON", "").lower() in ("true", "1", "yes")

_logger: logging.Logger | None = None


def _build_formatter() -> logging.Formatter:
    if JSON_MODE:
        try:
            from pythonjsonlogger import jsonlogger

            class _AgentFormatter(jsonlogger.JsonFormatter):
                def add_fields(self, log_record, record, message_dict):
                    super().add_fields(log_record, record, message_dict)
                    log_record["service"] = "vishwaas-agent"
                    log_record["level"] = record.levelname

            return _AgentFormatter(
                fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        except ImportError:
            pass  # fall through to plain text
    return logging.Formatter(
        "%(asctime)s,%(msecs)03d %(levelname)-5s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _ensure_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger("vishwaas-agent")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = _build_formatter()
    stderr_level = logging.DEBUG if DEBUG_MODE else logging.INFO

    # Try file first (production)
    try:
        log_path = Path(LOG_PATH)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except (OSError, PermissionError):
        pass

    # Always attach stderr for systemd/journal visibility (DEBUG when VISHWAAS_AGENT_DEBUG=1)
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(stderr_level)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """Return the application logger. Safe to call from any module."""
    return _ensure_logger()


def log_startup():
    """Log agent startup with key paths."""
    log = get_logger()
    log.info("VISHWAAS agent starting; log file: %s", LOG_PATH)


def log_key_generation():
    """Log that WireGuard keys were generated."""
    get_logger().info("WireGuard keypair generated and stored securely")


def log_join_request(master_url: str, node_name: str):
    """Log join request sent to MASTER."""
    get_logger().info("Join request sent to MASTER %s as node %s", master_url, node_name)


def log_command(endpoint: str, success: bool, detail: str = ""):
    """Log MASTER command execution."""
    level = logging.INFO if success else logging.ERROR
    get_logger().log(level, "Command %s: success=%s %s", endpoint, success, detail or "")


def log_suspicious(ip: str, reason: str):
    """Log suspicious/unauthorized access attempts."""
    get_logger().warning("Suspicious access from %s: %s", ip, reason)


def log_error(msg: str, exc: Exception | None = None):
    """Log error; optionally attach exception."""
    log = get_logger()
    if exc:
        log.exception("%s: %s", msg, exc)
    else:
        log.error("%s", msg)
