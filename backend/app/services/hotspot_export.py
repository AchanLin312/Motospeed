"""
热点数据导出与查询服务（2.0）。

改为读取 runtime_pipeline 写入的 GeoJSON，不再依赖数据库。
"""
from typing import Optional

from .runtime_pipeline import load_hotspots_geojson, export_hotspots_csv as runtime_export_csv


def query_hotspots_geojson(risk_level: Optional[str], start_time: Optional[str], end_time: Optional[str]):
    return load_hotspots_geojson(risk_level, start_time, end_time)


def export_hotspots_csv(risk_level: Optional[str], start_time: Optional[str], end_time: Optional[str]):
    """导出热点 CSV 文件路径。"""
    return runtime_export_csv(risk_level, start_time, end_time)


