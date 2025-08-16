import importlib
import sys
import types
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plan_daily_creates_future_nudge(tmp_path):
    config_module = types.ModuleType("config")
    config_module.BASE_DIR = ROOT
    config_module.settings = types.SimpleNamespace(
        subs=types.SimpleNamespace(nightly_toki_bonus={"free": 0})
    )
    sys.modules["app.config"] = config_module

    # provide minimal aiogram stub with Bot
    aiogram_mod = sys.modules.get("aiogram") or types.ModuleType("aiogram")
    if not hasattr(aiogram_mod, "Bot"):
        class _DummyBot:  # pragma: no cover - simple stub
            pass

        aiogram_mod.Bot = _DummyBot
    sys.modules["aiogram"] = aiogram_mod

    # ensure fresh storage and scheduler modules
    sys.modules.pop("app.storage", None)
    sys.modules.pop("app.scheduler", None)

    storage = importlib.import_module("app.storage")
    importlib.reload(storage)
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "alice")
    storage.set_user_field(1, "proactive_enabled", 1)

    # create character and chat for the user
    char_id = storage._exec("INSERT INTO characters(name) VALUES (?)", ("Hero",)).lastrowid
    storage.create_chat(1, char_id)

    scheduler = importlib.import_module("app.scheduler")
    importlib.reload(scheduler)

    class DummyScheduler:
        def __init__(self):
            self.jobs = []

        def add_job(self, id, trigger, replace_existing=False, run_date=None, func=None, args=()):
            job = types.SimpleNamespace(id=id, next_run_time=run_date)
            self.jobs.append(job)
            return job

        def remove_job(self, job_id):
            self.jobs = [j for j in self.jobs if j.id != job_id]

        def get_jobs(self):
            return list(self.jobs)

    dummy = DummyScheduler()
    scheduler._scheduler = dummy

    # call function under test
    scheduler._plan_daily(1)

    now_ts = dt.datetime.utcnow().timestamp()
    nudge_jobs = [j for j in dummy.jobs if j.id.startswith("nudge:1:")]
    assert nudge_jobs, "nudge job not scheduled"
    assert any(j.next_run_time.timestamp() > now_ts for j in nudge_jobs)

    # cleanup
    scheduler._scheduler = None
    sys.modules.pop("app.scheduler", None)
    storage.close()
    sys.modules.pop("app.storage", None)
    sys.modules.pop("app.config", None)

