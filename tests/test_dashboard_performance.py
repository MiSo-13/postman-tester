"""Batch history loading remains scoped and chart rendering tolerates gaps."""
from app.storage import Storage


def test_batch_results_and_project_isolation(tmp_path):
    store = Storage(tmp_path)
    p1 = store.create_project("one")
    p2 = store.create_project("two")
    a = store.create_run(p1, "old")
    b = store.create_run(p1, "new")
    other = store.create_run(p2, "private")
    for run_id in (a, b, other):
        store.add_result(run_id, "sample", "GET", "https://example.test",
                         "PASS", 200, 13, "")
    rows = store.results_for_runs(p1, [a, b, other])
    assert len(rows[a]) == len(rows[b]) == 1
    assert rows[other] == []
    assert store.results_for_runs(p1, []) == {}
    assert len(store.results_for_runs(p1, [a, a])[a]) == 1


def test_batch_query_limit(tmp_path):
    store = Storage(tmp_path)
    try:
        store.results_for_runs("project", ["any"] * 201)
    except ValueError:
        pass
    else:
        raise AssertionError("batch limit must reject oversize request")


def test_trend_chart_headless(qtbot=None):
    # Construct and render in a headless Qt application, without network access.
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QPixmap
    from app.trend_chart import TrendChart
    app = QApplication.instance() or QApplication([])
    chart = TrendChart([None, 10, 20, None, 15], "실패율")
    chart.resize(500, 240)
    image = QPixmap(chart.size())
    chart.render(image)
    assert not image.isNull()
    empty = TrendChart([None, None], "응답 시간")
    empty.resize(500, 240)
    empty.render(QPixmap(empty.size()))
    assert app is not None
