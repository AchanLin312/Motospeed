"""
风险识别与预警相关 API。

提供一键分析、热点查询、导出等接口，对应论文 3、4 章节。
"""
from flask import Blueprint, jsonify, request

from ..services.risk_analysis import (
    execute_analysis,
    latest_analysis_summary,
)
from ..services.hotspot_export import (
    query_hotspots_geojson,
    export_hotspots_csv,
)

analysis_bp = Blueprint("analysis", __name__)


@analysis_bp.post("/analysis")
def trigger_analysis():
    """执行完整的风险识别流程。"""
    params = request.get_json(silent=True) or {}
    try:
        result = execute_analysis(params)
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@analysis_bp.get("/analysis")
def get_latest_analysis():
    """获取最近一次分析摘要。"""
    try:
        summary = latest_analysis_summary()
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(summary)


@analysis_bp.get("/hotspots/geojson")
def hotspots_geojson():
    """获取热点区域 GeoJSON (WGS-84)。"""
    risk_level = request.args.get("riskLevel")
    start_time = request.args.get("startTime")
    end_time = request.args.get("endTime")
    geojson = query_hotspots_geojson(risk_level, start_time, end_time)
    return jsonify(geojson)


@analysis_bp.get("/export")
@analysis_bp.get("/hotspots/export")
def hotspots_export():
    """批量导出热点 CSV。"""
    risk_level = request.args.get("riskLevel")
    start_time = request.args.get("startTime")
    end_time = request.args.get("endTime")
    try:
        paths = export_hotspots_csv(risk_level, start_time, end_time)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(paths)


