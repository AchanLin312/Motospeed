"""
报告生成 API（3.0 新增）。
"""
from flask import Blueprint, jsonify, request, send_file

from ..services.report_generator import ReportGenerator

reports_bp = Blueprint("reports", __name__)


@reports_bp.post("/reports/risk-analysis")
def generate_risk_analysis_report():
    """生成风险分析综合报告。"""
    params = request.get_json(silent=True) or {}
    format_type = params.get("format", "word")  # word, excel, pdf
    include_charts = params.get("include_charts", True)

    try:
        generator = ReportGenerator()
        filepath = generator.generate_risk_analysis_report(format_type, include_charts)
        return jsonify({"filepath": filepath, "format": format_type})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@reports_bp.get("/reports/risk-analysis/download")
def download_risk_analysis_report():
    """下载风险分析报告。"""
    filepath = request.args.get("filepath")
    if not filepath:
        return jsonify({"error": "缺少文件路径参数"}), 400
    try:
        return send_file(filepath, as_attachment=True)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 404


@reports_bp.post("/reports/hotspot-export")
def generate_hotspot_export_report():
    """生成热点导出报告（用于周工作例会）。"""
    params = request.get_json(silent=True) or {}
    risk_level = params.get("risk_level")
    format_type = params.get("format", "excel")

    try:
        generator = ReportGenerator()
        filepath = generator.generate_hotspot_export_report(risk_level, format_type)
        return jsonify({"filepath": filepath, "format": format_type})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

