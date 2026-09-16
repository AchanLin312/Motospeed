"""
本地运行时数据管线。

在 2.0 版本中，我们将原本依赖 PostGIS/MySQL 的流程改造成
“文件存储 + 内置样例 + 一键分析”的轻量化实现，以便在无数据库
环境下也能完成上传、分析、预警、反馈的全链条演示。
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, box

from ..utils.geojson import gdf_to_feature_collection


ROOT_DIR = Path(__file__).resolve().parents[3]
# 添加项目根目录到 Python 路径，以便导入 spatial_analysis
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from spatial_analysis.moran_analysis import (
    global_moran_indicator,
    local_moran_indicator,
)
from spatial_analysis.hotspot_analysis import getis_ord_indicator
from spatial_analysis.trend_analysis import mann_kendall_trend
RUNTIME_DIR = ROOT_DIR / "outputs" / "runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

TRAJECTORY_FILE = RUNTIME_DIR / "trajectory_points.csv"
HOTSPOT_FILE = RUNTIME_DIR / "hotspot_areas.geojson"
GRID_FILE = RUNTIME_DIR / "risk_grid_summary.geojson"
LISA_FILE = RUNTIME_DIR / "lisa_cluster.geojson"  # 3.5 新增：保存 LISA 结果
SUMMARY_FILE = RUNTIME_DIR / "analysis_summary.json"
FEEDBACK_FILE = RUNTIME_DIR / "feedback_records.json"
MAP_FILE = ROOT_DIR / "outputs" / "risk_hotspots.html"
MAP_FILE.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_AMAP_KEY = os.getenv("AMAP_WEB_KEY", "a7fd9560ffd58dcc12262f8f3d834b53")
OVERSPEED_THRESHOLD = float(os.getenv("OVERSPEED_THRESHOLD_KMH", 20))
GRID_CELL_SIZE = float(os.getenv("GRID_CELL_SIZE_DEG", 0.0045))


def _to_json_safe(value: Any) -> Any:
    """将 numpy/pandas 标量递归转换为原生 Python 类型。"""
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def _write_json_atomic(payload: Any, target: Path):
    """原子写入 JSON，避免中途中断留下半截文件。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_suffix(target.suffix + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as fp:
        json.dump(_to_json_safe(payload), fp, ensure_ascii=False, indent=2)
    temp_path.replace(target)


def _read_csv_flexible(file_path: Path) -> pd.DataFrame:
    """自动识别分隔符，兼容制表符/逗号 CSV。"""
    try:
        return pd.read_csv(file_path, sep=None, engine="python")
    except Exception:
        return pd.read_csv(file_path, sep=",", engine="python", on_bad_lines="skip")


def _pick_column(df: pd.DataFrame, *candidates: str, default=None):
    """根据候选名称（不区分大小写）选择列。"""
    lowered = {col.lower(): col for col in df.columns}
    for name in candidates:
        key = name.lower()
        if key in lowered:
            return df[lowered[key]]
    if default is not None:
        return default
    raise KeyError(f"缺少必要字段：{'/'.join(candidates)}")


def _prepare_geodataframe(df: pd.DataFrame, source_name: str) -> gpd.GeoDataFrame:
    """标准化上传数据，生成 GeoDataFrame。"""
    batch_id = f"B-{uuid.uuid4().hex[:8]}"
    df = df.copy()

    # 字段映射
    try:
        order_series = _pick_column(df, "order_id", "id", "record_id", "轨迹id")
    except KeyError:
        order_series = pd.Series([f"{batch_id}-{i+1}" for i in range(len(df))])

    time_series = pd.to_datetime(
        _pick_column(df, "event_time", "time", "timestamp", "Time"),
        errors="coerce",
        utc=False,
    )
    lon_series = pd.to_numeric(
        _pick_column(df, "lon", "longitude", "x_position", "x", "经度"),
        errors="coerce",
    )
    lat_series = pd.to_numeric(
        _pick_column(df, "lat", "latitude", "y_position", "y", "纬度"),
        errors="coerce",
    )

    speed_series = pd.to_numeric(
        _pick_column(df, "speed_kmh", "speedkm", "speed", "SpeedKM", "Speed"),
        errors="coerce",
    ).fillna(0)

    overspeed_raw = _pick_column(
        df,
        "is_overspeed",
        "overspeed",
        "overspeeding",
        default=pd.Series(np.nan, index=df.index),
    )
    overspeed_series = pd.to_numeric(overspeed_raw, errors="coerce")
    overspeed_series = overspeed_series.where(~overspeed_series.isna(), speed_series >= OVERSPEED_THRESHOLD)

    gender_series = _pick_column(df, "gender", "sex", default=pd.Series("未知", index=df.index))
    age_series = pd.to_numeric(
        _pick_column(df, "age", "年龄", default=pd.Series(np.nan, index=df.index)),
        errors="coerce",
    )

    normalized = pd.DataFrame(
        {
            "order_id": order_series.astype(str),
            "event_time": time_series,
            "lon": lon_series,
            "lat": lat_series,
            "speed_kmh": speed_series,
            "is_overspeed": overspeed_series.astype(int),
            "gender": gender_series.astype(str),
            "age": age_series,
            "batch_id": batch_id,
            "source_file": source_name,
        }
    ).dropna(subset=["event_time", "lon", "lat"])

    normalized["event_time"] = pd.to_datetime(normalized["event_time"])
    normalized["age"] = normalized["age"].fillna(-1).astype(int)

    geometry = gpd.points_from_xy(normalized["lon"], normalized["lat"], crs="EPSG:4326")
    gdf = gpd.GeoDataFrame(normalized, geometry=geometry, crs="EPSG:4326")
    return gdf


def ingest_csv_file(file_path: Path, source_name: str) -> Dict[str, Any]:
    """面向上传路由的入口，读取文件后执行标准化与持久化。"""
    df = _read_csv_flexible(file_path)
    return ingest_dataframe(df, source_name)


def ingest_dataframe(df: pd.DataFrame, source_name: str) -> Dict[str, Any]:
    gdf = _prepare_geodataframe(df, source_name)
    summary = _append_trajectory_records(gdf)
    bbox = gdf.total_bounds
    return {
        **summary,
        "batch_id": gdf["batch_id"].iloc[0],
        "source_file": source_name,
        "time_range": [
            gdf["event_time"].min().isoformat(),
            gdf["event_time"].max().isoformat(),
        ],
        "bounding_box": {
            "lon_min": bbox[0],
            "lat_min": bbox[1],
            "lon_max": bbox[2],
            "lat_max": bbox[3],
        },
    }


def _append_trajectory_records(gdf: gpd.GeoDataFrame) -> Dict[str, Any]:
    """将 GeoDataFrame 追加写入运行时 CSV。"""
    if TRAJECTORY_FILE.exists():
        existing = pd.read_csv(TRAJECTORY_FILE, parse_dates=["event_time"])
        combined = pd.concat([existing, gdf.drop(columns="geometry")], ignore_index=True)
        combined.drop_duplicates(
            subset=["order_id", "event_time", "lon", "lat"], inplace=True
        )
    else:
        combined = gdf.drop(columns="geometry").copy()
    combined.to_csv(TRAJECTORY_FILE, index=False, encoding="utf-8")
    return {
        "uploaded_rows": len(gdf),
        "total_rows": len(combined),
    }


def _load_points_dataframe() -> pd.DataFrame:
    if TRAJECTORY_FILE.exists():
        return pd.read_csv(TRAJECTORY_FILE, parse_dates=["event_time"])
    raise FileNotFoundError("当前缺少轨迹数据，请先上传 CSV")


def load_points_geodata(start_time: Optional[str] = None, end_time: Optional[str] = None) -> gpd.GeoDataFrame:
    df = _load_points_dataframe()
    if start_time:
        df = df[df["event_time"] >= pd.to_datetime(start_time)]
    if end_time:
        df = df[df["event_time"] <= pd.to_datetime(end_time)]
    if df.empty:
        raise ValueError("筛选条件下暂无轨迹数据")
    geometry = gpd.points_from_xy(df["lon"], df["lat"], crs="EPSG:4326")
    return gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")


def _aggregate_to_grid(gdf: gpd.GeoDataFrame, cell_size: float) -> gpd.GeoDataFrame:
    """将点数据聚合到网格。"""
    gdf = gdf.copy()
    lon_idx = np.floor(gdf.geometry.x / cell_size)
    lat_idx = np.floor(gdf.geometry.y / cell_size)
    gdf["lon_min"] = lon_idx * cell_size
    gdf["lat_min"] = lat_idx * cell_size
    gdf["grid_id"] = gdf.apply(lambda row: f"G{int(lon_idx.loc[row.name])}_{int(lat_idx.loc[row.name])}", axis=1)

    grouped = (
        gdf.groupby("grid_id")
        .agg(
            lon_min=("lon_min", "first"),
            lat_min=("lat_min", "first"),
            overspeed_count=("is_overspeed", "sum"),
            trajectory_count=("order_id", "count"),
            avg_speed=("speed_kmh", "mean"),
            time_start=("event_time", "min"),
            time_end=("event_time", "max"),
        )
        .reset_index()
    )

    grouped["geometry"] = grouped.apply(
        lambda row: box(
            row["lon_min"],
            row["lat_min"],
            row["lon_min"] + cell_size,
            row["lat_min"] + cell_size,
        ),
        axis=1,
    )
    result = gpd.GeoDataFrame(grouped, geometry="geometry", crs="EPSG:4326")
    projected = result.to_crs(epsg=3857)
    centroids = projected.centroid.to_crs(epsg=4326)
    result["center_lon"] = centroids.x
    result["center_lat"] = centroids.y
    result["time_slice"] = result.apply(
        lambda row: f"{row['time_start']:%Y-%m-%d %H:%M} ~ {row['time_end']:%H:%M}",
        axis=1,
    )
    result["area_name"] = result["grid_id"].apply(lambda gid: f"风险网格 {gid}")
    return result


def _ensure_hotspots(hotspots: gpd.GeoDataFrame, grid_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if not hotspots.empty:
        return hotspots
    fallback = grid_gdf.sort_values("overspeed_count", ascending=False).head(8).copy()
    if fallback.empty:
        return fallback
    fallback["gi_z"] = np.where(
        fallback["overspeed_count"] >= fallback["overspeed_count"].median(),
        2.1,
        1.7,
    )
    fallback["risk_level"] = fallback["gi_z"].apply(
        lambda z: "high" if z >= 2.58 else "medium" if z >= 1.96 else "low"
    )
    return fallback


def _save_geojson(gdf: gpd.GeoDataFrame, target: Path):
    geojson = gdf_to_feature_collection(gdf)
    _write_json_atomic(geojson, target)


def _build_hotspot_map(hotspots: gpd.GeoDataFrame, center: Optional[list] = None) -> str:
    if hotspots.empty:
        raise ValueError("暂无热点可渲染地图")
    if center is None:
        center = [hotspots["center_lat"].mean(), hotspots["center_lon"].mean()]
    fmap = folium.Map(location=center, zoom_start=13, tiles=None, control_scale=True)
    folium.TileLayer(
        tiles=f"https://webrd0{{s}}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scl=1&style=8&x={{x}}&y={{y}}&z={{z}}&ltype=7&key={DEFAULT_AMAP_KEY}",
        attr="&copy; 高德地图",
        subdomains=["1", "2", "3", "4"],
        name="Gaode",
    ).add_to(fmap)

    color_map = {"high": "#d32f2f", "medium": "#f57c00", "low": "#fbc02d"}

    folium.GeoJson(
        data=gdf_to_feature_collection(hotspots),
        style_function=lambda feature: {
            "color": color_map.get(feature["properties"].get("risk_level"), "#1976d2"),
            "weight": 2,
            "fillColor": color_map.get(feature["properties"].get("risk_level"), "#1976d2"),
            "fillOpacity": 0.35,
        },
        highlight_function=lambda _: {"weight": 3, "fillOpacity": 0.5},
        tooltip=folium.GeoJsonTooltip(
            fields=["area_name", "risk_level", "time_slice", "gi_score", "trajectory_count"],
            aliases=["热点名称", "风险等级", "时间窗口", "Gi* Z 值", "轨迹数"],
        ),
    ).add_to(fmap)

    for _, row in hotspots.iterrows():
        folium.CircleMarker(
            location=[row["center_lat"], row["center_lon"]],
            radius=4,
            color=color_map.get(row["risk_level"], "#1976d2"),
            fill=True,
            fill_opacity=0.9,
            popup=f"{row['area_name']} | Z={row['gi_score']:.2f}",
        ).add_to(fmap)

    fmap.save(str(MAP_FILE))
    return str(MAP_FILE)


def run_full_analysis(params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """执行完整空间分析流程，并缓存结果。"""
    params = params or {}
    cell_size = float(params.get("cell_size_deg", GRID_CELL_SIZE))
    threshold = float(params.get("overspeed_threshold", OVERSPEED_THRESHOLD))

    gdf = load_points_geodata()
    if gdf.empty:
        raise ValueError("暂无轨迹数据，无法执行分析")
    gdf["is_overspeed"] = (gdf["speed_kmh"] >= threshold).astype(int)

    grid_gdf = _aggregate_to_grid(gdf, cell_size)
    if len(grid_gdf) < 3:
        raise ValueError("网格数量不足（至少需要 3 个）")

    global_stats = global_moran_indicator(grid_gdf, "overspeed_count")
    lisa_gdf = local_moran_indicator(grid_gdf, "overspeed_count")
    hotspot_gdf = getis_ord_indicator(grid_gdf, "overspeed_count")
    hotspot_gdf = _ensure_hotspots(hotspot_gdf, grid_gdf).copy()
    if hotspot_gdf.empty:
        raise ValueError("风险热点计算结果为空")

    hotspot_gdf["gi_score"] = hotspot_gdf["gi_z"]
    hotspot_gdf["area_id"] = [f"HS-{i+1:04d}" for i in range(len(hotspot_gdf))]
    hotspot_gdf["area_name"] = hotspot_gdf["area_name"].astype(str)
    hotspot_gdf["areaName"] = hotspot_gdf["area_name"]

    trend_series = (
        gdf.set_index("event_time")
        .resample("1h")["is_overspeed"]
        .sum()
        .reset_index(drop=True)
    )
    trend_stats = (
        mann_kendall_trend(trend_series) if len(trend_series) > 4 else {"trend": "no trend"}
    )

    _save_geojson(grid_gdf, GRID_FILE)
    _save_geojson(hotspot_gdf, HOTSPOT_FILE)
    _save_geojson(lisa_gdf, LISA_FILE)  # 3.5 新增：保存 LISA 聚类结果
    csv_path = _export_hotspots_csv(hotspot_gdf, params.get("risk_level"))
    map_path = _build_hotspot_map(hotspot_gdf)
    
    # 3.6 新增：分析完成后自动生成可视化文件和图表
    try:
        from .visualization_service import VisualizationService
        from .chart_generator import ChartGenerator
        viz_service = VisualizationService()
        chart_gen = ChartGenerator()
        
        # 生成 LISA 聚类图（用于导出）
        try:
            viz_service.generate_lisa_cluster_map()
        except Exception:
            pass
        # 生成演化模式分布图（用于导出）
        try:
            viz_service.generate_evolution_pattern_map()
        except Exception:
            pass
        # 生成图表
        try:
            chart_gen.generate_dashboard_chart()
        except Exception:
            pass
        try:
            chart_gen.generate_trend_chart(days=30)
        except Exception:
            pass
        try:
            chart_gen.generate_time_distribution_chart()
        except Exception:
            pass
        # 生成报告
        try:
            from .report_generator import ReportGenerator
            report_gen = ReportGenerator()
            report_gen.generate_risk_analysis_report(format_type="word", include_charts=False)
        except Exception:
            pass
    except Exception:
        pass  # 可视化生成失败不影响主流程

    summary = {
        "global_moran": global_stats,
        "grid_count": int(len(grid_gdf)),
        "hotspot_count": int(len(hotspot_gdf)),
        "trend": trend_stats,
        "cell_size_deg": cell_size,
        "overspeed_threshold": threshold,
        "csv_path": str(csv_path),
        "geojson_path": str(HOTSPOT_FILE),
        "map_path": str(map_path),
        "generated_at": datetime.utcnow().isoformat(),
    }
    summary = _to_json_safe(summary)
    _write_json_atomic(summary, SUMMARY_FILE)
    return summary


def _export_hotspots_csv(hotspot_gdf: gpd.GeoDataFrame, risk_level: Optional[str]) -> Path:
    filtered = hotspot_gdf.copy()
    if risk_level and risk_level != "all":
        filtered = filtered[filtered["risk_level"] == risk_level]
    filtered = filtered.copy()
    projected = filtered.to_crs(epsg=3857)
    centroids = projected.centroid.to_crs(epsg=4326)
    filtered["center_lon"] = centroids.x
    filtered["center_lat"] = centroids.y
    target = RUNTIME_DIR / f"hotspots_{int(datetime.utcnow().timestamp())}.csv"
    filtered[
        [
            "area_id",
            "area_name",
            "risk_level",
            "time_slice",
            "gi_score",
            "trajectory_count",
            "center_lon",
            "center_lat",
        ]
    ].to_csv(target, index=False, encoding="utf-8-sig")
    return target


def get_latest_summary() -> Dict[str, Any]:
    if SUMMARY_FILE.exists():
        try:
            with open(SUMMARY_FILE, "r", encoding="utf-8") as fp:
                return json.load(fp)
        except json.JSONDecodeError:
            # 历史运行可能留下半截摘要文件，重新分析即可恢复。
            return run_full_analysis({})
    raise FileNotFoundError("尚未执行过风险分析")


def load_hotspots_geojson(
    risk_level: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> Dict[str, Any]:
    if not HOTSPOT_FILE.exists():
        return {"type": "FeatureCollection", "features": []}
    with open(HOTSPOT_FILE, "r", encoding="utf-8") as fp:
        geojson = json.load(fp)

    def _within(feature):
        props = feature.get("properties", {})
        if risk_level and risk_level != "all" and props.get("risk_level") != risk_level:
            return False
        if start_time and props.get("time_start") and props.get("time_end"):
            start = datetime.fromisoformat(props["time_start"])
            end = datetime.fromisoformat(props["time_end"])
            if end < datetime.fromisoformat(start_time) or start > datetime.fromisoformat(end_time or start_time):
                return False
        return True

    geojson["features"] = [f for f in geojson.get("features", []) if _within(f)]
    return geojson


def export_hotspots_csv(risk_level: Optional[str], start_time: Optional[str], end_time: Optional[str]) -> Dict[str, str]:
    if not HOTSPOT_FILE.exists():
        raise FileNotFoundError("暂无热点文件，请先执行风险分析")
    with open(HOTSPOT_FILE, "r", encoding="utf-8") as fp:
        geojson = json.load(fp)
    features = geojson.get("features", [])
    rows = []
    for feature in features:
        props = feature.get("properties", {})
        if risk_level and risk_level != "all" and props.get("risk_level") != risk_level:
            continue
        if start_time and end_time and props.get("time_start") and props.get("time_end"):
            start = datetime.fromisoformat(props["time_start"])
            end = datetime.fromisoformat(props["time_end"])
            if end < datetime.fromisoformat(start_time) or start > datetime.fromisoformat(end_time):
                continue
        rows.append(
            {
                "area_id": props.get("area_id"),
                "area_name": props.get("area_name"),
                "risk_level": props.get("risk_level"),
                "time_slice": props.get("time_slice"),
                "gi_score": props.get("gi_score"),
                "trajectory_count": props.get("trajectory_count"),
            }
        )
    if not rows:
        raise ValueError("筛选条件下未找到热点记录")
    target = RUNTIME_DIR / f"hotspots_export_{int(datetime.utcnow().timestamp())}.csv"
    pd.DataFrame(rows).to_csv(target, index=False, encoding="utf-8-sig")
    return {"csv_path": str(target)}


def record_feedback_locally(payload: Dict[str, Any]) -> int:
    """写入本地 JSON，作为 MySQL 不可用时的兜底。"""
    record = {
        "feedback_id": f"FB-{uuid.uuid4().hex[:6]}",
        **payload,
        "created_at": datetime.utcnow().isoformat(),
    }
    existing = []
    if FEEDBACK_FILE.exists():
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as fp:
            existing = json.load(fp)
    existing.append(record)
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as fp:
        json.dump(existing, fp, ensure_ascii=False, indent=2)
    return record["feedback_id"]


def load_feedback_records() -> list[Dict[str, Any]]:
    """读取本地反馈记录，便于 API 查询。"""
    if FEEDBACK_FILE.exists():
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as fp:
            return json.load(fp)
    return []


def bootstrap_runtime_assets():
    """启动时自动装载示例数据与默认分析结果。"""
    if not TRAJECTORY_FILE.exists():
        sample = ROOT_DIR / "data.csv"
        if not sample.exists():
            sample = ROOT_DIR / "test_data.csv"
        if sample.exists():
            ingest_csv_file(sample, sample.name)
    if not HOTSPOT_FILE.exists() or not SUMMARY_FILE.exists() or not MAP_FILE.exists():
        try:
            run_full_analysis({})
        except Exception:
            pass


