"""#5 POST /analysis            —— 创建分析（后台线程，立即返回 202）
   #6 GET  /analysis/<id>/status 【管理】—— 进度/错误上报
   #7 GET  /analysis/<id>/summary      —— 汇总结果
"""
from flask import request

from . import api_v2_bp
from .common import ok, err
from . import tasks as taskmgr
from ...services.v2.data_import import get_batch_meta
from ...services.v2.pipeline_service import (
    new_analysis_version, get_summary, infer_task_state,
)
from ...services.v2.road_network_service import latest_network_id
from ...services.v2 import analysis_dir


@api_v2_bp.post("/analysis")
def create_analysis():
    """创建分析任务：{batch_id, net_id?, cell_size?, force?}。

    后台线程执行 IVMM → 行为 → 网格 → 评分 → 热点全链，轮询 #6 获取进度。
    """
    payload = request.get_json(silent=True) or {}
    batch_id = payload.get("batch_id")
    if not batch_id:
        return err("缺少 batch_id", 400)
    if get_batch_meta(batch_id) is None:
        return err(f"批次不存在: {batch_id}", 404)

    net_id = payload.get("net_id") or latest_network_id()
    if net_id is None:
        return err("无可用路网版本，请先上传路网（#3）", 409)

    cell_size = payload.get("cell_size")
    if cell_size is not None:
        try:
            cell_size = float(cell_size)
        except (TypeError, ValueError):
            return err("cell_size 须为数字（米）", 400)

    av = new_analysis_version(batch_id)
    task = taskmgr.start_analysis(av, batch_id, net_id, cell_size)
    return ok({
        "analysis_version": av,
        "batch_id": batch_id,
        "net_id": net_id,
        "status": task["status"],
        "status_url": f"/api/v2/analysis/{av}/status",
        "summary_url": f"/api/v2/analysis/{av}/summary",
    }, 202)


def _status_body(av: str) -> dict | None:
    """内存任务优先，服务重启后从磁盘产物推断。"""
    t = taskmgr.get_task(av)
    if t:
        return {
            "analysis_version": av,
            "status": t["status"],
            "progress": t["progress"],
            "stage": t["stage"],
            "message": t["message"],
            "error": t["error"],
            "started_at": t["started_at"],
            "finished_at": t["finished_at"],
        }
    if not analysis_dir(av).exists():
        return None
    state = infer_task_state(av)
    return {"analysis_version": av, "error": None, "message": "",
            "started_at": None, "finished_at": None, **state}


@api_v2_bp.get("/analysis/<analysis_version>/status")
def get_analysis_status(analysis_version: str):
    body = _status_body(analysis_version)
    if body is None:
        return err(f"分析版本不存在: {analysis_version}", 404)
    return ok(body)


@api_v2_bp.get("/analysis")
def list_analyses():
    """分析任务历史（内存任务表 + 磁盘已完成版本）。"""
    from ...services.v2 import ANALYSIS_DIR
    on_disk = []
    if ANALYSIS_DIR.exists():
        for d in sorted(ANALYSIS_DIR.iterdir(), reverse=True):
            if d.is_dir() and (d / "summary.json").exists():
                on_disk.append({"analysis_version": d.name,
                                "status": "completed"})
    return ok({"tasks": taskmgr.list_tasks(), "completed": on_disk})


@api_v2_bp.get("/analysis/<analysis_version>/summary")
def get_analysis_summary(analysis_version: str):
    summary = get_summary(analysis_version)
    if summary is None:
        if not analysis_dir(analysis_version).exists():
            return err(f"分析版本不存在: {analysis_version}", 404)
        return err("分析尚未完成，请先轮询 status 接口", 409)
    return ok(summary)
