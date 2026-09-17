"""#12 GET /exports/report    —— 分析报告导出（json / csv）
   #13 GET /exports/hotspots —— 热点图层 CSV 导出
"""
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import request, send_file

from . import api_v2_bp
from .common import err, resolve_analysis_version
from ...services.v2 import analysis_dir
from ...services.v2.hotspot_service import LAYERS


def _export_path(av: str, filename: str) -> Path:
    edir = analysis_dir(av) / "exports"
    edir.mkdir(parents=True, exist_ok=True)
    return edir / filename


@api_v2_bp.get("/exports/report")
def export_report():
    """导出分析报告：format=json（summary.json）或 csv（网格指标+CRI）。"""
    av = resolve_analysis_version(request.args.get("analysis_version"))
    if av is None:
        return err("尚无已完成的分析版本", 404)
    fmt = (request.args.get("format") or "json").lower()

    if fmt == "json":
        spath = analysis_dir(av) / "summary.json"
        if not spath.exists():
            return err(f"分析 {av} 未完成", 409)
        out = _export_path(av, f"report_{av}.json")
        out.write_text(spath.read_text(encoding="utf-8"), encoding="utf-8")
        return send_file(out, as_attachment=True, download_name=out.name,
                         mimetype="application/json")

    gpath = analysis_dir(av) / "grid_metrics.csv"
    if not gpath.exists():
        return err(f"分析 {av} 缺少网格指标", 409)
    df = pd.read_csv(gpath, encoding="utf-8-sig", dtype={"grid_id": str})
    out = _export_path(av, f"report_{av}.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    return send_file(out, as_attachment=True, download_name=out.name,
                     mimetype="text/csv")


@api_v2_bp.get("/exports/hotspots")
def export_hotspots():
    """导出热点图层 CSV（properties + 经纬度）。"""
    layer = (request.args.get("layer") or "comprehensive").lower()
    if layer not in LAYERS:
        return err(f"未知图层 {layer}，可选: {sorted(LAYERS)}", 400)
    av = resolve_analysis_version(request.args.get("analysis_version"))
    if av is None:
        return err("尚无已完成的分析版本", 404)

    gpath = analysis_dir(av) / "hotspots" / f"{layer}.geojson"
    if not gpath.exists():
        return err(f"分析 {av} 无 {layer} 热点结果", 404)

    gj = json.loads(gpath.read_text(encoding="utf-8"))
    rows = []
    for feat in gj.get("features", []):
        rec = dict(feat.get("properties") or {})
        geom = feat.get("geometry") or {}
        if geom.get("type") == "Point":
            rec["lon"], rec["lat"] = geom["coordinates"][:2]
        rows.append(rec)
    out = _export_path(av, f"hotspots_{layer}_{av}.csv")
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8-sig")
    return send_file(out, as_attachment=True, download_name=out.name,
                     mimetype="text/csv")
