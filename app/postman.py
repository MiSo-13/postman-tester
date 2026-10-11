"""Read Postman v2.1 collections without executing embedded JavaScript."""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Endpoint:
    folder: str
    name: str
    method: str
    url: str
    request: dict
    examples: list
    scripts: list


def parse_collection(path: str | Path) -> tuple[dict, list[Endpoint]]:
    document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict) or not isinstance(document.get("item"), list):
        raise ValueError("올바른 Postman Collection JSON이 아닙니다.")
    endpoints = []

    def visit(items, folders, inherited_auth):
        for item in items:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("item"), list):
                folder_auth = item["auth"] if "auth" in item else inherited_auth
                visit(item["item"], [*folders, item.get("name", "그룹")], folder_auth)
                continue
            request = item.get("request")
            if not isinstance(request, dict):
                continue
            url = request.get("url", "")
            if isinstance(url, dict):
                url = url.get("raw", "")
            # Postman inheritance precedence: request > nearest folder > collection.
            # An explicit noauth clears inherited auth; a missing auth inherits.
            effective_request = dict(request)
            if "auth" not in effective_request and inherited_auth is not None:
                effective_request["auth"] = inherited_auth
            endpoints.append(Endpoint(
                folder=" / ".join(folders),
                name=item.get("name", "이름 없는 API"),
                method=str(request.get("method", "GET")).upper(),
                url=str(url),
                request=effective_request,
                examples=item.get("response", []),
                scripts=item.get("event", []),
            ))

    visit(document["item"], [], document.get("auth"))
    return document, endpoints


def endpoints_from_document(document: dict) -> list[Endpoint]:
    """Parse a stored collection without requiring its original file."""
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "collection.json"
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        return parse_collection(path)[1]


def parse_environment(path: str | Path) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(doc, dict) or not isinstance(doc.get("values"), list):
        raise ValueError("올바른 Postman Environment JSON이 아닙니다.")
    return {v["key"]: v.get("value", "") for v in doc["values"]
            if isinstance(v, dict) and v.get("enabled", True) and "key" in v}


def preview_body(endpoint: Endpoint) -> str:
    body = endpoint.request.get("body", {})
    if body.get("mode") == "raw":
        return str(body.get("raw", ""))
    return json.dumps(body, ensure_ascii=False, indent=2) if body else ""


def preview_response(endpoint: Endpoint) -> str:
    if not endpoint.examples:
        return "응답 예시가 없습니다."
    example = endpoint.examples[0]
    return str(example.get("body", "")) or json.dumps(example, ensure_ascii=False, indent=2)
