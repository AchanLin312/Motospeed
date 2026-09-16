"""
地图快照相关 API。

v4.0 新增：提供地图快照功能，支持导出PNG/PDF格式。
"""
from flask import Blueprint, jsonify, request, send_file
from pathlib import Path

from ..services.map_snapshot_service import map_snapshot_service

snapshots_bp = Blueprint("snapshots", __name__)


@snapshots_bp.post("/create")
def create_snapshot():
    """创建地图快照（接收前端传来的图片文件或JSON数据）。"""
    try:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 检查是否是文件上传
        if 'image' in request.files:
            image_file = request.files['image']
            map_type = request.form.get('map_type', 'hotspot')
            
            snapshot_file = map_snapshot_service.output_dir / f"snapshot_{map_type}_{timestamp}.png"
            snapshot_file.parent.mkdir(parents=True, exist_ok=True)
            image_file.save(snapshot_file)
        else:
            # JSON格式（兼容旧接口）
            data = request.get_json() or {}
            map_type = data.get("map_type", "hotspot")
            image_data = data.get("image_data")
            
            if not image_data:
                return jsonify({"error": "缺少图片数据"}), 400
            
            snapshot_file = map_snapshot_service.output_dir / f"snapshot_{map_type}_{timestamp}.png"
            # 这里可以添加base64解码逻辑，暂时跳过
        
        # 生成元数据
        metadata = map_snapshot_service.generate_snapshot_metadata(
            map_type=map_type,
            view_bounds=data.get("view_bounds") if 'data' in locals() else None,
            filters=data.get("filters") if 'data' in locals() else None
        )

        # 保存快照信息
        info_file = map_snapshot_service.save_snapshot_info(snapshot_file, metadata)

        return jsonify({
            "success": True,
            "snapshot_file": str(snapshot_file),
            "info_file": str(info_file),
            "metadata": metadata
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@snapshots_bp.get("/list")
def list_snapshots():
    """列出所有快照。"""
    try:
        snapshots = map_snapshot_service.list_snapshots()
        return jsonify({
            "success": True,
            "snapshots": snapshots,
            "count": len(snapshots)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@snapshots_bp.get("/download/<snapshot_id>")
def download_snapshot(snapshot_id: str):
    """下载快照文件。"""
    try:
        # 查找快照文件
        snapshot_file = Path(f"outputs/snapshots/{snapshot_id}")
        if not snapshot_file.exists():
            return jsonify({"error": "快照文件不存在"}), 404

        return send_file(snapshot_file, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

