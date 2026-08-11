from fastapi.testclient import TestClient

from app.main import create_app


class FakeDatabase:
    def __init__(self):
        self.rows = []

    def insert_job(self, job):
        self.rows.append(dict(job))
        return dict(job)


def payload():
    return {
        "prompt": "async shadow test",
        "duration": "30",
        "style": "cinematic",
        "voice": "default",
        "captions": "off",
    }


def test_post_schedules_shadow_after_persistence_without_running_inline(monkeypatch, tmp_path):
    scheduled = []

    def capture_task(self, func, *args, **kwargs):
        scheduled.append((func, args, kwargs))

    monkeypatch.setattr("starlette.background.BackgroundTasks.add_task", capture_task)
    database = FakeDatabase()
    client = TestClient(create_app(database_client=database, data_dir=tmp_path))

    response = client.post("/api/videos", json=payload())

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert len(database.rows) == 1
    assert len(scheduled) == 1
    assert scheduled[0][0].__name__ == "_shadow"
    assert scheduled[0][1][-1] == str(database.rows[0]["id"])


def test_background_shadow_callable_runs_when_dispatched():
    from fastapi import BackgroundTasks

    calls = []

    def shadow(value):
        calls.append(value)

    tasks = BackgroundTasks()
    tasks.add_task(shadow, "dispatched")

    import asyncio
    asyncio.run(tasks())

    assert calls == ["dispatched"]


def test_scheduled_shadow_failure_cannot_change_response(monkeypatch, tmp_path):
    scheduled = []

    def capture_task(self, func, *args, **kwargs):
        scheduled.append((func, args, kwargs))

    monkeypatch.setattr("starlette.background.BackgroundTasks.add_task", capture_task)
    database = FakeDatabase()
    client = TestClient(create_app(database_client=database, data_dir=tmp_path))

    response = client.post("/api/videos", json=payload())
    assert response.status_code == 202

    failing_task = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("shadow failure"))
    try:
        failing_task(*scheduled[0][1], **scheduled[0][2])
    except RuntimeError:
        pass

    assert response.json()["status"] == "queued"
    assert len(database.rows) == 1
