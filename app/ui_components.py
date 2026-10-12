"""Composable developer-tool UI primitives: navigation, header, searchable API explorer."""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
                             QPushButton, QComboBox, QLineEdit, QTreeWidget)


class ProjectHeader(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProjectHeader")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 9, 14, 9)
        brand = QLabel("◈  POSTMAN TESTER")
        brand.setObjectName("Brand")
        row.addWidget(brand)
        row.addSpacing(20)
        row.addWidget(QLabel("프로젝트"))
        self.projects = QComboBox()
        self.projects.setMinimumWidth(180)
        row.addWidget(self.projects, 1)
        row.addWidget(QLabel("테마"))
        self.theme_selector = QComboBox()
        row.addWidget(self.theme_selector)


class NavigationSidebar(QFrame):
    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.setObjectName("NavigationSidebar")
        self.setFixedWidth(190)
        self.buttons = {}
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 16, 10, 12)
        column.setSpacing(5)
        for group, entries in actions:
            title = QLabel(group.upper())
            title.setObjectName("NavGroup")
            column.addWidget(title)
            for label, callback in entries:
                button = QPushButton(label)
                button.setObjectName("NavAction")
                button.setToolTip(label)
                button.setMinimumHeight(34)
                button.clicked.connect(callback)
                column.addWidget(button)
                self.buttons[label] = button
            column.addSpacing(14)
        column.addStretch()


class EndpointExplorer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EndpointExplorer")
        column = QVBoxLayout(self)
        column.setContentsMargins(8, 10, 8, 8)
        column.addWidget(QLabel("API EXPLORER"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("API 이름 / URL 검색")
        self.search.setClearButtonEnabled(True)
        column.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["API", "Method"])
        column.addWidget(self.tree, 1)
        self.search.textChanged.connect(self.apply_filter)

    def apply_filter(self, text):
        query = text.strip().casefold()
        root = self.tree.invisibleRootItem()

        def visit(item):
            matched = not query or any(
                query in item.text(col).casefold() for col in range(item.columnCount()))
            child_results = [visit(item.child(i)) for i in range(item.childCount())]
            child_match = any(child_results)
            item.setHidden(not (matched or child_match))
            if query and child_match:
                item.setExpanded(True)
            return matched or child_match

        for i in range(root.childCount()):
            visit(root.child(i))
