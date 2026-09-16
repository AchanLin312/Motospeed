"""
可视化 API（3.0 新增）。
"""
from flask import Blueprint, jsonify, request

from ..services.visualization_service import VisualizationService

visualizations_bp = Blueprint("visualizations", __name__)
viz_service = VisualizationService()


@visualizations_bp.get("/visualizations/lisa-cluster/geojson")
def get_lisa_cluster_geojson():
    """获取 LISA 聚类 GeoJSON 数据（供 UI 直接使用）。"""
    try:
        geojson = viz_service.get_lisa_cluster_geojson()
        return jsonify(geojson)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@visualizations_bp.post("/visualizations/lisa-cluster-map")
def generate_lisa_cluster_map():
    """生成 LISA 聚类图 HTML 文件（用于导出）。"""
    try:
        filepath = viz_service.generate_lisa_cluster_map()
        return jsonify({"filepath": filepath})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@visualizations_bp.get("/visualizations/evolution-pattern/geojson")
def get_evolution_pattern_geojson():
    """获取演化模式 GeoJSON 数据（供 UI 直接使用）。"""
    try:
        geojson = viz_service.get_evolution_pattern_geojson()
        return jsonify(geojson)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@visualizations_bp.post("/visualizations/evolution-pattern-map")
def generate_evolution_pattern_map():
    """生成演化模式分布图 HTML 文件（用于导出）。"""
    try:
        filepath = viz_service.generate_evolution_pattern_map()
        return jsonify({"filepath": filepath})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@visualizations_bp.get("/visualizations/dashboard")
def get_dashboard_data():
    """获取综合仪表盘数据。"""
    try:
        data = viz_service.generate_dashboard_data()
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@visualizations_bp.get("/visualizations/trend-chart")
def get_trend_chart_data():
    """获取趋势折线图数据。"""
    area_id = request.args.get("area_id")
    days = int(request.args.get("days", 30))

    try:
        data = viz_service.generate_trend_chart_data(area_id, days)
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@visualizations_bp.get("/visualizations/time-distribution")
def get_time_distribution_chart():
    """获取时段分布柱状图数据。"""
    area_id = request.args.get("area_id")

    try:
        data = viz_service.generate_time_distribution_chart(area_id)
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

