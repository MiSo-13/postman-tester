"""Safety and functional checks for response-to-assertion workflow."""
import json
import pytest

from app.response_assertion_candidates import candidates_from_preview, rule_from_candidate


def test_numeric_boolean_and_array_candidates():
    preview = json.dumps({"data": {"items": [{"id": 42, "active": True,
                    "email": "[REDACTED]", "label": "[STRING REDACTED]"}]}})
    found = dict(candidates_from_preview(preview))
    assert found["data.items[0].id"] == 42
    assert found["data.items[0].active"] is True
    assert rule_from_candidate("data.items[0].id", 42, "equals") == {
        "type": "equals", "path": "data.items[0].id", "expected": 42}
    assert rule_from_candidate("data.items[0].active", True, "value_type")["expected"] == "boolean"
    assert rule_from_candidate("data.items", found["data.items"], "value_type")["expected"] == "array"
    assert rule_from_candidate("data.items[0].email", found["data.items[0].email"], "exists")["type"] == "exists"


@pytest.mark.parametrize("kind", ["equals", "value_type"])
def test_masked_value_cannot_create_unsafe_rule(kind):
    with pytest.raises(ValueError):
        rule_from_candidate("data.email", "[REDACTED]", kind)


def test_does_not_create_candidate_from_unavailable_or_unsafe_path():
    assert candidates_from_preview("JSON 응답이 아닙니다") == []
    found = dict(candidates_from_preview('{"__internal": 1, "valid": 2, "bad.key": 3}'))
    assert list(found) == ["valid"]
    assert len(candidates_from_preview(json.dumps({"items": list(range(500))}))) <= 200


def test_dialog_chooses_field_and_generates_rule():
    from PyQt6.QtWidgets import QApplication
    from app.response_field_dialog import ResponseFieldRuleDialog
    app = QApplication.instance() or QApplication([])
    dialog = ResponseFieldRuleDialog('{"data":{"items":[{"id":42}]}}')
    for row in range(dialog.tree.topLevelItemCount()):
        item = dialog.tree.topLevelItem(row)
        if item.text(0) == "data.items[0].id":
            dialog.tree.setCurrentItem(item)
            break
    else:
        pytest.fail("required field not found")
    dialog.kind.setCurrentIndex(dialog.kind.findData("equals"))
    dialog.accept()
    assert dialog.rule["path"] == "data.items[0].id"
    assert dialog.rule["expected"] == 42
    assert app is not None
