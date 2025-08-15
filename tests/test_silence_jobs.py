import datetime as dt
import sys
import types


def test_schedule_silence_replaces_previous(monkeypatch):
    # stub aiogram.Bot before importing scheduler
    aiogram_module = types.ModuleType("aiogram")
    class DummyBot:
        pass
    aiogram_module.Bot = DummyBot
    monkeypatch.setitem(sys.modules, "aiogram", aiogram_module)

    from app import scheduler

    # dummy scheduler to track jobs
    class DummyJob:
        def __init__(self, jid, run_date):
            self.id = jid
            self.next_run_time = run_date

    class DummyScheduler:
        def __init__(self):
            self.jobs = {}

        def add_job(self, func, trigger, run_date, id, args, replace_existing=False, **kw):
            self.jobs[id] = DummyJob(id, run_date)

        def remove_job(self, job_id):
            self.jobs.pop(job_id, None)

        def get_jobs(self):
            return list(self.jobs.values())

    dummy = DummyScheduler()
    monkeypatch.setattr(scheduler, "_scheduler", dummy)
    monkeypatch.setattr(scheduler, "_user_jobs", {})

    base = dt.datetime(2020, 1, 1, 0, 0, 0)
    times = [base, base + dt.timedelta(seconds=1)]

    class DummyDatetime(dt.datetime):
        @classmethod
        def utcnow(cls):
            return times.pop(0)

    monkeypatch.setattr(scheduler.dt, "datetime", DummyDatetime)

    scheduler.schedule_silence_check(123, 456)
    scheduler.schedule_silence_check(123, 456)

    jobs = [j for j in dummy.get_jobs() if j.id.startswith("silence:123:")]
    assert len(jobs) == 1
    ts = int((base + dt.timedelta(seconds=1 + 600)).timestamp())
    assert jobs[0].id == f"silence:123:{ts}"
    assert scheduler._user_jobs[123] == [jobs[0].id]
    sys.modules.pop("app.scheduler", None)
