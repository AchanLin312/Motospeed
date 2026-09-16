"""
图表生成服务（3.6 新增）。

生成综合仪表盘、趋势折线图、时段分布柱状图等可视化图表。
使用 matplotlib 生成图片文件，供 UI 显示和报告使用。
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

from .runtime_pipeline import (
    RUNTIME_DIR,
    HOTSPOT_FILE,
    SUMMARY_FILE,
    TRAJECTORY_FILE,
)

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False


class ChartGenerator:
    """图表生成器，生成各类可视化图表。"""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or (Path(__file__).resolve().parents[3] / "outputs" / "charts")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_dashboard_chart(self) -> str:
        """
        生成综合仪表盘图表。

        包含核心业务指标、风险分布饼图、TOP10风险区域柱状图。
        """
        if not SUMMARY_FILE.exists():
            raise FileNotFoundError("尚未执行风险分析")

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
                    "risk_level": props.get("risk_level"),
                    "gi_score": props.get("gi_score", props.get("gi_z", 0)),
                })

        # 创建图表
        fig = plt.figure(figsize=(16, 10))
        fig.suptitle("综合仪表盘", fontsize=18, fontweight='bold', y=0.98)

        # 1. 核心指标（左上）
        ax1 = plt.subplot(2, 3, 1)
        ax1.axis('off')
        moran = summary.get("global_moran", {})
        metrics_text = f"""
核心业务指标

热点总数：{summary.get('hotspot_count', 0)}
网格总数：{summary.get('grid_count', 0)}
全局Moran's I：{moran.get('moran_i', 0):.4f}
p值：{moran.get('p_value', 0):.4f}
趋势ZMK值：{summary.get('trend', {}).get('zmk', 0):.2f}
        """
        ax1.text(0.1, 0.5, metrics_text, fontsize=12, verticalalignment='center',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        # 2. 风险分布饼图（右上）
        ax2 = plt.subplot(2, 3, 2)
        risk_counts = {
            "高": sum(1 for h in hotspots if h.get("risk_level") == "high"),
            "中": sum(1 for h in hotspots if h.get("risk_level") == "medium"),
            "低": sum(1 for h in hotspots if h.get("risk_level") == "low"),
        }
        if sum(risk_counts.values()) > 0:
            ax2.pie(risk_counts.values(), labels=risk_counts.keys(), autopct='%1.1f%%',
                   colors=['#d32f2f', '#f57c00', '#fbc02d'], startangle=90)
            ax2.set_title("风险分布", fontsize=14, fontweight='bold')
        else:
            ax2.text(0.5, 0.5, "暂无数据", ha='center', va='center', fontsize=12)
            ax2.set_title("风险分布", fontsize=14, fontweight='bold')

        # 3. TOP10 风险区域（左下，占2列）
        ax3 = plt.subplot(2, 3, (4, 6))
        top10 = sorted(hotspots, key=lambda x: x.get("gi_score", 0), reverse=True)[:10]
        if top10:
            areas = [f"区域{i+1}" for i in range(len(top10))]
            scores = [h.get("gi_score", 0) for h in top10]
            colors_list = ['#d32f2f' if h.get("risk_level") == "high" else 
                          '#f57c00' if h.get("risk_level") == "medium" else '#fbc02d'
                          for h in top10]
            ax3.barh(areas, scores, color=colors_list)
            ax3.set_xlabel("Gi* Z值", fontsize=12)
            ax3.set_title("TOP10 风险区域", fontsize=14, fontweight='bold')
            ax3.grid(axis='x', alpha=0.3)
        else:
            ax3.text(0.5, 0.5, "暂无数据", ha='center', va='center', fontsize=12)
            ax3.set_title("TOP10 风险区域", fontsize=14, fontweight='bold')

        plt.tight_layout(rect=[0, 0, 1, 0.96])

        filepath = self.output_dir / f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close()
        return str(filepath)

    def generate_trend_chart(self, days: int = 30, start_date: str = None, end_date: str = None) -> str:
        """
        生成趋势折线图。

        Args:
            days: 时间范围（天数），0表示全量数据（当start_date和end_date为None时使用）
            start_date: 起始日期（YYYY-MM-DD格式）
            end_date: 结束日期（YYYY-MM-DD格式）
        """
        if not TRAJECTORY_FILE.exists():
            raise FileNotFoundError("缺少轨迹数据")

        df = pd.read_csv(TRAJECTORY_FILE, parse_dates=["event_time"])
        
        # 处理时间过滤
        is_same_day = False
        if start_date and end_date:
            # 自定义日期范围
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)  # 包含结束日期当天
            df = df[(df["event_time"] >= start_dt) & (df["event_time"] <= end_dt)]
            
            # 检查是否是同一天
            if start_date == end_date:
                is_same_day = True
        elif days > 0:
            # 按天数
            cutoff_date = datetime.now() - timedelta(days=days)
            df = df[df["event_time"] >= cutoff_date]
        # days == 0 表示全量数据，不进行时间过滤

        # 根据是否同一天决定聚合方式
        if is_same_day:
            # 同一天：按小时聚合
            df["hour"] = df["event_time"].dt.hour
            hourly_stats = df.groupby("hour").agg({
                "is_overspeed": "sum",
                "order_id": "count",
                "speed_kmh": "mean",
            }).reset_index()
            
            fig, ax = plt.subplots(figsize=(12, 6))
            ax.plot(hourly_stats["hour"], hourly_stats["is_overspeed"], marker='o', linewidth=2, 
                   markersize=6, label='每小时超速次数', color='#d32f2f')
            ax.set_xlabel("小时（0-23时）", fontsize=12)
            ax.set_ylabel("超速次数", fontsize=12)
            ax.set_title(f"趋势折线图（{start_date} 24小时趋势）", fontsize=14, fontweight='bold')
            ax.set_xticks(range(0, 24, 2))  # 每2小时一个标签
            ax.legend(fontsize=11)
            ax.grid(True, alpha=0.3)
        else:
            # 多天：按日期聚合
            df["date"] = df["event_time"].dt.date
            daily_stats = df.groupby("date").agg({
                "is_overspeed": "sum",
                "order_id": "count",
                "speed_kmh": "mean",
            }).reset_index()

            fig, ax = plt.subplots(figsize=(12, 6))
            dates = [datetime.combine(d, datetime.min.time()) for d in daily_stats["date"]]
            
            ax.plot(dates, daily_stats["is_overspeed"], marker='o', linewidth=2, 
                   markersize=6, label='日均超速次数', color='#d32f2f')
            ax.set_xlabel("日期", fontsize=12)
            ax.set_ylabel("超速次数", fontsize=12)
            
            # 根据时间范围设置标题
            if start_date and end_date:
                title = f"趋势折线图（{start_date} 至 {end_date}）"
                num_days = len(daily_stats)
                interval = max(1, num_days // 15)  # 大约显示15个日期标签
            elif days == 0:
                title = "趋势折线图（全量数据）"
                num_days = len(daily_stats)
                interval = max(1, num_days // 15)
            else:
                title = f"趋势折线图（近{days}天）"
                interval = max(1, days // 10)
            
            ax.set_title(title, fontsize=14, fontweight='bold')
            ax.legend(fontsize=11)
            ax.grid(True, alpha=0.3)
            
            # 格式化日期
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=interval))
            plt.xticks(rotation=45)
        
        plt.tight_layout()

        filepath = self.output_dir / f"trend_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close()
        return str(filepath)

    def generate_time_distribution_chart(self) -> str:
        """
        生成时段分布柱状图。

        展示0-24时超速次数分布。
        """
        if not TRAJECTORY_FILE.exists():
            raise FileNotFoundError("缺少轨迹数据")

        df = pd.read_csv(TRAJECTORY_FILE, parse_dates=["event_time"])
        df["hour"] = df["event_time"].dt.hour

        hourly_stats = df.groupby("hour").agg({
            "is_overspeed": "sum",
            "order_id": "count",
        }).reset_index()

        fig, ax = plt.subplots(figsize=(14, 6))
        hours = hourly_stats["hour"]
        overspeed_counts = hourly_stats["is_overspeed"]
        
        bars = ax.bar(hours, overspeed_counts, color='#165DFF', alpha=0.7, edgecolor='#0E42D2', linewidth=1)
        ax.set_xlabel("时段（小时）", fontsize=12)
        ax.set_ylabel("超速次数", fontsize=12)
        ax.set_title("时段分布柱状图（0-24时）", fontsize=14, fontweight='bold')
        ax.set_xticks(range(0, 24, 2))
        ax.grid(axis='y', alpha=0.3)
        
        # 标注最大值
        max_idx = overspeed_counts.idxmax()
        max_hour = hours.iloc[max_idx]
        max_count = overspeed_counts.iloc[max_idx]
        ax.annotate(f'峰值: {max_count}次\n({max_hour}时)', 
                   xy=(max_hour, max_count), xytext=(max_hour + 2, max_count * 0.9),
                   arrowprops=dict(arrowstyle='->', color='red', lw=2),
                   fontsize=10, bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7))
        
        plt.tight_layout()

        filepath = self.output_dir / f"time_distribution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close()
        return str(filepath)

