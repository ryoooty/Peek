import sys
import types

# minimal config stub
config_mod = types.ModuleType("app.config")
config_mod.settings = types.SimpleNamespace()
sys.modules.setdefault("app.config", config_mod)

from app import scheduler


class FakeJob:
    def __init__(self, job_id):
        self.id = job_id


class FakeScheduler:
    def __init__(self, jobs):
        self._jobs = jobs
        self.removed = []

    def get_jobs(self):
        return list(self._jobs)

    def remove_job(self, job_id):
        self.removed.append(job_id)


def setup_scheduler(monkeypatch, jobs):
    fake_sched = FakeScheduler([FakeJob(j) for j in jobs])
    monkeypatch.setattr(scheduler, "_scheduler", fake_sched)
    monkeypatch.setattr(scheduler, "_user_jobs", {123: ["existing"]})
    return fake_sched


def test_rebuild_user_jobs_creates_plan_when_enabled(monkeypatch):
    fake_sched = setup_scheduler(monkeypatch, ["nudge:123:1", "silence:123:2", "other:123"])

    monkeypatch.setattr(scheduler.storage, "get_user", lambda uid: {"proactive_enabled": 1})

    called = []
    monkeypatch.setattr(scheduler, "_plan_daily", lambda uid: called.append(uid), raising=False)

    scheduler.rebuild_user_jobs(123)

    assert set(fake_sched.removed) == {"nudge:123:1", "silence:123:2"}
    assert 123 not in scheduler._user_jobs
    assert called == [123]


def test_rebuild_user_jobs_skips_plan_when_disabled(monkeypatch):
    fake_sched = setup_scheduler(monkeypatch, ["nudge:123:1"])

    monkeypatch.setattr(scheduler.storage, "get_user", lambda uid: {"proactive_enabled": 0})

    called = []
    monkeypatch.setattr(scheduler, "_plan_daily", lambda uid: called.append(uid), raising=False)

    scheduler.rebuild_user_jobs(123)

    assert set(fake_sched.removed) == {"nudge:123:1"}
    assert called == []
