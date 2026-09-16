"""
结构化报告生成模块（3.0 新增）。

支持生成 Word/PDF/Excel 格式的风险分析报告、热点分析报告、趋势分析报告。
面向一线警务实战，提供可直接用于工作例会的结构化文档。
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from ..utils.geojson import load_geojson_file
from .runtime_pipeline import (
    RUNTIME_DIR,
    SUMMARY_FILE,
    HOTSPOT_FILE,
    GRID_FILE,
    TRAJECTORY_FILE,
)


class ReportGenerator:
    """报告生成器，支持多格式输出。"""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or (Path(__file__).resolve().parents[3] / "outputs" / "reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_risk_analysis_report(
        self,
        format_type: str = "word",
        include_charts: bool = True,
    ) -> str:
        """
        生成风险分析综合报告。

        Args:
            format_type: "word", "pdf", "excel"
            include_charts: 是否包含图表（Word/PDF支持）

        Returns:
            生成文件的路径
        """
        if not SUMMARY_FILE.exists():
            raise FileNotFoundError("尚未执行风险分析，无法生成报告")

        with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
            summary = json.load(f)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"风险分析报告_{timestamp}"

        if format_type == "word":
            return self._generate_word_report(summary, filename, include_charts)
        elif format_type == "excel":
            return self._generate_excel_report(summary, filename)
        elif format_type == "pdf":
            # PDF 生成需要额外依赖，这里先返回 Word 路径
            word_path = self._generate_word_report(summary, filename, include_charts)
            return word_path
        else:
            raise ValueError(f"不支持的报告格式: {format_type}")

    def _generate_word_report(
        self,
        summary: Dict[str, Any],
        filename: str,
        include_charts: bool,
    ) -> str:
        """生成 Word 格式报告。"""
        doc = Document()
        doc.core_properties.title = "电动车超速预警平台 - 风险分析报告"
        doc.core_properties.author = "电动车超速预警平台"

        # 标题
        title = doc.add_heading("电动车超速行为风险分析报告", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # 报告信息
        info_para = doc.add_paragraph()
        info_para.add_run(f"生成时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n")
        info_para.add_run(f"分析批次：{summary.get('generated_at', '未知')}\n")
        info_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        doc.add_paragraph()  # 空行

        # 一、执行摘要
        doc.add_heading("一、执行摘要", 1)
        doc.add_paragraph(
            f"本次分析共识别 {summary.get('hotspot_count', 0)} 个风险热点区域，"
            f"覆盖 {summary.get('grid_count', 0)} 个分析网格。"
            f"全局空间自相关指数（Moran's I）为 {summary.get('global_moran', {}).get('moran_i', 0):.3f}，"
            f"p 值为 {summary.get('global_moran', {}).get('p_value', 0):.3f}。"
        )

        # 二、空间自相关分析
        doc.add_heading("二、空间自相关分析", 1)
        moran = summary.get("global_moran", {})
        doc.add_paragraph(f"全局 Moran's I 指数：{moran.get('moran_i', 0):.4f}")
        doc.add_paragraph(f"期望值：{moran.get('expected_i', 0):.4f}")
        doc.add_paragraph(f"Z 统计量：{moran.get('z_score', 0):.4f}")
        doc.add_paragraph(f"p 值：{moran.get('p_value', 0):.4f}")

        significance = "显著" if moran.get("p_value", 1) <= 0.05 else "不显著"
        pattern = "集聚" if moran.get("moran_i", 0) > moran.get("expected_i", 0) else "分散"
        doc.add_paragraph(
            f"空间自相关类型：{significance}的{pattern}模式。"
            f"建议对高-高聚类区域实施一级管控措施。"
        )

        # 三、时空热点分析
        doc.add_heading("三、时空热点分析", 1)
        hotspots = self._load_hotspots_data()
        high_risk = [h for h in hotspots if h.get("risk_level") == "high"]
        medium_risk = [h for h in hotspots if h.get("risk_level") == "medium"]
        low_risk = [h for h in hotspots if h.get("risk_level") == "low"]

        doc.add_paragraph(f"高风险热点数量：{len(high_risk)} 个")
        doc.add_paragraph(f"中风险热点数量：{len(medium_risk)} 个")
        doc.add_paragraph(f"低风险热点数量：{len(low_risk)} 个")

        # 热点列表表格
        if hotspots:
            doc.add_heading("3.1 热点区域列表", 2)
            table = doc.add_table(rows=1, cols=6)
            table.style = "Light Grid Accent 1"
            hdr_cells = table.rows[0].cells
            headers = ["区域ID", "区域名称", "风险等级", "Gi* Z值", "轨迹数", "时间窗口"]
            for i, header in enumerate(headers):
                hdr_cells[i].text = header
                hdr_cells[i].paragraphs[0].runs[0].font.bold = True

            for hotspot in hotspots[:20]:  # 限制前20个
                row_cells = table.add_row().cells
                row_cells[0].text = str(hotspot.get("area_id", ""))
                row_cells[1].text = str(hotspot.get("area_name", ""))
                risk_cn = {"high": "高", "medium": "中", "low": "低"}.get(
                    hotspot.get("risk_level"), "未知"
                )
                row_cells[2].text = risk_cn
                row_cells[3].text = f"{hotspot.get('gi_score', 0):.2f}"
                row_cells[4].text = str(hotspot.get("trajectory_count", 0))
                row_cells[5].text = str(hotspot.get("time_slice", ""))

        # 四、趋势分析
        doc.add_heading("四、趋势分析", 1)
        trend = summary.get("trend", {})
        trend_type = trend.get("trend", "无显著趋势")
        zmk = trend.get("zmk", 0)
        doc.add_paragraph(f"Mann-Kendall 趋势检验结果：{trend_type}")
        doc.add_paragraph(f"ZMK 值：{zmk:.4f}")

        if abs(zmk) > 2.58:
            alert = "红色预警" if zmk > 0 else "管控有效"
            doc.add_paragraph(f"预警等级：{alert}")

        # 五、应对建议
        doc.add_heading("五、应对建议", 1)
        doc.add_paragraph("基于热点分析结果，建议采取以下措施：")
        doc.add_paragraph(
            "1. 高风险区域：部署固定警力2名，配备AI抓拍设备1套，设置临时减速带。",
            style="List Bullet",
        )
        doc.add_paragraph(
            "2. 中风险区域：加强巡逻频次，在高峰时段增派移动警力。",
            style="List Bullet",
        )
        doc.add_paragraph(
            "3. 低风险区域：保持常态化巡查，跟踪后续趋势变化。",
            style="List Bullet",
        )

        # 六、附录
        doc.add_heading("六、技术参数", 1)
        doc.add_paragraph(f"网格大小：{summary.get('cell_size_deg', 0):.6f} 度（约 {summary.get('cell_size_deg', 0) * 111:.0f} 米）")
        doc.add_paragraph(f"超速阈值：{summary.get('overspeed_threshold', 20)} km/h")
        doc.add_paragraph(f"坐标系：WGS-84 (EPSG:4326)")

        # 保存
        filepath = self.output_dir / f"{filename}.docx"
        doc.save(str(filepath))
        return str(filepath)

    def _generate_excel_report(self, summary: Dict[str, Any], filename: str) -> str:
        """生成 Excel 格式报告。"""
        wb = Workbook()
        wb.remove(wb.active)  # 删除默认sheet

        # Sheet 1: 执行摘要
        ws_summary = wb.create_sheet("执行摘要")
        ws_summary.merge_cells("A1:B1")
        ws_summary["A1"] = "电动车超速行为风险分析报告"
        ws_summary["A1"].font = Font(size=16, bold=True)
        ws_summary["A1"].alignment = Alignment(horizontal="center", vertical="center")

        row = 3
        ws_summary[f"A{row}"] = "生成时间"
        ws_summary[f"B{row}"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row += 1
        ws_summary[f"A{row}"] = "热点总数"
        ws_summary[f"B{row}"] = summary.get("hotspot_count", 0)
        row += 1
        ws_summary[f"A{row}"] = "网格总数"
        ws_summary[f"B{row}"] = summary.get("grid_count", 0)
        row += 1
        ws_summary[f"A{row}"] = "全局Moran's I"
        ws_summary[f"B{row}"] = summary.get("global_moran", {}).get("moran_i", 0)
        row += 1
        ws_summary[f"A{row}"] = "p值"
        ws_summary[f"B{row}"] = summary.get("global_moran", {}).get("p_value", 0)

        # Sheet 2: 热点列表
        ws_hotspots = wb.create_sheet("热点列表")
        headers = ["区域ID", "区域名称", "风险等级", "Gi* Z值", "轨迹数", "中心经度", "中心纬度", "时间窗口"]
        for col, header in enumerate(headers, 1):
            cell = ws_hotspots.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            cell.font = Font(bold=True, color="FFFFFF")
            cell.alignment = Alignment(horizontal="center")

        hotspots = self._load_hotspots_data()
        for idx, hotspot in enumerate(hotspots, 2):
            ws_hotspots.cell(row=idx, column=1, value=hotspot.get("area_id", ""))
            ws_hotspots.cell(row=idx, column=2, value=hotspot.get("area_name", ""))
            risk_cn = {"high": "高", "medium": "中", "low": "低"}.get(
                hotspot.get("risk_level"), "未知"
            )
            ws_hotspots.cell(row=idx, column=3, value=risk_cn)
            ws_hotspots.cell(row=idx, column=4, value=hotspot.get("gi_score", 0))
            ws_hotspots.cell(row=idx, column=5, value=hotspot.get("trajectory_count", 0))
            ws_hotspots.cell(row=idx, column=6, value=hotspot.get("center_lon", 0))
            ws_hotspots.cell(row=idx, column=7, value=hotspot.get("center_lat", 0))
            ws_hotspots.cell(row=idx, column=8, value=hotspot.get("time_slice", ""))

        # 调整列宽
        for col in range(1, len(headers) + 1):
            ws_hotspots.column_dimensions[get_column_letter(col)].width = 15

        # Sheet 3: 空间统计指标
        ws_stats = wb.create_sheet("空间统计指标")
        moran = summary.get("global_moran", {})
        stats_data = [
            ["指标", "数值"],
            ["全局Moran's I", moran.get("moran_i", 0)],
            ["期望值", moran.get("expected_i", 0)],
            ["Z统计量", moran.get("z_score", 0)],
            ["p值", moran.get("p_value", 0)],
            ["趋势ZMK值", summary.get("trend", {}).get("zmk", 0)],
            ["趋势类型", summary.get("trend", {}).get("trend", "无显著趋势")],
        ]
        for row_idx, row_data in enumerate(stats_data, 1):
            for col_idx, value in enumerate(row_data, 1):
                cell = ws_stats.cell(row=row_idx, column=col_idx, value=value)
                if row_idx == 1:
                    cell.font = Font(bold=True)
                    cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                    cell.font = Font(bold=True, color="FFFFFF")

        filepath = self.output_dir / f"{filename}.xlsx"
        wb.save(str(filepath))
        return str(filepath)

    def _load_hotspots_data(self) -> List[Dict[str, Any]]:
        """加载热点数据。"""
        if not HOTSPOT_FILE.exists():
            return []
        geojson = load_geojson_file(HOTSPOT_FILE)
        hotspots = []
        for feature in geojson.get("features", []):
            props = feature.get("properties", {})
            hotspots.append({
                "area_id": props.get("area_id"),
                "area_name": props.get("area_name"),
                "risk_level": props.get("risk_level"),
                "gi_score": props.get("gi_score", props.get("gi_z", 0)),
                "trajectory_count": props.get("trajectory_count", 0),
                "center_lon": props.get("center_lon", 0),
                "center_lat": props.get("center_lat", 0),
                "time_slice": props.get("time_slice", ""),
            })
        return hotspots

    def generate_hotspot_export_report(
        self,
        risk_level: Optional[str] = None,
        format_type: str = "excel",
    ) -> str:
        """生成热点导出报告（用于周工作例会）。"""
        hotspots = self._load_hotspots_data()
        if risk_level and risk_level != "all":
            hotspots = [h for h in hotspots if h.get("risk_level") == risk_level]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"热点导出_{risk_level or '全部'}_{timestamp}"

        if format_type == "excel":
            wb = Workbook()
            ws = wb.active
            ws.title = "热点列表"

            headers = ["区域ID", "区域名称", "风险等级", "Gi* Z值", "轨迹数", "中心经度", "中心纬度", "时间窗口", "管控建议"]
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="D32F2F", end_color="D32F2F", fill_type="solid")
                cell.font = Font(bold=True, color="FFFFFF")

            for idx, hotspot in enumerate(hotspots, 2):
                ws.cell(row=idx, column=1, value=hotspot.get("area_id", ""))
                ws.cell(row=idx, column=2, value=hotspot.get("area_name", ""))
                risk_cn = {"high": "高", "medium": "中", "low": "低"}.get(
                    hotspot.get("risk_level"), "未知"
                )
                ws.cell(row=idx, column=3, value=risk_cn)
                ws.cell(row=idx, column=4, value=hotspot.get("gi_score", 0))
                ws.cell(row=idx, column=5, value=hotspot.get("trajectory_count", 0))
                ws.cell(row=idx, column=6, value=hotspot.get("center_lon", 0))
                ws.cell(row=idx, column=7, value=hotspot.get("center_lat", 0))
                ws.cell(row=idx, column=8, value=hotspot.get("time_slice", ""))
                # 简单管控建议
                if hotspot.get("risk_level") == "high":
                    ws.cell(row=idx, column=9, value="一级管控：固定警力2名+AI抓拍")
                elif hotspot.get("risk_level") == "medium":
                    ws.cell(row=idx, column=9, value="二级管控：加强巡逻")
                else:
                    ws.cell(row=idx, column=9, value="三级管控：常态化巡查")

            for col in range(1, len(headers) + 1):
                ws.column_dimensions[get_column_letter(col)].width = 18

            filepath = self.output_dir / f"{filename}.xlsx"
            wb.save(str(filepath))
            return str(filepath)
        else:
            raise ValueError(f"不支持格式: {format_type}")

