"""Ordered scenarios reference stable imported endpoint keys."""
import re

KEY = re.compile(r"^[a-f0-9]{64}$")


def validate_steps(steps, available_keys=None):
    if not isinstance(steps, list) or not steps or len(steps) > 200:
        raise ValueError("시나리오는 1~200개의 API 키 배열이어야 합니다.")
    if any(not isinstance(key, str) or not KEY.fullmatch(key) for key in steps):
        raise ValueError("API 키 형식이 올바르지 않습니다.")
    if available_keys is not None:
        missing = [key for key in steps if key not in set(available_keys)]
        if missing:
            raise ValueError("Collection에서 찾을 수 없는 API가 있습니다. 시나리오를 수정하세요.")
    return list(steps)


def resolve_steps(steps, endpoint_keys, endpoints):
    validated = validate_steps(steps, endpoint_keys)
    lookup = dict(zip(endpoint_keys, endpoints))
    return [(key, lookup[key]) for key in validated]


def should_stop(result_status: str, stop_on_failure: bool) -> bool:
    """Stop only on actual failure; user-disabled writes remain SKIPPED."""
    return bool(stop_on_failure and result_status in ("FAIL", "ERROR", "BLOCKED"))
