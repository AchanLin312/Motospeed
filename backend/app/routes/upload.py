"""
数据上传相关 API。

依据论文 1.2 研究目标中的"构建风险行为数据集"，提供 CSV 上传、
坐标系校验与 PostGIS 入库流程。

v4.0 升级：支持图片文件上传（JPG、PNG等）。
"""
from pathlib import Path
from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename
from PIL import Image
import os

from ..services.data_upload import handle_upload_file
from ..services.log_export_service import log_export_service

upload_bp = Blueprint("upload", __name__)

# 允许的图片扩展名
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif"}
ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/bmp", "image/gif"}


def is_allowed_image(filename: str) -> bool:
    """检查文件是否为允许的图片格式。"""
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


@upload_bp.post("")
@upload_bp.post("/trajectory")
def upload_trajectory():
    """上传共享电动自行车轨迹数据（CSV）。"""
    file = request.files.get("file")
    if file is None:
        return jsonify({"error": "缺少文件"}), 400

    filename = secure_filename(file.filename)
    upload_dir = Path(current_app.config["UPLOAD_DIR"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    filepath = upload_dir / filename
    file.save(filepath)

    try:
        summary = handle_upload_file(filepath, filename)
        # 记录操作日志
        log_export_service.log_operation(
            "upload",
            user=request.remote_addr,
            details={"filename": filename, "rows": summary.get("uploaded_rows", 0)}
        )
        return jsonify(summary)
    except Exception as exc:  # pylint: disable=broad-except
        current_app.logger.exception("上传失败：%s", exc)
        return jsonify({"error": str(exc)}), 400


@upload_bp.post("/image")
def upload_image():
    """上传图片文件（JPG、PNG等）。"""
    file = request.files.get("file")
    if file is None:
        return jsonify({"error": "缺少文件"}), 400

    filename = secure_filename(file.filename)
    if not is_allowed_image(filename):
        return jsonify({"error": f"不支持的图片格式，支持：{', '.join(ALLOWED_IMAGE_EXTENSIONS)}"}), 400

    # 创建图片上传目录
    image_dir = Path(current_app.config.get("UPLOAD_DIR", "uploads")) / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    # 保存原图
    filepath = image_dir / filename
    file.save(filepath)

    # 生成缩略图
    thumbnail_path = None
    try:
        with Image.open(filepath) as img:
            # 创建缩略图（最大尺寸200x200）
            img.thumbnail((200, 200), Image.Resampling.LANCZOS)
            thumbnail_name = f"thumb_{filename}"
            thumbnail_path = image_dir / thumbnail_name
            img.save(thumbnail_path, optimize=True, quality=85)
    except Exception as e:
        current_app.logger.warning(f"生成缩略图失败：{e}")

    # 记录操作日志
    log_export_service.log_operation(
        "upload_image",
        user=request.remote_addr,
        details={
            "filename": filename,
            "filepath": str(filepath),
            "thumbnail": str(thumbnail_path) if thumbnail_path else None
        }
    )

    return jsonify({
        "success": True,
        "filename": filename,
        "filepath": str(filepath),
        "thumbnail": str(thumbnail_path) if thumbnail_path else None,
        "size": filepath.stat().st_size
    })


@upload_bp.get("/images")
def list_images():
    """列出所有上传的图片。"""
    image_dir = Path(current_app.config.get("UPLOAD_DIR", "uploads")) / "images"
    if not image_dir.exists():
        return jsonify({"images": []})

    images = []
    for img_file in image_dir.glob("*"):
        if img_file.is_file() and not img_file.name.startswith("thumb_"):
            thumbnail = image_dir / f"thumb_{img_file.name}"
            images.append({
                "filename": img_file.name,
                "filepath": str(img_file),
                "thumbnail": str(thumbnail) if thumbnail.exists() else None,
                "size": img_file.stat().st_size,
                "modified": img_file.stat().st_mtime
            })

    return jsonify({
        "images": sorted(images, key=lambda x: x["modified"], reverse=True)
    })


@upload_bp.get("/images/view")
def view_image():
    """查看图片文件。"""
    from flask import send_file
    filepath = request.args.get("filepath")
    if not filepath:
        return jsonify({"error": "缺少文件路径参数"}), 400
    try:
        # 处理绝对路径和相对路径
        img_path = Path(filepath)
        # 如果是绝对路径但文件不存在，尝试从UPLOAD_DIR解析
        if not img_path.exists():
            # 提取文件名
            filename = img_path.name
            # 尝试从uploads目录查找
            upload_dir = Path(current_app.config.get("UPLOAD_DIR", "uploads"))
            # 检查是否是缩略图
            if filename.startswith("thumb_"):
                image_dir = upload_dir / "images"
                img_path = image_dir / filename
            else:
                image_dir = upload_dir / "images"
                img_path = image_dir / filename
        
        if not img_path.exists():
            return jsonify({"error": f"图片文件不存在: {img_path}"}), 404
        
        # 根据文件扩展名确定MIME类型
        ext = img_path.suffix.lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.bmp': 'image/bmp',
            '.gif': 'image/gif'
        }
        mimetype = mime_types.get(ext, 'image/jpeg')
        
        return send_file(str(img_path), mimetype=mimetype)
    except Exception as e:
        current_app.logger.exception("查看图片失败：%s", e)
        return jsonify({"error": str(e)}), 404


@upload_bp.delete("/images/<filename>")
def delete_image(filename):
    """删除上传的图片文件。"""
    try:
        image_dir = Path(current_app.config.get("UPLOAD_DIR", "uploads")) / "images"
        # 删除原图
        img_path = image_dir / filename
        if img_path.exists():
            img_path.unlink()
        
        # 删除缩略图（如果存在）
        thumb_path = image_dir / f"thumb_{filename}"
        if thumb_path.exists():
            thumb_path.unlink()
        
        # 记录操作日志
        log_export_service.log_operation(
            "delete_image",
            user=request.remote_addr,
            details={"filename": filename}
        )
        
        return jsonify({"success": True, "message": "图片已删除"})
    except Exception as e:
        current_app.logger.exception("删除图片失败：%s", e)
        return jsonify({"error": str(e)}), 500

