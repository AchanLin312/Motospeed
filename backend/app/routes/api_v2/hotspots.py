"""#8 GET /hotspots —— 四图层热点 GeoJSON（comprehensive/overspeed/reverse/rapid）"""
from pathlib import Path

from flask import request

from . import api_v2_bp
from .common import ok, err, resolve_analysis_version
from ...services.v2 import analysis_dir
from ...services.v2.hotspot_service import LAYERS, run_hotspots


@api_v2_bp.get("/hotspots")
def get_hotspots():
    """返回指定图层热点 GeoJSON。

    :param layer: comprehensive（默认）/ overspeed / reverse / rapid
    :param analysis_version: 缺省取最近完成版本
    """
    layer = (request.args.get("layer") or "comprehensive").lower()
    if layer not in LAYERS:
        return err(f"未知图层 {layer}，可选: {sorted(LAYERS)}", 400)

    av = resolve_analysis_version(request.args.get("analysis_version"))
    if av is None:
        return err("尚无已完成的分析版本，请先执行 #5 POST /analysis", 404)

    gpath = analysis_dir(av) / "hotspots" / f"{layer}.geojson"
    if not gpath.exists():
        # 首次访问且分析已完成 → 补算（hotspot_service 自带缓存语义）
        if not (analysis_dir(av) / "summary.json").exists():
            return err(f"分析 {av} 未完成，热点不可用", 409)
        try:
            run_hotspots(av, force=False)
        except Exception as e:  # noqa: BLE001
            return err(f"热点计算失败：{e}", 400)
    if not gpath.exists():
        return err("热点文件生成失败", 500)
    import json
    return ok(json.loads(Path(gpath).read_text(encoding="utf-8")))
