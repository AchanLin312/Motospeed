"""#14 GET /admin/logs 【管理】—— 分析任务审计日志
   #15 PUT /admin/config 【管理】—— 平台参数配置下发
"""
import json
import os

from flask import request, current_app

from . import api_v2_bp
from .common import ok, err, admin_required
from . import tasks as taskmgr
from ...services.v2 import V2_DIR

_CONFIG_PATH = V2_DIR / "admin_config.json"

# 可下发参数白名单（越界值拒绝，防止破坏算法语义）
_ALLOWED = {
    "overspeed_threshold_kmh": (5.0, 80.0),
    "grid_size_m": (50.0, 500.0),
    "admin_mode": None,          # bool
}
_DEFAULTS = {
    "overspeed_threshold_kmh": 20.0,
    "grid_size_m": 50.0,
    "admin_mode": False,
}


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            return {**_DEFAULTS, **cfg}
        except Exception:  # noqa: BLE001 —— 配置损坏时回退默认
            pass
    return dict(_DEFAULTS)


@api_v2_bp.get("/admin/logs")
@admin_required
def get_admin_logs():
    """分析任务审计：内存任务表（含进度与错误）+ 服务信息。"""
    return ok({
        "tasks": taskmgr.list_tasks(limit=100),
        "admin_mode_enabled": bool(os.environ.get("V2_ADMIN_TOKEN", "")),
        "generated_at": datetime_now(),
    })


def datetime_now() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


@api_v2_bp.get("/admin/config")
@admin_required
def get_admin_config():
    cfg = _load_config()
    # LLM 接入状态（密钥脱敏，仅回 base/model/是否配置，AC30）
    from ...services.v2 import llm_provider
    cfg["llm"] = llm_provider.llm_config()
    return ok(cfg)


@api_v2_bp.put("/admin/config")
@admin_required
def put_admin_config():
    """下发平台参数（白名单 + 区间校验），落盘 admin_config.json。"""
    payload = request.get_json(silent=True) or {}
    if not payload:
        return err("请求体为空", 400)

    cfg = _load_config()
    rejected = {}
    for k, v in payload.items():
        if k not in _ALLOWED:
            rejected[k] = "不在白名单"
            continue
        bounds = _ALLOWED[k]
        if bounds is not None:
            try:
                fv = float(v)
            except (TypeError, ValueError):
                rejected[k] = "须为数字"
                continue
            lo, hi = bounds
            if not (lo <= fv <= hi):
                rejected[k] = f"超出区间 [{lo}, {hi}]"
                continue
            cfg[k] = fv
        else:
            cfg[k] = bool(v)

    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    current_app.logger.info("admin config updated: %s (rejected=%s)",
                            cfg, rejected)
    return ok({"config": cfg, "rejected": rejected})
