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

    def visit(items, folders):
        for item in items:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("item"), list):
                visit(item["item"], [*folders, item.get("name", "그룹")])
                continue
            request = item.get("request")
            if not isinstance(request, dict):
                continue
            url = request.get("url", "")
            if isinstance(url, dict):
                url = url.get("raw", "")
            endpoints.append(Endpoint(
                folder=" / ".join(folders),
                name=item.get("name", "이름 없는 API"),
                method=str(request.get("method", "GET")).upper(),
                url=str(url),
                request=request,
                examples=item.get("response", []),
                scripts=item.get("event", []),
            ))

    visit(document["item"], [])
    return document, endpoints


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
