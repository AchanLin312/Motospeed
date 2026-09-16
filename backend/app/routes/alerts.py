"""
预警推送 API（3.0 新增）。
"""
from flask import Blueprint, jsonify, request

from ..services.alert_service import AlertService

alerts_bp = Blueprint("alerts", __name__)
alert_service = AlertService()


@alerts_bp.post("/alerts/generate")
def generate_alerts():
    """基于最新分析结果自动生成预警。"""
    try:
        alerts = alert_service.generate_alerts_from_analysis()
        return jsonify({
            "count": len(alerts),
            "alerts": alerts,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@alerts_bp.get("/alerts")
def list_alerts():
    """获取预警列表。"""
    alert_level = request.args.get("alert_level")
    status = request.args.get("status")

    try:
        alerts = alert_service.load_all_alerts(alert_level, status)
        return jsonify({
            "count": len(alerts),
            "alerts": alerts,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@alerts_bp.post("/alerts/<alert_id>/read")
def mark_alert_read(alert_id: str):
    """标记预警为已读。"""
    try:
        alert_service.mark_alert_read(alert_id)
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@alerts_bp.post("/alerts/<alert_id>/handle")
def mark_alert_handled(alert_id: str):
    """标记预警为已处置。"""
    try:
        alert_service.mark_alert_handled(alert_id)
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@alerts_bp.get("/alerts/statistics")
def get_alert_statistics():
    """获取预警统计信息。"""
    try:
        stats = alert_service.get_alert_statistics()
        return jsonify(stats)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

