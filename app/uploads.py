"""Validate Postman multipart fields before opening files or sending HTTP."""
import mimetypes
from pathlib import Path

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def prepare_formdata(body: dict, variables: dict, file_root: Path):
    from .runner import substitute

    entries = body.get("formdata")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Form-data 항목이 없습니다.")
    if file_root is None:
        raise ValueError("업로드 기준 디렉터리가 설정되지 않았습니다.")
    root = Path(file_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("업로드 기준 경로가 디렉터리가 아닙니다.")

    fields = []
    files = []
    total_bytes = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Form-data 항목 형식이 올바르지 않습니다.")
        if entry.get("disabled", False):
            continue
        key = entry.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("Form-data 필드 이름이 없습니다.")
        kind = entry.get("type", "text")
        if kind == "text":
            value = substitute(str(entry.get("value", "")), variables)
            fields.append((key, value))
        elif kind == "file":
            source = entry.get("src")
            if not isinstance(source, str) or not source.strip():
                raise ValueError(f"{key}: 파일 경로가 비어 있습니다.")
            source = substitute(source, variables)
            candidate = Path(source)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError(f"{key}: 상대 경로만 허용됩니다.")
            target = (root / candidate).resolve(strict=True)
            if not target.is_relative_to(root) or not target.is_file():
                raise ValueError(f"{key}: 허용된 파일 디렉터리 내부의 파일이어야 합니다.")
            if target.is_symlink():
                raise ValueError(f"{key}: 심볼릭 링크는 업로드할 수 없습니다.")
            size = target.stat().st_size
            total_bytes += size
            if total_bytes > MAX_UPLOAD_BYTES:
                raise ValueError("전체 업로드 크기는 20 MiB를 초과할 수 없습니다.")
            media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            files.append((key, target, media_type))
        else:
            raise ValueError(f"{key}: 지원하지 않는 Form-data 유형입니다.")
    if not fields and not files:
        raise ValueError("활성화된 Form-data 항목이 없습니다.")
    return fields, files
