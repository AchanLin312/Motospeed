import json
import os
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QObject, pyqtSlot, QUrl
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QDateEdit,
    QCheckBox,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from ui import services


class MapBridge(QObject):
    mapClickedSignal = pyqtSignal(float, float)

    @pyqtSlot(float, float)
    def mapClicked(self, lon: float, lat: float):
        self.mapClickedSignal.emit(lon, lat)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("数治骑迹 - 交互式主界面")
        self.setGeometry(50, 50, 1400, 900)

        self.selected_file = None
        self.current_batch_id = None
        self.analysis_output = None
        self.selected_photo_path = None

        self._init_style()
        self._init_layout()
        self._init_map_views()
        self._update_status("请选择功能开始操作")

    def _init_style(self):
        self.setStyleSheet(
            """
            QMainWindow { background-color: #F5F8FF; }
            QPushButton {
                background-color: #165DFF;
                color: #FFFFFF;
                border-radius: 8px;
                height: 38px;
                font-weight: 500;
            }
            QPushButton:hover { background-color: #0E42D2; }
            QPushButton:disabled { background-color: #AABFF7; }
            QLabel { color: #333333; font-size: 13px; }
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E8F3FF;
                border-radius: 8px;
                gridline-color: #E8F3FF;
            }
            QTextEdit, QLineEdit, QComboBox, QDateEdit {
                background-color: #FFFFFF;
                border: 1px solid #E8F3FF;
                border-radius: 8px;
                padding: 6px;
            }
            """
        )

    def _init_layout(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 左侧功能区
        self.left_widget = QWidget()
        self.left_widget.setFixedWidth(300)
        left_layout = QVBoxLayout(self.left_widget)
        left_layout.setSpacing(12)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.buttons = {}
        for text in ["数据上传", "风险识别", "预警推送", "应对建议", "用户反馈"]:
            btn = QPushButton(text)
            btn.clicked.connect(lambda checked, name=text: self.switch_function(name))
            self.buttons[text] = btn
            left_layout.addWidget(btn)

        self.operation_stack = QStackedWidget()
        self.operation_stack.addWidget(self._create_upload_panel())
        self.operation_stack.addWidget(self._create_analysis_panel())
        self.operation_stack.addWidget(self._create_alert_panel())
        self.operation_stack.addWidget(self._create_recommend_panel())
        self.operation_stack.addWidget(self._create_feedback_panel())
        left_layout.addWidget(self.operation_stack, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(
            "background-color:#E8F3FF;color:#165DFF;border-radius:6px;padding:6px;"
        )
        left_layout.addWidget(self.status_label)

        # 右侧结果区
        self.right_widget = QWidget()
        right_layout = QVBoxLayout(self.right_widget)
        right_layout.setSpacing(12)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.result_stack = QStackedWidget()
        self.result_stack.addWidget(self._create_upload_result())
        self.result_stack.addWidget(self._create_analysis_result())
        self.result_stack.addWidget(self._create_alert_result())
        self.result_stack.addWidget(self._create_recommend_result())
        self.result_stack.addWidget(self._create_feedback_result())
        right_layout.addWidget(self.result_stack)

        self.bottom_status = QLabel("当前无上传数据 | 坐标系：WGS-84 (EPSG:4326)")
        self.bottom_status.setStyleSheet("color:#666666;")
        right_layout.addWidget(self.bottom_status)

        main_layout.addWidget(self.left_widget)
        main_layout.addWidget(self.right_widget, stretch=1)

    def _create_upload_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("📁 轨迹 CSV 文件"))
        self.file_path_label = QLabel("未选择文件")
        self.file_path_label.setStyleSheet("color:#666666;")
        layout.addWidget(self.file_path_label)
        select_btn = QPushButton("选择文件")
        select_btn.clicked.connect(self.select_csv_file)
        layout.addWidget(select_btn)
        self.upload_btn = QPushButton("上传并解析")
        self.upload_btn.setEnabled(False)
        self.upload_btn.clicked.connect(self.upload_csv_data)
        layout.addWidget(self.upload_btn)
        layout.addStretch()
        return panel

    def _create_analysis_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("🔍 空间分析算法"))
        self.algorithm_checks = {}
        for text in ["全局Moran's I", "局部Moran's I", "Gi*热点", "Mann-Kendall"]:
            cb = QCheckBox(text)
            cb.setChecked(text != "Mann-Kendall")
            self.algorithm_checks[text] = cb
            layout.addWidget(cb)
        self.analysis_btn = QPushButton("开始分析")
        self.analysis_btn.clicked.connect(self.run_analysis)
        layout.addWidget(self.analysis_btn)
        layout.addStretch()
        return panel

    def _create_alert_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("⚠️ 预警筛选"))
        self.alert_level_combo = QComboBox()
        self.alert_level_combo.addItems(["all", "high", "medium", "low"])
        layout.addWidget(self.alert_level_combo)
        self.alert_start = QDateEdit()
        self.alert_start.setCalendarPopup(True)
        self.alert_end = QDateEdit()
        self.alert_end.setCalendarPopup(True)
        layout.addWidget(self.alert_start)
        layout.addWidget(self.alert_end)
        filter_btn = QPushButton("筛选热点")
        filter_btn.clicked.connect(self.apply_alert_filters)
        layout.addWidget(filter_btn)
        export_btn = QPushButton("导出预警列表")
        export_btn.clicked.connect(self.export_alerts)
        layout.addWidget(export_btn)
        layout.addStretch()
        return panel

    def _create_recommend_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("🧠 自动生成应对策略"))
        generate_btn = QPushButton("生成建议")
        generate_btn.clicked.connect(self.generate_recommendations)
        layout.addWidget(generate_btn)
        layout.addStretch()
        return panel

    def _create_feedback_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("📝 反馈提交"))
        self.feedback_user_combo = QComboBox()
        self.feedback_user_combo.addItems(["交警", "普通用户"])
        layout.addWidget(self.feedback_user_combo)
        self.feedback_title = QLineEdit()
        self.feedback_title.setPlaceholderText("反馈标题")
        layout.addWidget(self.feedback_title)
        self.feedback_content = QTextEdit()
        self.feedback_content.setPlaceholderText("反馈内容（支持文字描述现场情况）")
        layout.addWidget(self.feedback_content)
        coord_layout = QHBoxLayout()
        self.feedback_lon = QLineEdit()
        self.feedback_lon.setPlaceholderText("经度")
        self.feedback_lat = QLineEdit()
        self.feedback_lat.setPlaceholderText("纬度")
        coord_layout.addWidget(self.feedback_lon)
        coord_layout.addWidget(self.feedback_lat)
        layout.addLayout(coord_layout)
        photo_btn = QPushButton("上传现场照片")
        photo_btn.clicked.connect(self.select_photo)
        layout.addWidget(photo_btn)
        self.photo_preview = QLabel("无照片")
        self.photo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo_preview.setStyleSheet("background:#FFFFFF;border:1px dashed #E8F3FF;height:120px;")
        layout.addWidget(self.photo_preview)
        submit_btn = QPushButton("提交反馈")
        submit_btn.clicked.connect(self.submit_feedback)
        layout.addWidget(submit_btn)
        layout.addStretch()
        return panel

    def _create_upload_result(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.upload_table = QTableWidget()
        self.upload_table.setColumnCount(5)
        self.upload_table.setHorizontalHeaderLabels(
            ["批次ID", "文件名", "数量", "时间范围", "坐标范围"]
        )
        layout.addWidget(self.upload_table)
        return panel

    def _create_analysis_result(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # 3.5 新增：地图类型选择控件
        map_type_layout = QHBoxLayout()
        map_type_layout.addWidget(QLabel("地图类型："))
        self.map_type_combo = QComboBox()
        self.map_type_combo.addItems(["热点地图", "LISA聚类图", "演化模式分布图"])
        self.map_type_combo.currentTextChanged.connect(self.on_map_type_changed)
        map_type_layout.addWidget(self.map_type_combo)
        map_type_layout.addStretch()
        refresh_map_btn = QPushButton("刷新地图")
        refresh_map_btn.clicked.connect(self.refresh_current_map)
        map_type_layout.addWidget(refresh_map_btn)
        layout.addLayout(map_type_layout)
        
        self.analysis_map_view = QWebEngineView()
        layout.addWidget(self.analysis_map_view, stretch=2)
        
        indicator_layout = QHBoxLayout()
        self.moran_label = QLabel("全局Moran's I：--")
        self.hotspot_label = QLabel("热点数：--")
        self.highrisk_label = QLabel("高风险区域：--")
        for lbl in [self.moran_label, self.hotspot_label, self.highrisk_label]:
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                "background:#FFFFFF;border:1px solid #E8F3FF;border-radius:8px;padding:12px;font-size:14px;"
            )
            indicator_layout.addWidget(lbl)
        layout.addLayout(indicator_layout)
        self.risk_table = QTableWidget()
        self.risk_table.setColumnCount(3)
        self.risk_table.setHorizontalHeaderLabels(["风险等级", "区域数量", "轨迹数"])
        layout.addWidget(self.risk_table, stretch=1)
        return panel

    def _create_alert_result(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.alert_map_view = QWebEngineView()
        layout.addWidget(self.alert_map_view, stretch=2)
        self.alert_table = QTableWidget()
        self.alert_table.setColumnCount(5)
        self.alert_table.setHorizontalHeaderLabels(
            ["区域ID", "风险等级", "时间范围", "中心经度", "中心纬度"]
        )
        layout.addWidget(self.alert_table, stretch=1)
        return panel

    def _create_recommend_result(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.recommend_text = QTextEdit()
        self.recommend_text.setReadOnly(True)
        layout.addWidget(self.recommend_text)
        return panel

    def _create_feedback_result(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.feedback_map_view = QWebEngineView()
        layout.addWidget(self.feedback_map_view, stretch=2)
        self.feedback_table = QTableWidget()
        self.feedback_table.setColumnCount(5)
        self.feedback_table.setHorizontalHeaderLabels(
            ["反馈ID", "类型", "标题", "时间", "坐标"]
        )
        layout.addWidget(self.feedback_table, stretch=1)
        return panel

    def _init_map_views(self):
        template = PROJECT_ROOT / "ui" / "map_template.html"
        url = QUrl.fromLocalFile(str(template))

        self.analysis_bridge = MapBridge()
        self.alert_bridge = MapBridge()
        self.feedback_bridge = MapBridge()
        self.feedback_bridge.mapClickedSignal.connect(self._update_feedback_coords)

        for view, bridge in [
            (self.analysis_map_view, self.analysis_bridge),
            (self.alert_map_view, self.alert_bridge),
            (self.feedback_map_view, self.feedback_bridge),
        ]:
            channel = QWebChannel()
            channel.registerObject("qtBridge", bridge)
            view.page().setWebChannel(channel)
            view.setUrl(url)

    def _update_status(self, text: str):
        self.status_label.setText(text)

    def switch_function(self, name: str):
        index = ["数据上传", "风险识别", "预警推送", "应对建议", "用户反馈"].index(name)
        self.operation_stack.setCurrentIndex(index)
        self.result_stack.setCurrentIndex(index)
        for btn_name, btn in self.buttons.items():
            btn.setStyleSheet(
                "background-color:#165DFF;color:#FFFFFF;border-radius:8px;height:38px;font-weight:500;"
            )
        self.buttons[name].setStyleSheet(
            "background-color:#0E42D2;color:#FFFFFF;border-radius:8px;height:38px;font-weight:700;"
        )
        self._update_status(f"当前功能：{name}")

    # ---------------- 功能逻辑 ----------------
    def select_csv_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择轨迹 CSV 文件", str(PROJECT_ROOT), "CSV Files (*.csv)"
        )
        if file_path:
            self.selected_file = file_path
            self.file_path_label.setText(f"已选择：{Path(file_path).name}")
            self.upload_btn.setEnabled(True)

    def upload_csv_data(self):
        if not self.selected_file:
            self._update_status("请选择 CSV 文件")
            return
        try:
            info = services.process_csv_upload(self.selected_file)
            self.current_batch_id = info["batch_id"]
            self._update_status(f"上传成功，共 {info['data_count']} 条记录")
            self.bottom_status.setText(
                f"当前批次：{info['batch_id']} | 坐标系：WGS-84 (EPSG:4326)"
            )
            self._refresh_upload_table()
        except Exception as exc:
            self._update_status(f"上传失败：{exc}")

    def _refresh_upload_table(self):
        self.upload_table.setRowCount(0)
        for batch in services.data_batches.values():
            row = self.upload_table.rowCount()
            self.upload_table.insertRow(row)
            for col, value in enumerate(
                [
                    batch.batch_id,
                    batch.file_name,
                    batch.data_count,
                    batch.time_range,
                    batch.coord_range,
                ]
            ):
                self.upload_table.setItem(row, col, QTableWidgetItem(str(value)))

    def run_analysis(self):
        if not self.current_batch_id:
            self._update_status("请先上传数据批次")
            return
        algorithms = [
            name for name, btn in self.algorithm_checks.items() if btn.isChecked()
        ]
        if not algorithms:
            self._update_status("请选择至少一个算法")
            return
        try:
            self.analysis_output = services.run_spatial_analysis(
                self.current_batch_id, algorithms
            )
            geojson = services.generate_hotspot_geojson(self.current_batch_id)
            self._load_geojson(self.analysis_map_view, geojson)
            self._load_geojson(self.alert_map_view, geojson)
            self._load_geojson(self.feedback_map_view, geojson)
            self._update_analysis_result()
            self._update_alert_table()
            # 3.5 新增：分析完成后刷新当前地图类型
            self.refresh_current_map()
            self._update_status("分析完成")
        except Exception as exc:
            self._update_status(f"分析失败：{exc}")

    def _load_geojson(self, view: QWebEngineView, geojson: dict):
        script = f"loadHotspotGeoJSON({json.dumps(geojson, ensure_ascii=False)});"
        view.page().runJavaScript(script)

    def _load_lisa_geojson(self, view: QWebEngineView, geojson: dict):
        """加载 LISA 聚类 GeoJSON 到地图。"""
        script = f"loadLISAClusterGeoJSON({json.dumps(geojson, ensure_ascii=False)});"
        view.page().runJavaScript(script)

    def _load_evolution_geojson(self, view: QWebEngineView, geojson: dict):
        """加载演化模式 GeoJSON 到地图。"""
        script = f"loadEvolutionPatternGeoJSON({json.dumps(geojson, ensure_ascii=False)});"
        view.page().runJavaScript(script)

    def on_map_type_changed(self, map_type: str):
        """地图类型切换回调。"""
        self.refresh_current_map()

    def refresh_current_map(self):
        """刷新当前选中的地图类型。"""
        map_type = self.map_type_combo.currentText()
        if map_type == "热点地图":
            self._load_hotspot_map()
        elif map_type == "LISA聚类图":
            self._load_lisa_map()
        elif map_type == "演化模式分布图":
            self._load_evolution_map()

    def _load_hotspot_map(self):
        """加载热点地图。"""
        try:
            geojson = services.generate_hotspot_geojson(self.current_batch_id)
            self._load_geojson(self.analysis_map_view, geojson)
        except Exception as exc:
            self._update_status(f"加载热点地图失败：{exc}")

    def _load_lisa_map(self):
        """加载 LISA 聚类图。"""
        try:
            geojson = services.get_lisa_cluster_geojson()
            self._load_lisa_geojson(self.analysis_map_view, geojson)
        except Exception as exc:
            self._update_status(f"加载LISA聚类图失败：{exc}")

    def _load_evolution_map(self):
        """加载演化模式分布图。"""
        try:
            geojson = services.get_evolution_pattern_geojson()
            self._load_evolution_geojson(self.analysis_map_view, geojson)
        except Exception as exc:
            self._update_status(f"加载演化模式分布图失败：{exc}")

    def _update_analysis_result(self):
        summary = self.analysis_output["summary"]
        hotspots = self.analysis_output["hotspots"]
        if "全局Moran's I" in summary:
            m = summary["全局Moran's I"]
            self.moran_label.setText(
                f"全局Moran's I：{m['moran_i']:.3f} (p={m['p_value']:.3f})"
            )
        self.hotspot_label.setText(f"热点数：{len(hotspots)}")
        high = sum(1 for h in hotspots if h["risk_level"] == "high")
        self.highrisk_label.setText(f"高风险区域：{high}")

        level_map = {"high": "高", "medium": "中", "low": "低"}
        self.risk_table.setRowCount(0)
        for level_cn, level in [("高", "high"), ("中", "medium"), ("低", "low")]:
            count = sum(1 for h in hotspots if h["risk_level"] == level)
            traj = sum(h["trajectory_count"] for h in hotspots if h["risk_level"] == level)
            row = self.risk_table.rowCount()
            self.risk_table.insertRow(row)
            self.risk_table.setItem(row, 0, QTableWidgetItem(level_cn))
            self.risk_table.setItem(row, 1, QTableWidgetItem(str(count)))
            self.risk_table.setItem(row, 2, QTableWidgetItem(str(traj)))

    def apply_alert_filters(self):
        if not self.current_batch_id:
            self._update_status("请先上传并分析数据")
            return
        risk_level = self.alert_level_combo.currentText()
        try:
            geojson = services.generate_hotspot_geojson(self.current_batch_id)
            if risk_level != "all":
                geojson["features"] = [
                    f for f in geojson["features"] if f["properties"]["risk_level"] == risk_level
                ]
            self._load_geojson(self.alert_map_view, geojson)
            self._update_alert_table(risk_level)
            self._update_status("筛选完成")
        except Exception as exc:
            self._update_status(f"筛选失败：{exc}")

    def _update_alert_table(self, risk_level: str = "all"):
        if not self.analysis_output:
            return
        records = self.analysis_output["hotspots"]
        if risk_level != "all":
            records = [r for r in records if r["risk_level"] == risk_level]
        self.alert_table.setRowCount(0)
        for item in records:
            row = self.alert_table.rowCount()
            self.alert_table.insertRow(row)
            values = [
                item.get("area_id"),
                item.get("risk_level"),
                item.get("time_slice"),
                f"{item.get('grid_lon'):.5f}",
                f"{item.get('grid_lat'):.5f}",
            ]
            for col, value in enumerate(values):
                self.alert_table.setItem(row, col, QTableWidgetItem(str(value)))

    def export_alerts(self):
        if not self.current_batch_id:
            self._update_status("请先上传并分析数据")
            return
        level = self.alert_level_combo.currentText()
        try:
            path = services.export_alert_list(self.current_batch_id, level)
            self._update_status(f"导出成功：{path}")
        except Exception as exc:
            self._update_status(f"导出失败：{exc}")

    def generate_recommendations(self):
        if not self.current_batch_id:
            self._update_status("请先完成风险分析")
            return
        try:
            text = services.build_recommendation_text(self.current_batch_id)
            self.recommend_text.setPlainText(text or "暂无热点数据，无法生成建议")
            self._update_status("已生成应对建议")
        except Exception as exc:
            self._update_status(f"生成失败：{exc}")

    def select_photo(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择现场照片", str(PROJECT_ROOT), "Images (*.png *.jpg *.jpeg)"
        )
        if file_path:
            self.selected_photo_path = file_path
            pixmap = QPixmap(file_path).scaled(200, 150, Qt.AspectRatioMode.KeepAspectRatio)
            self.photo_preview.setPixmap(pixmap)

    def submit_feedback(self):
        title = self.feedback_title.text().strip()
        content = self.feedback_content.toPlainText().strip()
        if not title or not content:
            self._update_status("请填写标题和内容")
            return
        record = services.save_feedback_record(
            user_type=self.feedback_user_combo.currentText(),
            title=title,
            content=content,
            lon=self.feedback_lon.text() or None,
            lat=self.feedback_lat.text() or None,
            photo_path=self.selected_photo_path,
        )
        self._update_status("反馈提交成功")
        self._refresh_feedback_table()
        self.feedback_title.clear()
        self.feedback_content.clear()
        self.feedback_lon.clear()
        self.feedback_lat.clear()
        self.photo_preview.clear()
        self.photo_preview.setText("无照片")

    def _refresh_feedback_table(self):
        records = services.list_feedback_records()
        self.feedback_table.setRowCount(0)
        for record in records:
            row = self.feedback_table.rowCount()
            self.feedback_table.insertRow(row)
            coord = (
                f"{record['lon']}, {record['lat']}"
                if record.get("lon") and record.get("lat")
                else "-"
            )
            values = [
                record["feedback_id"],
                record["user_type"],
                record["title"],
                record["created_at"],
                coord,
            ]
            for col, value in enumerate(values):
                self.feedback_table.setItem(row, col, QTableWidgetItem(str(value)))

    def _update_feedback_coords(self, lon: float, lat: float):
        self.feedback_lon.setText(f"{lon:.6f}")
        self.feedback_lat.setText(f"{lat:.6f}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

