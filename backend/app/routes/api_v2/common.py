"""api_v2 公共工具：统一响应、管理模式校验、分析版本解析。"""
import functools
import os

from flask import jsonify, request, current_app


def ok(data=None, status: int = 200):
    return jsonify(data), status


def err(message: str, status: int = 400, **extra):
    body = {"error": message}
    body.update(extra)
    return jsonify(body), status


def admin_required(fn):
    """管理模式校验（AC26）：请求头 X-Admin-Token 须等于环境变量 V2_ADMIN_TOKEN。

    未配置 V2_ADMIN_TOKEN 时视为开发模式，放行（密钥治理见 M8）。
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        token = os.environ.get("V2_ADMIN_TOKEN", "")
        if token:
            provided = request.headers.get("X-Admin-Token", "")
            if provided != token:
                return err("管理模式校验失败：X-Admin-Token 无效", 403)
        return fn(*args, **kwargs)
    return wrapper


def resolve_analysis_version(provided: str | None) -> str | None:
    """显式提供则用之，否则取最近完成的版本。"""
    if provided:
        return provided
    from ...services.v2.pipeline_service import latest_analysis_version
    return latest_analysis_version()
