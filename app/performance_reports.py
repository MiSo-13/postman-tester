"""Per-run performance analysis using persisted metadata only."""
from datetime import datetime
from html import escape
from math import ceil, isfinite
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font


def percentile(values, percent):
    """Nearest-rank percentile, defined only for nonempty finite samples."""
    values = sorted(float(x) for x in values
                    if isinstance(x, (int, float)) and not isinstance(x, bool)
                    and isfinite(x) and x >= 0)
    if not values:
        return None
    return round(values[max(0, ceil(percent / 100 * len(values)) - 1)], 2)


def performance_summary(run, rows):
    latencies = [r.get("elapsed_ms") for r in rows]
    measured = [x for x in latencies if isinstance(x, (int, float))
                and not isinstance(x, bool) and isfinite(x) and x >= 0]
    start = datetime.fromisoformat(run["started_at"])
    end = datetime.fromisoformat(run["finished_at"]) if run.get("finished_at") else None
    seconds = max(0.0, (end - start).total_seconds()) if end else None
    completed = sum(r["status"] != "SKIPPED" for r in rows)
    retries = sum(max(0, int(r.get("retry_count", 0))) for r in rows)
    return {
        "run_id": run["id"], "name": run["name"], "status": run["status"],
        "requests": len(rows), "executed": completed,
        "skipped": len(rows) - completed, "retries": retries,
        "measurements": len(measured),
        "p50_ms": percentile(measured, 50),
        "p95_ms": percentile(measured, 95),
        "p99_ms": percentile(measured, 99),
        "elapsed_seconds": round(seconds, 3) if seconds is not None else None,
        "rps": round(completed / seconds, 3) if seconds and seconds > 0 else None,
    }


METRICS = [
    ("run_id", "실행 ID"), ("name", "회차명"), ("status", "상태"),
    ("requests", "전체 결과 건수"), ("executed", "SKIPPED 제외 건수"),
    ("skipped", "SKIPPED 건수"), ("retries", "총 재시도 횟수"),
    ("measurements", "응답 시간 측정 건수"), ("p50_ms", "P50 (ms)"),
    ("p95_ms", "P95 (ms)"), ("p99_ms", "P99 (ms)"),
    ("elapsed_seconds", "실행 소요 시간 (초)"),
    ("rps", "RPS (SKIPPED 제외 / 전체 회차 경과 시간)"),
]


def export_performance_report(storage, run_id, output_directory: Path):
    run = storage.get_run(run_id)
    if run is None or run.get("finished_at") is None:
        raise ValueError("완료된 실행 회차만 성능 보고서를 생성할 수 있습니다.")
    summary = performance_summary(run, storage.results(run_id))
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    xlsx_path = output_directory / f"{run_id}_performance.xlsx"
    html_path = output_directory / f"{run_id}_performance.html"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Performance"
    sheet.append(["지표", "값"])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for key, label in METRICS:
        value = summary[key]
        # Avoid Excel formula interpretation of arbitrary run names.
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
            value = "'" + value
        sheet.append([label, value])
    sheet.column_dimensions["A"].width = 54
    sheet.column_dimensions["B"].width = 45
    workbook.save(xlsx_path)
    table = "".join(
        f"<tr><th>{escape(label)}</th><td>{escape(str(summary[key] if summary[key] is not None else '—'))}</td></tr>"
        for key, label in METRICS)
    html_path.write_text(
        "<!doctype html><html lang='ko'><meta charset='utf-8'>"
        "<title>실행 성능 보고서</title><style>"
        "body{font:14px sans-serif;margin:32px;max-width:900px}"
        "table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #ddd;padding:9px;text-align:left}"
        "th{background:#edf1f5}</style>"
        "<h1>실행 성능 보고서</h1><table>" + table + "</table>"
        "<p>백분위수: 최근접 순위 방식. P50/P95/P99는 측정된 API 응답 시간만 사용합니다."
        " RPS는 SKIPPED를 제외한 요청 결과 건수를 전체 실행 경과 시간으로 나눈 값입니다."
        " 로그인, 재시도 대기, 보고서 생성 시간 등 조건에 영향을 받으므로 부하시험 RPS와 동일하지 않습니다.</p>"
        "</html>", encoding="utf-8")
    storage.save_report(run_id, "performance_xlsx", xlsx_path)
    storage.save_report(run_id, "performance_html", html_path)
    return [xlsx_path, html_path]
