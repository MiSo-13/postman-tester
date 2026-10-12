"""Response preview sanitization and existing response persistence contract."""
import httpx
from app.response_preview import safe_json_preview
from app.runner import execute
from types import SimpleNamespace


def test_masks_strings_and_sensitive_named_fields():
    response = httpx.Response(200, json={
        "token": "secret-token", "profile": {
            "email": "person@example.test", "id": 42, "name": "someone",
            "notes": "private text", "active": True}})
    preview = safe_json_preview(response)
    assert "secret-token" not in preview
    assert "person@example.test" not in preview
    assert "someone" not in preview and "private text" not in preview
    assert '"id": 42' in preview
    assert "[REDACTED]" in preview and "[STRING REDACTED]" in preview


def test_drops_binary_and_oversize():
    assert "JSON이 아닌" in safe_json_preview(httpx.Response(200, content=b"binary"))
    assert "32KB" in safe_json_preview(httpx.Response(200, content=b"x" * 32769))


def test_runner_callback_does_not_modify_persisted_result():
    preview = []
    with httpx.Client(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"secret": "never persist", "ok": True}))) as client:
        result = execute(
            SimpleNamespace(method="GET", url="https://example.test",
                            request={"header": []}),
            {}, client=client, preview_callback=preview.append)
    assert result["status"] == "PASS"
    assert len(preview) == 1 and "never persist" not in preview[0]
    assert "preview" not in result and "secret" not in str(result)


def test_json_nested_limits():
    payload = {"items": [{"value": "hidden"} for _ in range(250)]}
    preview = safe_json_preview(httpx.Response(200, json=payload))
    assert preview.count("[STRING REDACTED]") == 200
