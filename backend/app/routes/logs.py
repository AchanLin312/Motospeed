"""
日志导出相关 API。

v4.0 新增：支持将操作日志、反馈记录导出为CSV格式。
"""
from flask import Blueprint, jsonify, request, send_file

from ..services.log_export_service import log_export_service

logs_bp = Blueprint("logs", __name__)


@logs_bp.post("/export")
def export_logs():
    """导出日志为CSV文件。"""
    try:
        data = request.get_json() or {}
        
        # 确保日志目录存在
        log_export_service.output_dir.mkdir(parents=True, exist_ok=True)
        
        csv_file = log_export_service.export_logs_to_csv(
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            operation_types=data.get("operation_types"),
            include_feedback=data.get("include_feedback", True),
            include_images=data.get("include_images", True)
        )
        
        # 确保文件已创建
        if not csv_file.exists():
            raise FileNotFoundError(f"日志文件创建失败：{csv_file}")

        return send_file(str(csv_file), as_attachment=True, download_name=csv_file.name)
    except Exception as e:
        from flask import current_app
        current_app.logger.exception("导出日志失败：%s", e)
        return jsonify({"error": str(e)}), 500


@logs_bp.get("/statistics")
def get_log_statistics():
    """获取日志统计信息。"""
    try:
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        
        stats = log_export_service.get_log_statistics(
            start_date=start_date,
            end_date=end_date
        )

        return jsonify({
            "success": True,
            "statistics": stats
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

