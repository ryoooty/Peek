from __future__ import annotations

from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler

_scheduler: Optional[AsyncIOScheduler] = None

def set_scheduler(s: AsyncIOScheduler) -> None:
    global _scheduler
    _scheduler = s

def get_scheduler() -> Optional[AsyncIOScheduler]:
    return _scheduler
