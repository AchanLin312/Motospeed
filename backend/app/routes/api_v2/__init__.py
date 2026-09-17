"""API v2 路由包（手册 15 接口，/api/v2 前缀）。

管理模式接口（X-Admin-Token）：#3 路网上传、#6 状态、#14 admin/logs、#15 admin/config。
"""
from flask import Blueprint

api_v2_bp = Blueprint("api_v2", __name__)

from . import (  # noqa: E402,F401  注册各子路由
    batches,
    road_networks,
    analysis,
    hotspots,
    grids,
    advice,
    exports,
    admin,
)
