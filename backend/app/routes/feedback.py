"""
用户反馈模块 API。

围绕论文 4.2 “用户反馈”功能，支持交警/用户上传现场图片与备注。
"""
from pathlib import Path
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from ..services.feedback_service import save_feedback, list_feedback_records

feedback_bp = Blueprint("feedback", __name__)


def _extract_payload():
    """统一处理 JSON 或表单参数。"""
    if request.is_json:
        data = request.get_json() or {}
        files = {}
    else:
        data = request.form.to_dict()
        files = request.files
    return data, files


@feedback_bp.post("")
def submit_feedback():
    """接收现场反馈（JSON 或 multipart/form-data）。"""
    data, files = _extract_payload()
    photo = files.get("photo") if files else None
    photo_path = None
    if photo:
        filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secure_filename(photo.filename)}"
        upload_dir = Path(current_app.config["UPLOAD_DIR"]) / "feedback"
        upload_dir.mkdir(parents=True, exist_ok=True)
        photo_path = str(upload_dir / filename)
        photo.save(photo_path)

    result = save_feedback(
        content=data.get("content", ""),
        area_id=data.get("area_id"),
        user_type=data.get("user_type", "user"),
        lon=data.get("lon"),
        lat=data.get("lat"),
        photo_path=photo_path,
    )
    return jsonify(result)


@feedback_bp.get("")
def list_feedback():
    """列出本地缓存的反馈记录。"""
    records = list_feedback_records()
    return jsonify({"count": len(records), "records": records})


@feedback_bp.get("/history")
def get_feedback_history():
    """获取反馈历史记录（用于前端显示）。"""
    try:
        records = list_feedback_records()
        # 转换为前端需要的格式
        feedbacks = []
        for record in records:
            # 处理时间戳（可能是datetime对象、时间戳或ISO字符串）
            timestamp = record.get("timestamp") or record.get("created_at")
            timestamp_value = 0
            if timestamp:
                if isinstance(timestamp, datetime):
                    timestamp_value = int(timestamp.timestamp())
                elif isinstance(timestamp, str):
                    try:
                        # 尝试解析ISO格式
                        if 'T' in timestamp:
                            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            timestamp_value = int(dt.timestamp())
                        else:
                            timestamp_value = int(float(timestamp))
                    except:
                        timestamp_value = 0
                elif isinstance(timestamp, (int, float)):
                    timestamp_value = int(timestamp)
            
            feedbacks.append({
                "feedback_id": record.get("feedback_id") or record.get("id") or f"FB-{len(feedbacks)}",
                "timestamp": timestamp_value,
                "content": record.get("content", ""),
                "lon": record.get("lon"),
                "lat": record.get("lat"),
                "area_id": record.get("area_id"),
                "photo_path": record.get("photo_path")
            })
        
        # 按时间戳排序（降序）
        feedbacks.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return jsonify({"feedbacks": feedbacks})
    except Exception as e:
        current_app.logger.exception("获取反馈历史失败：%s", e)
        return jsonify({"error": str(e), "feedbacks": []}), 500


@feedback_bp.delete("/<feedback_id>")
def delete_feedback(feedback_id):
    """删除反馈记录。"""
    try:
        from ..services.feedback_service import delete_feedback_record
        result = delete_feedback_record(feedback_id)
        if result:
            return jsonify({"success": True, "message": "反馈已删除"})
        else:
            return jsonify({"error": "反馈记录不存在"}), 404
    except Exception as e:
        current_app.logger.exception("删除反馈失败：%s", e)
        return jsonify({"error": str(e)}), 500