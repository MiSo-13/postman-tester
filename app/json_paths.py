"""Bounded JSON object/array paths: a.b[0].c; no wildcards or evaluation."""
import re

_SEGMENT = re.compile(r"[A-Za-z0-9-]+|\[(0|[1-9][0-9]{0,5})\]")


def path_parts(path):
    if not isinstance(path, str) or not path or len(path) > 256:
        raise ValueError("JSON 경로는 1~256자여야 합니다.")
    output = []
    for segment in path.split("."):
        if not segment or segment.startswith("_"):
            raise ValueError("JSON 경로가 올바르지 않습니다.")
        pos = 0
        while pos < len(segment):
            match = _SEGMENT.match(segment, pos)
            if not match:
                raise ValueError("객체 키와 [숫자] 배열 인덱스만 허용합니다.")
            value = match.group()
            if value.startswith("["):
                output.append(int(match.group(1)))
            else:
                if pos != 0:
                    raise ValueError("객체 키는 배열 인덱스 뒤에 바로 올 수 없습니다.")
                output.append(value)
            pos = match.end()
    if len(output) > 32:
        raise ValueError("JSON 경로의 깊이는 32 이하이어야 합니다.")
    return output


def find_path(document, path):
    node = document
    for part in path_parts(path):
        if type(part) is int:
            if not isinstance(node, list) or part >= len(node):
                return False, None
            node = node[part]
        else:
            if not isinstance(node, dict) or part not in node:
                return False, None
            node = node[part]
    return True, node
