"""#1 POST /batches/trajectory —— CSV 上传（DV01-DV08 校验）
   #2 GET  /batches          —— 批次列表
"""
import tempfile
from pathlib import Path

from flask import request

from . import api_v2_bp
from .common import ok, err
from ...services.v2.data_import import (
    import_trajectory_csv, list_batches, get_batch_meta, ImportValidationError,
)

from werkzeug.utils import secure_filename


@api_v2_bp.post("/batches/trajectory")
def upload_trajectory():
    """上传轨迹 CSV，标准化入库（不可变批次）。"""
    f = request.files.get("file")
    if f is None or not f.filename:
        return err("缺少文件字段 file（multipart/form-data）", 400)
    source_name = request.form.get("source_name") or secure_filename(f.filename)

    suffix = Path(f.filename).suffix or ".csv"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / f"upload{suffix}"
        f.save(str(p))
        try:
            meta = import_trajectory_csv(p, source_name=source_name)
        except ImportValidationError as e:
            return err(f"数据校验失败（DV 规则）：{e}", 422)
        except Exception as e:  # noqa: BLE001
            return err(f"导入失败：{e}", 400)
    return ok(meta, 201)


@api_v2_bp.get("/batches")
def get_batches():
    """批次列表（含最新批次标注）。"""
    batches = list_batches()
    latest = (max(batches, key=lambda b: b.get("created_at", ""))["batch_id"]
              if batches else None)
    return ok({"batches": batches, "latest": latest,
               "count": len(batches)})


@api_v2_bp.get("/batches/<batch_id>")
def get_batch(batch_id: str):
    meta = get_batch_meta(batch_id)
    if meta is None:
        return err(f"批次不存在: {batch_id}", 404)
    return ok(meta)
