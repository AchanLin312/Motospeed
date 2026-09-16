"""
Moran 分析工具。

依据论文 3.1 节的空间自相关分析流程实现全局与局部 Moran。
若缺失 libpysal/esda 依赖，则退化为纯 numpy 版本，保证演示环境可运行。
"""
from typing import Dict

import numpy as np
import geopandas as gpd

try:  # 可选依赖
    from libpysal.weights import KNN
    from esda.moran import Moran, Moran_Local

    HAS_PYSAL = True
except Exception:  # pragma: no cover
    # 打包环境中可能出现 DLL 加载失败，此时退回纯 Python 实现。
    KNN = Moran = Moran_Local = None
    HAS_PYSAL = False


def _fallback_weight_matrix(gdf: gpd.GeoDataFrame, radius: float = 0.01) -> np.ndarray:
    coords = np.column_stack(
        (
            gdf.geometry.centroid.x.to_numpy(),
            gdf.geometry.centroid.y.to_numpy(),
        )
    )
    diff = coords[:, None, :] - coords[None, :, :]
    dist = np.hypot(diff[..., 0], diff[..., 1])
    weights = (dist > 0) & (dist <= radius)
    weights = weights.astype(float)
    return weights


def _ensure_weights(gdf: gpd.GeoDataFrame, k: int = 5):
    if HAS_PYSAL:
        w = KNN.from_dataframe(gdf, k=k)
        w.transform = "R"
        return w
    return _fallback_weight_matrix(gdf)


def _moran_expected(n: int) -> float:
    return -1.0 / (n - 1) if n > 1 else 0.0


def global_moran_indicator(gdf: gpd.GeoDataFrame, column: str) -> Dict:
    y = gdf[column].to_numpy(dtype=float)
    n = len(y)
    if n < 2:
        return {
            "indicator": column,
            "moran_i": 0.0,
            "expected_i": 0.0,
            "z_score": 0.0,
            "p_value": 1.0,
        }

    if HAS_PYSAL:
        w = _ensure_weights(gdf)
        moran = Moran(y, w)
        return {
            "indicator": column,
            "moran_i": float(moran.I),
            "expected_i": float(moran.EI),
            "z_score": float(moran.z_norm),
            "p_value": float(moran.p_norm),
        }

    weights = _ensure_weights(gdf)
    x = y - y.mean()
    s0 = weights.sum()
    if s0 == 0 or np.allclose(x, 0):
        moran_i = 0.0
    else:
        numerator = (weights * (x[:, None] * x[None, :])).sum()
        denominator = (x**2).sum()
        moran_i = (n / s0) * (numerator / denominator)
    expected_i = _moran_expected(n)
    return {
        "indicator": column,
        "moran_i": float(moran_i),
        "expected_i": float(expected_i),
        "z_score": 0.0,
        "p_value": 1.0,
    }


def local_moran_indicator(gdf: gpd.GeoDataFrame, column: str) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    y = gdf[column].to_numpy(dtype=float)
    n = len(y)
    if n == 0:
        return gdf

    if HAS_PYSAL:
        w = _ensure_weights(gdf)
        lisa = Moran_Local(y, w)
        gdf["lisa_z"] = lisa.z_sim
        gdf["lisa_p"] = lisa.p_sim
        gdf["lisa_cluster"] = lisa.q
    else:
        weights = _ensure_weights(gdf)
        x = y - y.mean()
        m2 = (x**2).sum() / n if n else 1
        lisa_scores = (weights * x).sum(axis=1) * x / m2
        gdf["lisa_z"] = lisa_scores
        gdf["lisa_p"] = 1.0
        gdf["lisa_cluster"] = np.where(
            (x > 0) & (lisa_scores > 0),
            1,
            np.where((x < 0) & (lisa_scores > 0), 2, np.where((x > 0), 3, 4)),
        )
    gdf["cluster_label"] = gdf["lisa_cluster"].map(
        {
            1: "高-高",
            2: "低-低",
            3: "高-低",
            4: "低-高",
        }
    )
    return gdf

