"""Usage counters for local AI-planning requests, not account-wide billing."""
FIELDS = ("input_tokens", "output_tokens", "total_tokens", "cached_tokens", "reasoning_tokens")


def parse_usage(response):
    raw = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(raw, dict):
        return None
    details_in = raw.get("input_tokens_details") or {}
    details_out = raw.get("output_tokens_details") or {}
    values = {
        "input_tokens": raw.get("input_tokens"),
        "output_tokens": raw.get("output_tokens"),
        "total_tokens": raw.get("total_tokens"),
        "cached_tokens": details_in.get("cached_tokens") if isinstance(details_in, dict) else None,
        "reasoning_tokens": details_out.get("reasoning_tokens") if isinstance(details_out, dict) else None,
    }
    if any(type(values[k]) is not int or values[k] < 0 for k in FIELDS[:3]):
        return None
    for field in FIELDS[3:]:
        if type(values[field]) is not int or values[field] < 0:
            values[field] = 0
    return values


def add_usage(total, usage):
    if usage is None:
        return total.copy()
    return {key: total.get(key, 0) + usage.get(key, 0) for key in FIELDS}


def empty_usage():
    return {key: 0 for key in FIELDS}


def usage_summary(usage):
    if usage is None:
        return "토큰 사용량 정보 없음"
    return (f"입력 {usage['input_tokens']:,} · 출력 {usage['output_tokens']:,} · "
            f"합계 {usage['total_tokens']:,} · 캐시 {usage['cached_tokens']:,} · "
            f"추론 {usage['reasoning_tokens']:,}")
