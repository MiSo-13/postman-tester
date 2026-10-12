"""Connection reuse and cancellation regression tests."""
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from app.runner import execute


def endpoint(index):
    return SimpleNamespace(method="GET", name=f"api-{index}",
                           url=f"https://example.test/{index}",
                           request={"header": []})


def test_injected_client_reused_for_multiple_requests():
    requests = []
    def handler(request):
        requests.append(request.url.path)
        return httpx.Response(200)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with patch("app.runner.httpx.Client") as constructor:
            first = execute(endpoint(1), {}, client=client)
            second = execute(endpoint(2), {}, client=client)
            constructor.assert_not_called()
    assert [first["status"], second["status"]] == ["PASS", "PASS"]
    assert requests == ["/1", "/2"]


def test_cancel_stops_between_requests_and_closes_client(tmp_path):
    from app.main_window import RunWorker
    from app.storage import Storage
    from app.settings import Settings

    storage = Storage(tmp_path / "data")
    project = storage.create_project("cancellation")
    run_id = storage.create_run(project, "cancel")
    worker = RunWorker(storage, run_id,
                       [(str(i), endpoint(i)) for i in range(3)],
                       {}, Settings(tmp_path), {})
    calls = []
    def mocked_execute(*args, **kwargs):
        calls.append(kwargs.get("client"))
        worker.cancel()
        return {"status": "PASS", "http_status": 200,
                "elapsed_ms": 2, "detail": ""}
    with patch("app.main_window.execute", side_effect=mocked_execute):
        worker.run()
    assert len(calls) == 1
    assert calls[0].is_closed
    assert storage.runs(project)[0]["status"] == "CANCELLED"
    assert len(storage.results(run_id)) == 1


def test_worker_uses_one_client_for_all_steps(tmp_path):
    from app.main_window import RunWorker
    from app.storage import Storage
    from app.settings import Settings

    storage = Storage(tmp_path / "data")
    project = storage.create_project("reuse")
    run_id = storage.create_run(project, "reuse")
    worker = RunWorker(storage, run_id,
                       [(str(i), endpoint(i)) for i in range(3)],
                       {}, Settings(tmp_path), {})
    clients = []
    def mocked_execute(*args, **kwargs):
        clients.append(kwargs["client"])
        return {"status": "PASS", "http_status": 200,
                "elapsed_ms": 2, "detail": ""}
    with patch("app.main_window.execute", side_effect=mocked_execute):
        worker.run()
    assert len(clients) == 3
    assert clients[0] is clients[1] is clients[2]
    assert clients[0].is_closed
    assert storage.runs(project)[0]["status"] == "COMPLETED"
