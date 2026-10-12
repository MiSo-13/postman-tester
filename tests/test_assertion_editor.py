"""Rule editor input conversion and Qt dialog interactions."""
import pytest

from app.assertion_editor_model import parse_rule_fields, describe_rule


@pytest.mark.parametrize("values,expected", [
    (("status", "", "201"), {"type": "status", "expected": 201}),
    (("exists", "data.users[0].id"), {"type": "exists", "path": "data.users[0].id"}),
    (("equals", "data.name", '"tester"'),
     {"type": "equals", "path": "data.name", "expected": "tester"}),
    (("equals", "data.active", "true"),
     {"type": "equals", "path": "data.active", "expected": True}),
    (("value_type", "data.users", "array"),
     {"type": "value_type", "path": "data.users", "expected": "array"}),
])
def test_parse_editor_fields(values, expected):
    assert parse_rule_fields(*values) == expected


def test_range_and_length_fields():
    assert parse_rule_fields("range", "data.age", minimum="18", maximum="65") == {
        "type": "range", "path": "data.age", "min": 18, "max": 65}
    assert parse_rule_fields("length", "data.users", minimum="1") == {
        "type": "length", "path": "data.users", "min": 1}


@pytest.mark.parametrize("args", [
    ("equals", "data.id", "not-json"),
    ("range", "data.id", "", "false"),
    ("length", "data.users", "", "-1"),
    ("value_type", "data.id", "wrong"),
    ("status", "", "abc"),
    ("exists", "data.users[*]"),
])
def test_invalid_entries_are_rejected(args):
    with pytest.raises(ValueError):
        parse_rule_fields(*args)


def test_rule_descriptions():
    assert "HTTP 상태" in describe_rule({"type": "status", "expected": 200})
    assert "data.age" in describe_rule(
        {"type": "range", "path": "data.age", "min": 18})


def test_editor_add_modify_remove_and_cancel():
    from PyQt6.QtWidgets import QApplication
    from app.assertion_editor import AssertionRuleEditor
    app = QApplication.instance() or QApplication([])
    dialog = AssertionRuleEditor([{"type": "status", "expected": 200}])
    assert len(dialog.rules) == 1
    dialog.kind.setCurrentIndex(dialog.kind.findData("equals"))
    dialog.path.setText("data.users[0].id")
    dialog.expected.setText("42")
    dialog.add_rule()
    assert len(dialog.rules) == 2
    assert dialog.rules[1]["expected"] == 42
    dialog.table.selectRow(1)
    dialog.expected.setText("43")
    dialog.replace_rule()
    assert dialog.rules[1]["expected"] == 43
    dialog.table.selectRow(1)
    dialog.remove_rule()
    assert len(dialog.rules) == 1
    dialog.reject()
    assert len(dialog.rules) == 1
    assert app is not None


def test_editor_limit_of_twenty_rules():
    from PyQt6.QtWidgets import QApplication
    from app.assertion_editor import AssertionRuleEditor
    from unittest.mock import patch
    app = QApplication.instance() or QApplication([])
    dialog = AssertionRuleEditor([{"type": "status", "expected": 200}] * 20)
    dialog.kind.setCurrentIndex(dialog.kind.findData("status"))
    dialog.expected.setText("201")
    with patch("app.assertion_editor.QMessageBox.warning") as warning:
        dialog.add_rule()
    assert len(dialog.rules) == 20
    assert warning.called
    assert app is not None
