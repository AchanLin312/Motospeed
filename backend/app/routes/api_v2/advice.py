"""#10 POST /advice/generate      —— AI 治理建议（M6）
   #11 GET  /advice/<id>/basis   —— 建议依据溯源（M6）

LLM 配置（环境变量，AC30）：LLM_API_BASE / LLM_API_KEY / LLM_MODEL；
未配置时自动使用本地知识库规则模板兜底。
"""
from flask import request

from . import api_v2_bp
from .common import ok, err, resolve_analysis_version
from ...services.v2 import advice_service


@api_v2_bp.post("/advice/generate")
def generate_advice():
    """生成网格治理建议（六部分结构 + basis_ids，AC21-AC24）。

    请求体：{grid_id, analysis_version?, risk_layer?, force?}
    - 只在显式调用时生成（12.2：不在地图加载时批量调用）
    - 相同缓存键命中时直接返回（cached=true，不重复调用 LLM）
    - force=true 管理员清除缓存后重新生成
    """
    payload = request.get_json(silent=True) or {}
    grid_id = payload.get("grid_id")
    if not grid_id:
        return err("缺少 grid_id", 400)
    try:
        av = resolve_analysis_version(payload.get("analysis_version"))
    except FileNotFoundError as exc:
        return err(str(exc), 404)
    force = bool(payload.get("force"))
    try:
        record = advice_service.generate_advice(
            av, grid_id, risk_layer=payload.get("risk_layer"), force=force)
    except FileNotFoundError as exc:
        return err(str(exc), 404)
    except KeyError as exc:
        return err(str(exc), 404)
    return ok(record)


@api_v2_bp.get("/advice/<grid_id>/basis")
def get_advice_basis(grid_id: str):
    """返回建议的依据条款（BASIS-NPC57…BASIS-METHOD）与触发规则详情。"""
    av = request.args.get("analysis_version")
    try:
        av = resolve_analysis_version(av)
        data = advice_service.get_basis(av, grid_id)
    except FileNotFoundError as exc:
        return err(str(exc), 404)
    return ok(data)


@api_v2_bp.delete("/advice/<grid_id>")
def delete_advice(grid_id: str):
    """管理员清除单条建议缓存（12.2），下次调用将重新生成。"""
    av = request.args.get("analysis_version")
    try:
        av = resolve_analysis_version(av)
    except FileNotFoundError as exc:
        return err(str(exc), 404)
    removed = advice_service.clear_advice(av, grid_id)
    return ok({"grid_id": grid_id, "analysis_version": av, "removed": removed})
