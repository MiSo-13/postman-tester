"""Select safe failed requests from saved results without replaying writes."""
SAFE_METHODS = frozenset(("GET", "HEAD", "OPTIONS"))
FAILED = frozenset(("FAIL", "ERROR", "BLOCKED"))


def retry_candidates(results, endpoints, endpoint_keys):
    """Return unique, read-only failed endpoints in their original result order."""
    lookup = {}
    for key, endpoint in zip(endpoint_keys, endpoints):
        identity = (endpoint.name, endpoint.method.upper(), endpoint.url)
        lookup.setdefault(identity, []).append((key, endpoint))
    selected = []
    seen = set()
    for result in results:
        method = str(result["method"]).upper()
        if result["status"] not in FAILED or method not in SAFE_METHODS:
            continue
        identity = (result["endpoint_name"], method, result["url"])
        matches = lookup.get(identity, [])
        # Fail closed on renamed, deleted, or ambiguous matching requests.
        if len(matches) != 1:
            continue
        key, endpoint = matches[0]
        if key not in seen:
            selected.append((key, endpoint))
            seen.add(key)
    return selected
