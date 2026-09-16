"""
增强的可视化服务（3.0 新增）。

提供 LISA 聚类图、演化模式分布图、综合仪表盘、趋势折线图等高级可视化。
支持交互式图表生成与导出。
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import folium
import geopandas as gpd
import pandas as pd
import numpy as np

from ..utils.geojson import gdf_to_feature_collection
from .runtime_pipeline import (
    RUNTIME_DIR,
    HOTSPOT_FILE,
    GRID_FILE,
    LISA_FILE,
    SUMMARY_FILE,
    TRAJECTORY_FILE,
    DEFAULT_AMAP_KEY,
)


class VisualizationService:
    """可视化服务，生成各类图表与地图。"""

    def __init__(self):
        self.output_dir = Path(__file__).resolve().parents[3] / "outputs" / "visualizations"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_lisa_cluster_geojson(self) -> Dict[str, Any]:
        """
        获取 LISA 聚类 GeoJSON 数据（供 UI 直接使用）。

        5类聚类模式：
        - 高-高聚类（红色）：核心风险区
        - 高-低异常值（橙色）：隐患预警区
        - 低-高异常值（蓝色）：潜在风险区
        - 低-低聚类（绿色）：安全区
        - 不具有显著性（灰色）：随机分布
        """
        if not LISA_FILE.exists():
            # 如果没有 LISA 文件，尝试从 GRID 文件加载
            if not GRID_FILE.exists():
                raise FileNotFoundError("尚未执行空间自相关分析")
            with open(GRID_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        
        with open(LISA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def generate_lisa_cluster_map(self) -> str:
        """
        生成 LISA 聚类图 HTML 文件（用于导出）。
        """
        lisa_geojson = self.get_lisa_cluster_geojson()
        features = lisa_geojson.get("features", [])
        if not features:
            raise ValueError("LISA 聚类数据为空")

        # 确定地图中心
        lons = []
        lats = []
        for feature in features:
            geom = feature.get("geometry", {})
            if geom.get("type") == "Polygon":
                coords = geom.get("coordinates", [])[0]
                for coord in coords:
                    lons.append(coord[0])
                    lats.append(coord[1])
            elif geom.get("type") == "Point":
                lons.append(geom.get("coordinates", [0])[0])
                lats.append(geom.get("coordinates", [0])[1])

        center = [np.mean(lats), np.mean(lons)] if lats else [28.2, 113.0]

        fmap = folium.Map(location=center, zoom_start=12, tiles=None, control_scale=True)
        folium.TileLayer(
            tiles=f"https://webrd0{{s}}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scl=1&style=8&x={{x}}&y={{y}}&z={{z}}&ltype=7&key={DEFAULT_AMAP_KEY}",
            attr="&copy; 高德地图",
            subdomains=["1", "2", "3", "4"],
            name="高德地图",
        ).add_to(fmap)

        # LISA 聚类颜色映射
        cluster_colors = {
            "高-高": "#d32f2f",  # 红色
            "高-低": "#f57c00",  # 橙色
            "低-高": "#1976d2",  # 蓝色
            "低-低": "#388e3c",  # 绿色
            "不具有显著性": "#9e9e9e",  # 灰色
        }

        # 添加 LISA 聚类图层
        for feature in features:
            props = feature.get("properties", {})
            cluster_label = props.get("cluster_label", "不具有显著性")
            color = cluster_colors.get(cluster_label, "#9e9e9e")

            # 创建样式函数，确保闭包正确捕获颜色
            def make_style_func(c):
                return lambda feat: {
                    "fillColor": c,
                    "color": c,
                    "weight": 2,
                    "fillOpacity": 0.5,
                }

            folium.GeoJson(
                data=feature,
                style_function=make_style_func(color),
                tooltip=folium.GeoJsonTooltip(
                    fields=["grid_id", "cluster_label", "overspeed_count", "trajectory_count"],
                    aliases=["网格ID", "聚类模式", "超速次数", "轨迹数"],
                ),
            ).add_to(fmap)

        # 添加图例
        legend_html = """
        <div style="position: fixed; 
                    bottom: 50px; right: 50px; width: 200px; height: 180px; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:14px; padding: 10px">
        <h4>LISA 聚类模式</h4>
        <p><span style="color:#d32f2f">■</span> 高-高聚类（核心风险区）</p>
        <p><span style="color:#f57c00">■</span> 高-低异常值（隐患预警区）</p>
        <p><span style="color:#1976d2">■</span> 低-高异常值（潜在风险区）</p>
        <p><span style="color:#388e3c">■</span> 低-低聚类（安全区）</p>
        <p><span style="color:#9e9e9e">■</span> 不具有显著性</p>
        </div>
        """
        fmap.get_root().html.add_child(folium.Element(legend_html))

        filepath = self.output_dir / f"lisa_cluster_map_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        fmap.save(str(filepath))
        return str(filepath)

    def get_evolution_pattern_geojson(self) -> Dict[str, Any]:
        """
        获取演化模式 GeoJSON 数据（供 UI 直接使用）。

        17类演化模式，支持时间轴播放。
        """
        if not HOTSPOT_FILE.exists():
            raise FileNotFoundError("尚未执行热点分析")

        with open(HOTSPOT_FILE, "r", encoding="utf-8") as f:
            hotspots_geojson = json.load(f)

        # 根据趋势判断演化模式并添加到属性中
        if SUMMARY_FILE.exists():
            with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
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

            for feature in hotspots_geojson.get("features", []):
                props = feature.get("properties", {})
                risk_level = props.get("risk_level", "low")
                gi_score = props.get("gi_score", props.get("gi_z", 0))

                # 判断演化模式
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

        return hotspots_geojson

    def generate_evolution_pattern_map(self) -> str:
        """
        生成演化模式分布图 HTML 文件（用于导出）。
        """
        hotspots_geojson = self.get_evolution_pattern_geojson()

        features = hotspots_geojson.get("features", [])
        if not features:
            raise ValueError("热点数据为空")

        # 确定地图中心
        lons = []
        lats = []
        for feature in features:
            props = feature.get("properties", {})
            if "center_lon" in props:
                lons.append(props["center_lon"])
                lats.append(props["center_lat"])

        center = [np.mean(lats), np.mean(lons)] if lats else [28.2, 113.0]

        fmap = folium.Map(location=center, zoom_start=12, tiles=None, control_scale=True)
        folium.TileLayer(
            tiles=f"https://webrd0{{s}}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scl=1&style=8&x={{x}}&y={{y}}&z={{z}}&ltype=7&key={DEFAULT_AMAP_KEY}",
            attr="&copy; 高德地图",
            subdomains=["1", "2", "3", "4"],
            name="高德地图",
        ).add_to(fmap)

        pattern_colors = {
            "振荡热点": "#9c27b0",
            "新增热点": "#ff9800",
            "加强的热点": "#d32f2f",
            "逐渐减少的热点": "#f06292",
            "持续的热点": "#1976d2",
        }

        for feature in features:
            props = feature.get("properties", {})
            pattern = props.get("evolution_pattern", "振荡热点")
            color = props.get("pattern_color", pattern_colors.get(pattern, "#9e9e9e"))

            def make_style_func(c):
                return lambda feat: {
                    "fillColor": c,
                    "color": c,
                    "weight": 2,
                    "fillOpacity": 0.4,
                }

            folium.GeoJson(
                data=feature,
                style_function=make_style_func(color),
                tooltip=folium.GeoJsonTooltip(
                    fields=["area_name", "risk_level", "evolution_pattern", "gi_score", "time_slice"],
                    aliases=["区域名称", "风险等级", "演化模式", "Gi* Z值", "时间窗口"],
                ),
            ).add_to(fmap)

        filepath = self.output_dir / f"evolution_pattern_map_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        fmap.save(str(filepath))
        return str(filepath)

    def generate_dashboard_data(self) -> Dict[str, Any]:
        """
        生成综合仪表盘数据。

        包含核心业务指标、实时预警信息、重点风险区域TOP10、管控效果排名。
        """
        if not SUMMARY_FILE.exists():
            return {}

        with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
            summary = json.load(f)

        # 加载热点数据
        hotspots = []
        if HOTSPOT_FILE.exists():
            with open(HOTSPOT_FILE, "r", encoding="utf-8") as f:
                hotspots_geojson = json.load(f)
            for feature in hotspots_geojson.get("features", []):
                props = feature.get("properties", {})
                hotspots.append({
                    "area_id": props.get("area_id"),
                    "area_name": props.get("area_name"),
                    "risk_level": props.get("risk_level"),
                    "gi_score": props.get("gi_score", props.get("gi_z", 0)),
                    "trajectory_count": props.get("trajectory_count", 0),
                })

        # TOP10 高风险区域
        top10_hotspots = sorted(
            hotspots,
            key=lambda x: x.get("gi_score", 0),
            reverse=True,
        )[:10]

        moran = summary.get("global_moran", {})
        trend = summary.get("trend", {})

        return {
            "core_metrics": {
                "hotspot_count": summary.get("hotspot_count", 0),
                "grid_count": summary.get("grid_count", 0),
                "global_moran_i": moran.get("moran_i", 0),
                "moran_p_value": moran.get("p_value", 0),
                "trend_zmk": trend.get("zmk", 0),
                "trend_type": trend.get("trend", "无显著趋势"),
            },
            "risk_distribution": {
                "high": sum(1 for h in hotspots if h.get("risk_level") == "high"),
                "medium": sum(1 for h in hotspots if h.get("risk_level") == "medium"),
                "low": sum(1 for h in hotspots if h.get("risk_level") == "low"),
            },
            "top10_hotspots": top10_hotspots,
            "generated_at": datetime.now().isoformat(),
        }

    def generate_trend_chart_data(
        self,
        area_id: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        生成趋势折线图数据。

        Args:
            area_id: 区域ID，None表示全域
            days: 时间范围（天数）

        Returns:
            包含时间序列数据的字典
        """
        if not TRAJECTORY_FILE.exists():
            return {"error": "缺少轨迹数据"}

        df = pd.read_csv(TRAJECTORY_FILE, parse_dates=["event_time"])
        df = df[df["event_time"] >= (datetime.now() - pd.Timedelta(days=days))]

        # 按日期聚合
        df["date"] = df["event_time"].dt.date
        daily_stats = df.groupby("date").agg({
            "is_overspeed": "sum",
            "order_id": "count",
            "speed_kmh": "mean",
        }).reset_index()

        return {
            "dates": [str(d) for d in daily_stats["date"]],
            "overspeed_counts": daily_stats["is_overspeed"].tolist(),
            "trajectory_counts": daily_stats["order_id"].tolist(),
            "avg_speeds": daily_stats["speed_kmh"].tolist(),
        }

    def generate_time_distribution_chart(
        self,
        area_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        生成时段分布柱状图数据。

        展示特定区域不同时段（0-24时按1小时划分）的超速次数分布。
        """
        if not TRAJECTORY_FILE.exists():
            return {"error": "缺少轨迹数据"}

        df = pd.read_csv(TRAJECTORY_FILE, parse_dates=["event_time"])
        df["hour"] = df["event_time"].dt.hour

        hourly_stats = df.groupby("hour").agg({
            "is_overspeed": "sum",
            "order_id": "count",
        }).reset_index()

        return {
            "hours": hourly_stats["hour"].tolist(),
            "overspeed_counts": hourly_stats["is_overspeed"].tolist(),
            "trajectory_counts": hourly_stats["order_id"].tolist(),
        }

