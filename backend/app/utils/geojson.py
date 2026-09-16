"""
GeoJSON 辅助函数。

用于将 GeoDataFrame 或 Shapely 几何体转为前端 Leaflet 可直接
消费的 GeoJSON，确保坐标系统一为 WGS-84。
"""
import json
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

import pandas as pd
import numpy as np

import geopandas as gpd


def gdf_to_feature_collection(gdf: gpd.GeoDataFrame) -> Dict[str, Any]:
    """
    将 GeoDataFrame 转为 FeatureCollection。

    :param gdf: 输入数据，要求 crs=EPSG:4326
    """
    if gdf.crs is None or str(gdf.crs).lower() not in {"epsg:4326", "epsg: 4326"}:
        gdf = gdf.to_crs(epsg=4326)

    def _serialize(value):
        if isinstance(value, (datetime, pd.Timestamp)):
            return value.isoformat()
        if isinstance(value, (np.integer, )):
            return int(value)
        if isinstance(value, (np.floating, )):
            return float(value)
        if isinstance(value, (pd.Series, pd.DataFrame)):
            return value.to_dict()
        return value

    features = []
    for _, row in gdf.iterrows():
        props = {key: _serialize(val) for key, val in row.drop(labels="geometry").to_dict().items()}
        features.append(
            {
                "type": "Feature",
                "geometry": row.geometry.__geo_interface__,
                "properties": props,
            }
        )

    return {"type": "FeatureCollection", "features": features}


def load_geojson_file(file_path: Path) -> Dict[str, Any]:
    """从文件加载 GeoJSON。"""
    with open(file_path, "r", encoding="utf-8") as fp:
        return json.load(fp)

