"""
Getis-Ord Gi* 与热点多边形生成。

参考论文 3.2 节的时空热点分析，输出 Gi* Z 值与风险等级。
若缺失 libpysal/esda 依赖，则退化为 z-score 排序方案。
"""
import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPoint
import numpy as np

try:
    from esda.getisord import G_Local
    from libpysal.weights import KNN

    HAS_PYSAL = True
except Exception:  # pragma: no cover
    # 打包环境中可能出现 DLL 加载失败，此时退回 z-score 近似实现。
    HAS_PYSAL = False
    KNN = G_Local = None


def _classify_risk(z_score: float) -> str:
    if z_score >= 2.58:
        return "high"
    if z_score >= 1.96:
        return "medium"
    if z_score >= 1.65:
        return "low"
    return "insignificant"


def _fallback_gi_scores(values: np.ndarray) -> np.ndarray:
    mean = values.mean()
    std = values.std(ddof=1) or 1.0
    return (values - mean) / std


def getis_ord_indicator(gdf: gpd.GeoDataFrame, column: str) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    values = gdf[column].to_numpy(dtype=float)
    if HAS_PYSAL and len(gdf) >= 5:
        w = KNN.from_dataframe(gdf, k=min(5, len(gdf) - 1))
        w.transform = "R"
        gi = G_Local(values, w)
        gdf["gi_z"] = gi.Zs
    else:
        gdf["gi_z"] = _fallback_gi_scores(values)
    gdf["risk_level"] = gdf["gi_z"].apply(_classify_risk)
    return gdf[gdf["risk_level"] != "insignificant"]


def create_hotspot_polygon(points_gdf: gpd.GeoDataFrame, buffer_distance: float = 0.001) -> gpd.GeoDataFrame:
    """
    基于热点点集生成缓冲多边形，供地图高亮。
    """
    if points_gdf.empty:
        return gpd.GeoDataFrame(columns=["risk_level", "geometry"], crs="EPSG:4326")
    multipoint = MultiPoint(points_gdf.geometry.tolist())
    polygon = multipoint.convex_hull.buffer(buffer_distance)
    return gpd.GeoDataFrame(
        [{"risk_level": points_gdf.iloc[0]["risk_level"], "geometry": polygon}],
        crs="EPSG:4326",
    )

