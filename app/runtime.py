from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import register_reload_hook, settings

_scheduler: Optional[AsyncIOScheduler] = None


def set_scheduler(s: AsyncIOScheduler) -> None:
    global _scheduler
    _scheduler = s


def get_scheduler() -> Optional[AsyncIOScheduler]:
    return _scheduler


# ----- Logging -----
log = logging.getLogger("peek")
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
log.addHandler(_handler)


def _apply_log_level(cfg) -> None:
    level = getattr(logging, str(getattr(cfg, "log_level", "INFO")).upper(), logging.INFO)
    log.setLevel(level)


_apply_log_level(settings)
register_reload_hook(_apply_log_level)


# ----- Error counters -----
_error_counters: Dict[str, int] = defaultdict(int)


def inc_error(key: str) -> None:
    _error_counters[key] += 1


def get_error_counters() -> Dict[str, int]:
    return dict(_error_counters)
