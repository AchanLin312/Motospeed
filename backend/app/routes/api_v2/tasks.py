"""分析后台任务管理：线程 + 内存任务表（AC：长任务不阻塞请求）。

任务仅存内存（进程内），服务重启后由 status 接口从磁盘产物推断状态。
"""
import threading
import traceback
from datetime import datetime

from ...services.v2.pipeline_service import run_pipeline

_TASKS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def start_analysis(analysis_version: str, batch_id: str, net_id: str | None,
                   cell_size: float | None) -> dict:
    """创建任务并启动后台线程，立即返回任务快照。"""
    task = {
        "analysis_version": analysis_version,
        "batch_id": batch_id,
        "net_id": net_id,
        "status": "queued",
        "progress": 0.0,
        "stage": "",
        "message": "",
        "error": None,
        "started_at": _now(),
        "finished_at": None,
    }
    with _LOCK:
        _TASKS[analysis_version] = task
    th = threading.Thread(target=_run, args=(analysis_version, batch_id,
                                             net_id, cell_size),
                          daemon=True, name=f"v2-analysis-{analysis_version}")
    th.start()
    return dict(task)


def _run(analysis_version: str, batch_id: str, net_id: str | None,
         cell_size: float | None) -> None:
    def progress(stage: str, pct: float, message: str = ""):
        with _LOCK:
            t = _TASKS.get(analysis_version)
            if t:
                t.update({"stage": stage, "progress": round(pct, 1),
                          "message": message, "status": "running"})

    try:
        with _LOCK:
            t = _TASKS.get(analysis_version)
            if t:
                t["status"] = "running"
        run_pipeline(analysis_version, batch_id, net_id=net_id,
                     cell_size=cell_size, progress=progress)
        with _LOCK:
            t = _TASKS.get(analysis_version)
            if t:
                t.update({"status": "completed", "progress": 100.0,
                          "stage": "done", "message": "分析完成",
                          "finished_at": _now()})
    except Exception as e:  # noqa: BLE001 —— 后台线程兜底，错误上报到任务表
        traceback.print_exc()
        with _LOCK:
            t = _TASKS.get(analysis_version)
            if t:
                t.update({"status": "failed", "error": str(e),
                          "message": "分析失败", "finished_at": _now()})


def get_task(analysis_version: str) -> dict | None:
    with _LOCK:
        t = _TASKS.get(analysis_version)
        return dict(t) if t else None


def list_tasks(limit: int = 50) -> list[dict]:
    with _LOCK:
        tasks = sorted(_TASKS.values(),
                       key=lambda t: t.get("started_at") or "", reverse=True)
        return [dict(t) for t in tasks[:limit]]
