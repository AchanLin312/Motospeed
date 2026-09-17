"""M4 热点分析服务：四图层 Gi* + Moran/LISA + 趋势占位。

验收对照：
- AC18 四套热点图层：综合 CRI / 超速率 / 逆行率 / 急变速率
- 质量门控：仅 quality_flag=valid 网格参与 Gi*（既不产出热点多边形，
  也不作为 KNN 邻居抬升他格邻域总和），低暴露统计噪声不再制造幽灵热点
- AC19 无显著热点时兜底 top8，selection_type=top_risk_fallback
- Z 分级阈值 2.58 / 1.96 / 1.65（α=0.01 / 0.05 / 0.10）
- AC25 Moran / LISA 保留（作用于综合 CRI）
- AC28 趋势分析：单日数据不足，明确返回"数据不足"

输入：analysis/<version>/grid_metrics.csv（M3 产出，含 cri / 三类事件率）
输出：analysis/<version>/hotspots/<layer>.geojson（4 个）
      analysis/<version>/moran_meta.json + lisa.geojson

Gi* 复用 V1 的 spatial_analysis.hotspot_analysis.getis_ord_indicator
（KNN k=5，缺失 pysal 时退化为 z-score），在 UTM 50N 米制坐标下计算后转回 WGS84。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from . import RULE_VERSION, TARGET_CRS, analysis_dir

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from spatial_analysis.hotspot_analysis import (  # noqa: E402
    _classify_risk,
    _fallback_gi_scores,
    getis_ord_indicator,
)
from spatial_analysis.moran_analysis import (  # noqa: E402
    global_moran_indicator,
    local_moran_indicator,
)

FALLBACK_TOP_N = 8        # AC19：无显著热点时兜底 top8
LISA_P_THRESHOLD = 0.05   # LISA 显著性

# 图层 -> 取值列（AC18）
LAYERS = {
    "comprehensive": {"column": "cri", "label": "综合风险 CRI"},
    "overspeed": {"column": "overspeed_rate", "label": "超速率"},
    "reverse": {"column": "reverse_rate", "label": "逆行率"},
    "rapid": {"column": "rapid_rate", "label": "急变速率"},
}


def _load_grids(analysis_version: str) -> gpd.GeoDataFrame:
    gpath = analysis_dir(analysis_version) / "grid_metrics.csv"
    if not gpath.exists():
        raise FileNotFoundError("缺少 grid_metrics.csv，请先执行网格聚合")
    df = pd.read_csv(gpath, encoding="utf-8-sig", dtype={"grid_id": str})
    gdf = gpd.GeoDataFrame(df, geometry=shapely.box(
        df["min_lon"], df["min_lat"], df["max_lon"], df["max_lat"]),
        crs="EPSG:4326")
    return gdf


def _features_from(gdf: gpd.GeoDataFrame, column: str,
                   selection_type: str) -> list[dict]:
    feats = []
    for _, r in gdf.iterrows():
        feats.append({
            "type": "Feature",
            "geometry": r.geometry.__geo_interface__,
            "properties": {
                "grid_id": r["grid_id"],
                "layer_value": None if pd.isna(r[column]) else round(float(r[column]), 2),
                "gi_z": None if "gi_z" not in gdf.columns or pd.isna(r.get("gi_z"))
                        else round(float(r["gi_z"]), 3),
                "risk_level": r.get("risk_level", ""),
                "vehicle_count": int(r["vehicle_count"]),
                "exposure_km": float(r["exposure_km"]),
                "overspeed_count": int(r["overspeed_count"]),
                "reverse_count": int(r["reverse_count"]),
                "rapid_count": int(r["rapid_count"]),
                "cri": None if pd.isna(r.get("cri")) else float(r["cri"]),
                "quality_flag": r.get("quality_flag", ""),
                "selection_type": selection_type,
            },
        })
    return feats


def _valid_quality(gdf: gpd.GeoDataFrame) -> pd.Series:
    """质量门控：仅 valid 网格可参与 Gi*/Moran 统计。

    低暴露网格不参与有两重意义：自身不产出热点多边形，且不作为 KNN
    邻居进入其他网格的邻域总和 —— 否则数据空洞两侧的孤立格会被拼成
    "邻域"，把 0 值格子推成热点（幽灵热点）。
    """
    if "quality_flag" in gdf.columns:
        return gdf["quality_flag"].eq("valid")
    return pd.Series(True, index=gdf.index)   # 兼容旧版数据


def _run_layer(gdf_all: gpd.GeoDataFrame, layer: str, column: str,
               rapid_available: bool) -> tuple[dict, dict]:
    """对单图层执行 Gi*，返回 (geojson, 图层 meta)。"""
    values = pd.to_numeric(gdf_all[column], errors="coerce")
    quality_ok = _valid_quality(gdf_all)
    if layer == "comprehensive":
        # AC17：CRI 不可用时综合图层为空
        avail = gdf_all["cri_available"].astype(bool)
        valid = gdf_all[values.notna() & avail & quality_ok].copy()
    elif layer == "rapid" and not rapid_available:
        valid = gdf_all.iloc[0:0].copy()
    else:
        valid = gdf_all[values.notna() & quality_ok].copy()

    base_meta = {
        "layer": layer,
        "column": column,
        "n_valid": int(len(valid)),
        "z_thresholds": [2.58, 1.96, 1.65],
    }
    if len(valid) < 5:
        return ({"type": "FeatureCollection", "features": []},
                {**base_meta, "n_significant": 0, "selection_type": "insufficient_data"})
    if float(values.loc[valid.index].max()) <= 0:
        return ({"type": "FeatureCollection", "features": []},
                {**base_meta, "n_significant": 0, "selection_type": "no_risk"})

    # Gi* 在 UTM 米制下计算（KNN 权重需要真实距离），显著结果转回 WGS84
    utm = valid.to_crs(TARGET_CRS)
    sig = getis_ord_indicator(utm, column)
    if len(sig):
        sig = sig.to_crs("EPSG:4326")
        feats = _features_from(sig, column, "hotspot_gi")
        meta = {**base_meta, "n_significant": int(len(sig)),
                "selection_type": "hotspot_gi"}
    else:
        # AC19：无显著热点 → 按原始值兜底 top8
        fb = valid.assign(_v=values.loc[valid.index]).sort_values(
            "_v", ascending=False).head(FALLBACK_TOP_N)
        zs = _fallback_gi_scores(values.loc[fb.index].to_numpy(float))
        fb = fb.assign(gi_z=zs,
                       risk_level=[_classify_risk(z) for z in zs])
        feats = _features_from(fb, column, "top_risk_fallback")
        meta = {**base_meta, "n_significant": int(len(fb)),
                "selection_type": "top_risk_fallback",
                "fallback_top_n": FALLBACK_TOP_N}
    geojson = {"type": "FeatureCollection", "layer": layer,
               "label": LAYERS[layer]["label"], "features": feats}
    return geojson, meta


def run_hotspots(analysis_version: str, force: bool = False) -> dict:
    """执行四图层 Gi* 热点分析并缓存 GeoJSON。"""
    adir = analysis_dir(analysis_version)
    hdir = adir / "hotspots"
    hdir.mkdir(parents=True, exist_ok=True)
    meta_path = hdir / "hotspots_meta.json"
    if meta_path.exists() and not force:
        return json.loads(meta_path.read_text(encoding="utf-8"))

    gdf = _load_grids(analysis_version)
    wmeta_path = adir / "weights.json"
    rapid_available = True
    if wmeta_path.exists():
        rapid_available = bool(
            json.loads(wmeta_path.read_text(encoding="utf-8")).get(
                "rapid_available", True))

    layers_meta = {}
    for layer, spec in LAYERS.items():
        geojson, meta = _run_layer(gdf, layer, spec["column"], rapid_available)
        (hdir / f"{layer}.geojson").write_text(
            json.dumps(geojson, ensure_ascii=False), encoding="utf-8")
        layers_meta[layer] = meta

    out = {
        "analysis_version": analysis_version,
        "rule_version": RULE_VERSION,
        "method": "Getis-Ord Gi* (KNN k=5, UTM 50N)",
        "layers": layers_meta,
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }
    meta_path.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return out


def run_moran(analysis_version: str) -> dict:
    """综合 CRI 的全局 Moran + LISA 聚类（AC25），含趋势状态（AC28）。"""
    adir = analysis_dir(analysis_version)
    gdf = _load_grids(analysis_version)
    values = pd.to_numeric(gdf["cri"], errors="coerce")
    avail = gdf["cri_available"].astype(bool)
    valid = gdf[values.notna() & avail & _valid_quality(gdf)].copy()

    trend = {
        "status": "insufficient_data",
        "message": "单日数据不足以进行时间趋势分析（Mann-Kendall 需多日序列）",
    }
    if len(valid) < 5:
        out = {
            "analysis_version": analysis_version,
            "rule_version": RULE_VERSION,
            "n_valid": int(len(valid)),
            "global_moran": None,
            "trend": trend,
            "built_at": datetime.now().isoformat(timespec="seconds"),
        }
        (adir / "moran_meta.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return out

    utm = valid.to_crs(TARGET_CRS)
    glob = global_moran_indicator(utm, "cri")
    lisa = local_moran_indicator(utm, "cri")
    if "lisa_p" in lisa.columns and lisa["lisa_p"].notna().any():
        sig = lisa[lisa["lisa_p"] < LISA_P_THRESHOLD]
    else:                       # 退化实现无 p 值，保留全部正自相关簇
        sig = lisa[lisa["lisa_z"] > 0]
    sig = sig.to_crs("EPSG:4326")
    feats = [{
        "type": "Feature",
        "geometry": r.geometry.__geo_interface__,
        "properties": {
            "grid_id": r["grid_id"],
            "cri": float(r["cri"]),
            "lisa_cluster": int(r["lisa_cluster"]),
            "cluster_label": r["cluster_label"],
        },
    } for _, r in sig.iterrows()]
    (adir / "lisa.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats},
                   ensure_ascii=False), encoding="utf-8")

    out = {
        "analysis_version": analysis_version,
        "rule_version": RULE_VERSION,
        "n_valid": int(len(valid)),
        "global_moran": {k: (round(v, 6) if isinstance(v, (int, float)) else v)
                         for k, v in glob.items()},
        "lisa_clusters": {
            "n_significant": int(len(sig)),
            "by_label": sig["cluster_label"].value_counts().to_dict(),
        },
        "trend": trend,
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }
    (adir / "moran_meta.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


# ---------------------------------------------------------------- 自测

def _selftest() -> None:
    """构造 9 格带空间聚集的网格，验证四图层/兜底/Moran 主流程。"""
    import tempfile
    from . import ANALYSIS_DIR

    rows = []
    for c in range(3):
        for r in range(3):
            x0, y0 = 454000 + c * 250, 4397250 + r * 250
            cri = 90.0 if (c == 2 and r == 2) else 10.0 + c * 5
            rows.append({
                "grid_id": f"G{c:04d}_{r:04d}", "col": c, "row": r,
                "min_lon": 116.5 + c * 0.0025, "min_lat": 39.75 + r * 0.00225,
                "max_lon": 116.5 + (c + 1) * 0.0025,
                "max_lat": 39.75 + (r + 1) * 0.00225,
                "vehicle_count": 5, "exposure_km": 10.0,
                "overspeed_count": c + r, "reverse_count": 0,
                "rapid_count": 1,
                "overspeed_rate": (c + r) / 10.0 * 100,
                "reverse_rate": 0.0, "rapid_rate": 0.1 * 100,
                "total_events": c + r + 1,
                "overspeed_index": c * 10.0, "reverse_index": 0.0,
                "rapid_index": 1.0, "cri": cri, "cri_available": True,
                "quality_flag": "valid",
            })
    df = pd.DataFrame(rows)
    with tempfile.TemporaryDirectory() as td:
        av = "AV-SELFTEST-HOTSPOT"
        adir = ANALYSIS_DIR / av
        adir.mkdir(parents=True, exist_ok=True)
        df.to_csv(adir / "grid_metrics.csv", index=False, encoding="utf-8-sig")
        try:
            hm = run_hotspots(av, force=True)
            for layer in LAYERS:
                m = hm["layers"][layer]
                gj = json.loads((adir / "hotspots" / f"{layer}.geojson")
                                .read_text(encoding="utf-8"))
                if layer == "reverse":      # 合成数据全 0 → 无风险
                    assert m["selection_type"] == "no_risk", m
                else:
                    assert m["selection_type"] in (
                        "hotspot_gi", "top_risk_fallback"), m
                assert len(gj["features"]) == m["n_significant"]
            mm = run_moran(av)
            assert mm["global_moran"] is not None
            assert mm["trend"]["status"] == "insufficient_data"
            # CRI 不可用 → 综合图层 insufficient_data
            df2 = df.copy()
            df2["cri"] = np.nan
            df2["cri_available"] = False
            df2.to_csv(adir / "grid_metrics.csv", index=False,
                       encoding="utf-8-sig")
            hm2 = run_hotspots(av, force=True)
            assert hm2["layers"]["comprehensive"]["selection_type"] == \
                "insufficient_data"
            # 幽灵热点回归：低暴露网格（率值分母爆炸）不得进入任何热点图层
            ghost = df.iloc[0].copy()
            ghost["grid_id"] = "GHOST_LOWE"
            ghost["quality_flag"] = "low_exposure"
            ghost["exposure_km"] = 0.005        # 5m 暴露 3 起事件
            ghost["overspeed_count"] = 3
            ghost["overspeed_rate"] = 62516.0   # 分母爆炸的统计噪声值
            df3 = pd.concat([df, ghost.to_frame().T], ignore_index=True)
            df3.to_csv(adir / "grid_metrics.csv", index=False,
                       encoding="utf-8-sig")
            hm3 = run_hotspots(av, force=True)
            for layer in LAYERS:
                gj3 = json.loads((adir / "hotspots" / f"{layer}.geojson")
                                 .read_text(encoding="utf-8"))
                ids = [f["properties"]["grid_id"]
                       for f in gj3["features"]]
                assert "GHOST_LOWE" not in ids, \
                    f"{layer} 图层出现低暴露幽灵热点"
            assert hm3["layers"]["overspeed"]["n_valid"] == 9, \
                hm3["layers"]["overspeed"]
            print("hotspot_service selftest: ghost-hotspot regression PASS")
            print("hotspot_service selftest: ALL PASS")
            print(json.dumps({k: v["selection_type"]
                              for k, v in hm["layers"].items()},
                             ensure_ascii=False))
        finally:
            import shutil
            shutil.rmtree(adir, ignore_errors=True)


if __name__ == "__main__":
    _selftest()
