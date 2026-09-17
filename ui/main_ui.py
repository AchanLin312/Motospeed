"""数治骑迹 V2 桌面壳：全屏内嵌 V2 Web 工作台（需后端先运行）。"""
import sys
from pathlib import Path

import requests

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

PROJECT_ROOT = Path(__file__).resolve().parents[1]
V2_ROOT = "http://127.0.0.1:5000"

BACKEND_DOWN_HTML = """
<html><body style="font-family:'Microsoft YaHei',sans-serif;background:#F5F8FF;
     display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
  <div style="text-align:center;">
    <h2 style="color:#d93025;">后端未启动</h2>
    <p style="color:#333;">请先运行 <b>start_desktop.bat</b> 或在项目根目录执行
       <b>venv\\Scripts\\python.exe backend\\run.py</b>，然后点击顶部「重新加载」。</p>
  </div>
</body></html>
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("数治骑迹 - V2 工作台")
        self.setGeometry(50, 50, 1400, 900)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部工具条：标题 + 后端状态 + 重新加载
        bar = QWidget()
        bar.setStyleSheet("background-color:#165DFF;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(14, 6, 14, 6)
        bar_layout.setSpacing(12)
        title = QLabel("数治骑迹 V2 工作台")
        title.setStyleSheet("color:#FFFFFF;font-size:14px;font-weight:600;")
        self.status_label = QLabel("正在检查后端...")
        self.status_label.setStyleSheet("color:#D6E4FF;font-size:12px;")
        reload_btn = QPushButton("重新加载")
        reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reload_btn.setStyleSheet(
            "QPushButton{background:#FFFFFF;color:#165DFF;border:none;"
            "border-radius:4px;padding:4px 14px;font-size:12px;}"
            "QPushButton:hover{background:#E8F3FF;}"
        )
        reload_btn.clicked.connect(self.reload_view)
        bar_layout.addWidget(title)
        bar_layout.addStretch()
        bar_layout.addWidget(self.status_label)
        bar_layout.addWidget(reload_btn)

        # 全屏内嵌 V2 页面
        self.view = QWebEngineView()
        layout.addWidget(bar)
        layout.addWidget(self.view, stretch=1)

        self.reload_view()

    def _backend_ready(self) -> bool:
        try:
            r = requests.get(f"{V2_ROOT}/health", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def reload_view(self):
        if self._backend_ready():
            self.view.load(QUrl(f"{V2_ROOT}/"))
            self.status_label.setText(f"后端已连接 {V2_ROOT}")
        else:
            self.view.setHtml(BACKEND_DOWN_HTML, QUrl("http://localhost/"))
            self.status_label.setText("后端未启动：请先运行 start_desktop.bat")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
