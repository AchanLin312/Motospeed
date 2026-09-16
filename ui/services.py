"""
UI 层业务封装。

面向 PyQt6 主界面，基于论文提出的指标体系完成
数据上传、风险识别、预警导出、建议生成与反馈存储。
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from spatial_analysis.moran_analysis import (
    global_moran_indicator,
    local_moran_indicator,
)
from spatial_analysis.hotspot_analysis import getis_ord_indicator
from backend.app.services.recommendation import generate_recommendations

DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR = PROJECT_ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


@dataclass
class DataBatch:
    batch_id: str
    file_name: str
    data_count: int
    time_range: str
    coord_range: str
    status: str
    dataframe: pd.DataFrame
    geodataframe: gpd.GeoDataFrame


data_batches: Dict[str, DataBatch] = {}
hotspot_cache: Dict[str, gpd.GeoDataFrame] = {}
analysis_summary: Dict[str, Dict] = {}
feedback_records: List[Dict] = []


def _parse_csv(file_path: str) -> pd.DataFrame:
    df = pd.read_csv(file_path)
    required_cols = {"Time", "X_position", "Y_position", "Speed"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"缺少字段: {', '.join(missing)}")
    df["Time"] = pd.to_datetime(df["Time"])
    df["Speed"] = pd.to_numeric(df["Speed"], errors="coerce").fillna(0)
    df["overspeed"] = df["Speed"] > 0.8  # demo 阈值
    return df


def process_csv_upload(file_path: str) -> Dict:
    df = _parse_csv(file_path)
    geom = gpd.points_from_xy(df["X_position"], df["Y_position"], crs="EPSG:4326")
    gdf = gpd.GeoDataFrame(df.copy(), geometry=geom)
    batch_id = f"batch-{int(time.time())}"
    time_range = f"{df['Time'].min()} ~ {df['Time'].max()}"
    coord_range = (
        f"Lon[{df['X_position'].min():.5f}, {df['X_position'].max():.5f}] / "
        f"Lat[{df['Y_position'].min():.5f}, {df['Y_position'].max():.5f}]"
    )
    data_batches[batch_id] = DataBatch(
        batch_id=batch_id,
        file_name=Path(file_path).name,
        data_count=len(df),
        time_range=time_range,
        coord_range=coord_range,
        status="已解析",
        dataframe=df,
        geodataframe=gdf,
    )
    return {
        "batch_id": batch_id,
        "file_name": Path(file_path).name,
        "data_count": len(df),
        "time_range": time_range,
        "coord_range": coord_range,
        "status": "已解析",
    }


def _grid_aggregate(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    if "ID" not in gdf.columns:
        gdf["ID"] = range(1, len(gdf) + 1)
    gdf["grid_lon"] = gdf["X_position"].round(4)
    gdf["grid_lat"] = gdf["Y_position"].round(4)
    grouped = (
        gdf.groupby(["grid_lon", "grid_lat"])
        .agg(
            overspeed_count=("overspeed", "sum"),
            trajectory_count=("ID", "count"),
            avg_speed=("Speed", "mean"),
        )
        .reset_index()
    )
    grouped["male_young_ratio"] = 0.4
    grouped["geometry"] = [
        Point(lon, lat) for lon, lat in zip(grouped["grid_lon"], grouped["grid_lat"])
    ]
    result = gpd.GeoDataFrame(grouped, geometry="geometry", crs="EPSG:4326")
    return result


def run_spatial_analysis(batch_id: str, algorithms: List[str]) -> Dict:
    if batch_id not in data_batches:
        raise ValueError("批次不存在，请重新上传数据")
    gdf = data_batches[batch_id].geodataframe
    indicator_gdf = _grid_aggregate(gdf)

    result = {}
    if "全局Moran's I" in algorithms:
        result["全局Moran's I"] = global_moran_indicator(indicator_gdf, "overspeed_count")
    if "局部Moran's I" in algorithms:
        lisa = local_moran_indicator(indicator_gdf, "overspeed_count")
        result["局部Moran's I"] = lisa[["grid_lon", "grid_lat", "cluster_label"]].to_dict("records")
    if "Gi*热点" in algorithms:
        hotspots = getis_ord_indicator(indicator_gdf, "overspeed_count")
    else:
        hotspots = indicator_gdf[indicator_gdf["overspeed_count"] > 0].copy()
        hotspots["gi_z"] = hotspots["overspeed_count"].apply(lambda v: 2.5 if v > 1 else 1.8)
    hotspots = hotspots.copy()
    hotspots["risk_level"] = hotspots["gi_z"].apply(
        lambda z: "high" if z >= 2.58 else "medium" if z >= 1.96 else "low"
        if z >= 1.65
        else "low"
        if z >= 0
        else "low"
    )
    hotspots["area_id"] = [f"{batch_id}-HS-{i+1:03d}" for i in range(len(hotspots))]
    hotspots["time_slice"] = data_batches[batch_id].time_range
    hotspot_cache[batch_id] = hotspots
    analysis_summary[batch_id] = result
    return {
        "summary": result,
        "hotspots": hotspots.drop(columns="geometry").to_dict("records"),
    }


def generate_hotspot_geojson(batch_id: str) -> Dict:
    if batch_id not in hotspot_cache:
        raise ValueError("当前批次暂无热点，请先完成风险分析")
    gdf = hotspot_cache[batch_id]
    return json.loads(gdf.to_json())


def get_lisa_cluster_geojson() -> Dict:
    """获取 LISA 聚类 GeoJSON（3.5 新增）。"""
    import requests
    try:
        response = requests.get("http://127.0.0.1:5000/api/visualizations/lisa-cluster/geojson", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    # 如果 API 不可用，尝试从文件读取
    lisa_file = PROJECT_ROOT / "outputs" / "runtime" / "lisa_cluster.geojson"
    if lisa_file.exists():
        with open(lisa_file, "r", encoding="utf-8") as f:
            return json.load(f)
    raise ValueError("LISA 聚类数据不可用，请先执行风险分析")


def get_evolution_pattern_geojson() -> Dict:
    """获取演化模式 GeoJSON（3.5 新增）。"""
    import requests
    try:
        response = requests.get("http://127.0.0.1:5000/api/visualizations/evolution-pattern/geojson", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    # 如果 API 不可用，尝试从文件读取并添加演化模式
    hotspot_file = PROJECT_ROOT / "outputs" / "runtime" / "hotspot_areas.geojson"
    if hotspot_file.exists():
        with open(hotspot_file, "r", encoding="utf-8") as f:
            geojson = json.load(f)
        # 添加演化模式属性（简化实现）
        summary_file = PROJECT_ROOT / "outputs" / "runtime" / "analysis_summary.json"
        if summary_file.exists():
            with open(summary_file, "r", encoding="utf-8") as f:
                summary = json.load(f)
            trend = summary.get("trend", {})
            zmk = trend.get("zmk", 0)
            pattern_colors = {
                "振荡热点": "#9c27b0",
                "新增热点": "#ff9800",
                "加强的热点": "#d32f2f",
                "逐渐减少的热点": "#f06292",
                "持续的热点": "#1976d2",
            }
            for feature in geojson.get("features", []):
                props = feature.get("properties", {})
                risk_level = props.get("risk_level", "low")
                gi_score = props.get("gi_score", props.get("gi_z", 0))
                if risk_level == "high" and gi_score >= 2.58:
                    if abs(zmk) > 2.58:
                        pattern = "新增热点" if zmk > 0 else "逐渐减少的热点"
                    else:
                        pattern = "加强的热点"
                elif risk_level == "high":
                    pattern = "持续的热点"
                else:
                    pattern = "振荡热点"
                props["evolution_pattern"] = pattern
                props["pattern_color"] = pattern_colors.get(pattern, "#9e9e9e")
        return geojson
    raise ValueError("演化模式数据不可用，请先执行风险分析")


def export_alert_list(batch_id: str, risk_level: Optional[str] = None) -> str:
    if batch_id not in hotspot_cache:
        raise ValueError("请先执行风险分析")
    gdf = hotspot_cache[batch_id]
    filtered = gdf if not risk_level or risk_level == "all" else gdf[gdf["risk_level"] == risk_level]
    if filtered.empty:
        raise ValueError("没有符合条件的热点区域")
    filtered = filtered.copy()
    filtered["center_lon"] = filtered.geometry.x
    filtered["center_lat"] = filtered.geometry.y
    filtered["boundary_coords"] = filtered.geometry.apply(lambda geom: json.dumps(geom.__geo_interface__["coordinates"]))
    csv_path = OUTPUT_DIR / f"{batch_id}_hotspots_{int(time.time())}.csv"
    filtered[
        [
            "area_id",
            "risk_level",
            "time_slice",
            "gi_z",
            "trajectory_count",
            "center_lon",
            "center_lat",
            "boundary_coords",
        ]
    ].to_csv(csv_path, index=False, encoding="utf-8-sig")
    return str(csv_path)


def build_recommendation_text(batch_id: str) -> str:
    if batch_id not in hotspot_cache:
        raise ValueError("请先执行风险分析")
    lines: List[str] = []
    for _, row in hotspot_cache[batch_id].iterrows():
        recs = generate_recommendations(
            {
                "risk_level": row.get("risk_level"),
                "time_slice": row.get("time_slice"),
                "avg_speed": row.get("avg_speed"),
                "male_young_ratio": row.get("male_young_ratio", 0.4),
            }
        )
        lines.append(
            "\n".join(
                [
                    f"【区域ID：{row['area_id']}】风险等级：{row['risk_level']}（Z={row['gi_z']:.2f}）",
                    f"热点时间：{row['time_slice']}",
                    f"平均速度：{row['avg_speed']:.2f}，涉及轨迹：{row['trajectory_count']}",
                    "应对建议：",
                    *[f"{i+1}. {text}" for i, text in enumerate(recs)],
                    "",
                ]
            )
        )
    return "\n".join(lines).strip()


def save_feedback_record(
    user_type: str,
    title: str,
    content: str,
    lon: Optional[str],
    lat: Optional[str],
    photo_path: Optional[str],
) -> Dict:
    record = {
        "feedback_id": f"FB-{int(time.time())}",
        "user_type": user_type,
        "title": title,
        "content": content,
        "lon": lon,
        "lat": lat,
        "photo_path": photo_path,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    feedback_records.append(record)
    json_path = OUTPUT_DIR / "feedback_records.json"
    with open(json_path, "w", encoding="utf-8") as fp:
        json.dump(feedback_records, fp, ensure_ascii=False, indent=2)
    return record


def list_feedback_records() -> List[Dict]:
    return feedback_records

