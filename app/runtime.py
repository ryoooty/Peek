from __future__ import annotations

from typing import Optional, Dict
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings

_scheduler: Optional[AsyncIOScheduler] = None
_logger: Optional[logging.Logger] = None
_error_counts: Dict[str, int] = {}


def setup_logging() -> logging.Logger:
    """Configure root logger based on settings."""
    global _logger
    if _logger is not None:
        return _logger
    level = getattr(logging, str(settings.log_level).upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    _logger = logging.getLogger("peek")
    _logger.setLevel(level)
    return _logger


def get_logger() -> logging.Logger:
    return setup_logging()


def incr_error(name: str = "general") -> None:
    _error_counts[name] = _error_counts.get(name, 0) + 1


def get_error_counts() -> Dict[str, int]:
    return dict(_error_counts)


def set_scheduler(s: AsyncIOScheduler) -> None:
    global _scheduler
    _scheduler = s


def get_scheduler() -> Optional[AsyncIOScheduler]:
    return _scheduler

