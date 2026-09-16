"""
图表生成 API（3.6 新增）。
"""
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file

from ..services.chart_generator import ChartGenerator

charts_bp = Blueprint("charts", __name__)
chart_gen = ChartGenerator()


@charts_bp.post("/charts/dashboard")
def generate_dashboard_chart():
    """生成综合仪表盘图表。"""
    try:
        filepath = chart_gen.generate_dashboard_chart()
        return jsonify({"success": True, "chart_path": str(filepath), "filepath": str(filepath)})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@charts_bp.get("/charts/dashboard/download")
@charts_bp.get("/charts/trend/download")
@charts_bp.get("/charts/time-distribution/download")
def download_chart():
    """下载图表文件。"""
    filepath = request.args.get("filepath")
    if not filepath:
        return jsonify({"error": "缺少文件路径参数"}), 400
    try:
        from pathlib import Path
        chart_path = Path(filepath)
        if not chart_path.exists():
            return jsonify({"error": "图表文件不存在"}), 404
        return send_file(str(chart_path), mimetype='image/png', as_attachment=True)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 404


@charts_bp.post("/charts/trend")
def generate_trend_chart():
    """生成趋势折线图。"""
    params = request.get_json(silent=True) or {}
    
    # 支持自定义日期范围
    if "start_date" in params and "end_date" in params:
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        try:
            filepath = chart_gen.generate_trend_chart(start_date=start_date, end_date=end_date)
            return jsonify({"success": True, "chart_path": str(filepath), "filepath": str(filepath)})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
    else:
        # 按天数
        days_value = params.get("days", 30)
        # 支持"all"字符串或0值表示全量数据
        if days_value == "all" or days_value == 0:
            days = 0  # 0表示全量数据
        else:
            days = int(days_value)
        try:
            filepath = chart_gen.generate_trend_chart(days=days)
            return jsonify({"success": True, "chart_path": str(filepath), "filepath": str(filepath)})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 400


@charts_bp.post("/charts/time-distribution")
def generate_time_distribution_chart():
    """生成时段分布柱状图。"""
    try:
        filepath = chart_gen.generate_time_distribution_chart()
        return jsonify({"success": True, "chart_path": str(filepath), "filepath": str(filepath)})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@charts_bp.get("/charts/list")
def list_charts():
    """列出所有已生成的图表文件。"""
    import os
    chart_files = []
    chart_dir = chart_gen.output_dir
    if chart_dir.exists():
        for file in sorted(chart_dir.glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True):
            chart_files.append({
                "filename": file.name,
                "filepath": str(file),
                "size": file.stat().st_size,
                "modified": datetime.fromtimestamp(file.stat().st_mtime).isoformat(),
            })
    return jsonify({"charts": chart_files[:20]})  # 返回最近20个

