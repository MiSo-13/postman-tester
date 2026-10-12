"""Aggregate saved API execution history for the project dashboard.

Counts reflect completed result rows (not unique endpoints). Skipped requests
are excluded from the failure-rate denominator, while BLOCKED and ERROR count.
"""
from collections import defaultdict
from statistics import mean


def build_dashboard(runs, results_by_run, limit=30):
    if not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError("집계 회차 범위는 1~200이어야 합니다.")
    selected = [r for r in runs if r["status"] != "PENDING"][:limit]
    timeline = []
    grouped = defaultdict(lambda: {"name": "", "method": "", "url": "",
                                    "pass": 0, "fail": 0, "skipped": 0,
                                    "times": [], "latest": None, "latest_http": None})
    for run in reversed(selected):
        counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "BLOCKED": 0, "SKIPPED": 0}
        times = []
        for item in results_by_run.get(run["id"], []):
            status = item["status"]
            if status in counts:
                counts[status] += 1
            elapsed = item["elapsed_ms"]
            if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool) and elapsed >= 0:
                times.append(elapsed)
            key = (item["endpoint_name"], item["method"], item["url"])
            api = grouped[key]
            api["name"], api["method"], api["url"] = key
            if status == "PASS":
                api["pass"] += 1
            elif status == "SKIPPED":
                api["skipped"] += 1
            else:
                api["fail"] += 1
            if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool) and elapsed >= 0:
                api["times"].append(elapsed)
            api["latest"] = status
            api["latest_http"] = item["http_status"]
        executed = counts["PASS"] + counts["FAIL"] + counts["ERROR"] + counts["BLOCKED"]
        failures = executed - counts["PASS"]
        timeline.append({"run_id": run["id"], "name": run["name"],
                         "started_at": run["started_at"], "status": run["status"],
                         "pass": counts["PASS"], "fail": failures,
                         "skipped": counts["SKIPPED"], "executed": executed,
                         "failure_rate": round(failures / executed * 100, 2) if executed else None,
                         "avg_ms": round(mean(times), 2) if times else None})
    apis = []
    for api in grouped.values():
        executed = api["pass"] + api["fail"]
        apis.append({k: api[k] for k in ("name", "method", "url", "pass", "fail", "skipped",
                                         "latest", "latest_http")} | {
            "executed": executed,
            "failure_rate": round(api["fail"] / executed * 100, 2) if executed else None,
            "avg_ms": round(mean(api["times"]), 2) if api["times"] else None})
    apis.sort(key=lambda api: (
        -(api["failure_rate"] if api["failure_rate"] is not None else -1),
        -api["fail"], api["name"], api["method"], api["url"]))
    executed_total = sum(r["executed"] for r in timeline)
    fail_total = sum(r["fail"] for r in timeline)
    all_times = [v for api in grouped.values() for v in api["times"]]
    return {"runs": len(timeline), "executed": executed_total,
            "failures": fail_total, "skipped": sum(r["skipped"] for r in timeline),
            "failure_rate": round(fail_total / executed_total * 100, 2) if executed_total else None,
            "avg_ms": round(mean(all_times), 2) if all_times else None,
            "timeline": timeline, "apis": apis}
