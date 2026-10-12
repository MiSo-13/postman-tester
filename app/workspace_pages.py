"""Standalone home and workspace overview panels for the desktop application."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame


class ProjectHome(QWidget):
    def __init__(self, create_project, import_collection, import_environment, parent=None):
        super().__init__(parent)
        self.setObjectName("ProjectHome")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        heading = QLabel("시작하기")
        heading.setObjectName("PageHeading")
        layout.addWidget(heading)
        self.description = QLabel("프로젝트를 생성하고 Postman Collection을 가져오세요.")
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        row = QHBoxLayout()
        self.create_button = QPushButton("새 프로젝트")
        self.create_button.clicked.connect(create_project)
        row.addWidget(self.create_button)
        self.collection_button = QPushButton("Collection 가져오기")
        self.collection_button.clicked.connect(import_collection)
        row.addWidget(self.collection_button)
        self.environment_button = QPushButton("Environment 가져오기")
        self.environment_button.clicked.connect(import_environment)
        row.addWidget(self.environment_button)
        layout.addLayout(row)
        layout.addStretch()

    def set_project_available(self, available):
        self.collection_button.setEnabled(available)
        self.environment_button.setEnabled(available)
        self.description.setText(
            "Collection과 Environment를 가져온 뒤 API 탐색으로 이동하세요."
            if available else "먼저 새 프로젝트를 생성하세요. 프로젝트가 필요한 기능은 비활성화됩니다.")


class WorkspaceOverview(QWidget):
    def __init__(self, title, description, actions, parent=None):
        super().__init__(parent)
        self.setObjectName("WorkspaceOverview")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        heading = QLabel(title)
        heading.setObjectName("PageHeading")
        layout.addWidget(heading)
        message = QLabel(description)
        message.setWordWrap(True)
        layout.addWidget(message)
        self.buttons = {}
        for label, callback in actions:
            button = QPushButton(label)
            button.clicked.connect(callback)
            layout.addWidget(button)
            self.buttons[label] = button
        layout.addStretch()
