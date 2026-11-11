"""一线反馈接口（甲方第三次需求 五）：
   POST /feedback          提交现场核查反馈（multipart，可带 1-3 张照片）
   GET  /feedback          反馈台账（按网格/结论/日期筛选）
   GET  /feedback/export   台账导出 CSV（Excel 兼容）
   GET  /feedback/stats    网格核查状态 + 连续不成立复核提示 + 治理前后对比
"""
from flask import Response, request

from . import api_v2_bp
from .common import err, ok, resolve_analysis_version
from ...services.v2 import feedback_service


def _av() -> str | None:
    return resolve_analysis_version(request.args.get("analysis_version") or None)


@api_v2_bp.post("/feedback")
def create_feedback():
    grid_id = (request.form.get("grid_id") or "").strip()
    if not grid_id:
        return err("缺少 grid_id", 400)
    av = resolve_analysis_version(request.form.get("analysis_version") or None)
    if not av:
        return err("缺少 analysis_version（且无已完成的分析版本）", 400)
    photos = [(f.filename, f.read()) for f in request.files.getlist("photos")
              if f and f.filename]
    try:
        rec = feedback_service.add_feedback(av, grid_id, request.form, photos)
    except ValueError as e:
        return err(str(e), 422)
    return ok(rec, 201)


@api_v2_bp.get("/feedback")
def list_feedback():
    av = _av()
    if not av:
        return ok({"items": []})
    return ok({"items": feedback_service.list_feedback(
        analysis_version=av,
        grid_id=request.args.get("grid_id") or None,
        conclusion=request.args.get("conclusion") or None,
        date_from=request.args.get("date_from") or None,
        date_to=request.args.get("date_to") or None)})


@api_v2_bp.get("/feedback/export")
def export_feedback():
    av = _av()
    csv_text = feedback_service.export_feedback(
        analysis_version=av,
        grid_id=request.args.get("grid_id") or None,
        conclusion=request.args.get("conclusion") or None,
        date_from=request.args.get("date_from") or None,
        date_to=request.args.get("date_to") or None)
    return Response(csv_text, mimetype="text/csv", headers={
        "Content-Disposition": "attachment; filename=feedback.csv"})


@api_v2_bp.get("/feedback/stats")
def feedback_stats():
    av = _av()
    grid_id = request.args.get("grid_id") or ""
    if not av:
        return err("尚无已完成的分析版本", 400)
    if not grid_id:
        return err("缺少 grid_id", 400)
    return ok(feedback_service.feedback_stats(av, grid_id))
