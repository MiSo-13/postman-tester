"""Compare saved runs without reading response bodies or secrets."""
from collections import defaultdict


def compare_runs(before, after):
    """Pair duplicate endpoints by occurrence; report transitions and elapsed deltas."""
    groups_a, groups_b = defaultdict(list), defaultdict(list)
    for row in before:
        groups_a[(row["endpoint_name"], row["method"], row["url"])].append(row)
    for row in after:
        groups_b[(row["endpoint_name"], row["method"], row["url"])].append(row)
    output = []
    for identity in sorted(set(groups_a) | set(groups_b)):
        left, right = groups_a[identity], groups_b[identity]
        for idx in range(max(len(left), len(right))):
            a = left[idx] if idx < len(left) else None
            b = right[idx] if idx < len(right) else None
            old = a["status"] if a else None
            new = b["status"] if b else None
            if a is None:
                change = "ADDED"
            elif b is None:
                change = "REMOVED"
            elif old == new:
                change = "UNCHANGED"
            elif old != "PASS" and new == "PASS":
                change = "RECOVERED"
            elif old == "PASS" and new != "PASS":
                change = "REGRESSED"
            else:
                change = "CHANGED"
            prior_ms = a["elapsed_ms"] if a else None
            latest_ms = b["elapsed_ms"] if b else None
            delta = (round(latest_ms - prior_ms, 2) if
                     isinstance(prior_ms, (int, float)) and
                     isinstance(latest_ms, (int, float)) else None)
            output.append({
                "name": identity[0], "method": identity[1], "url": identity[2],
                "occurrence": idx + 1, "before": old, "after": new,
                "change": change,
                "before_http": a["http_status"] if a else None,
                "after_http": b["http_status"] if b else None,
                "delta_ms": delta,
            })
    return output
