"""
预警推送服务（3.0 增强）。

实现三级预警（红/黄/蓝）、多终端推送、预警跟踪等功能。
面向一线警务实战，支持自动分级与手动推送。
"""
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .runtime_pipeline import HOTSPOT_FILE, SUMMARY_FILE, RUNTIME_DIR


class AlertLevel(Enum):
    """预警等级枚举。"""
    RED = "red"  # 红色预警：加强的热点
    YELLOW = "yellow"  # 黄色预警：新增热点
    BLUE = "blue"  # 蓝色预警：持续的热点


ALERT_FILE = RUNTIME_DIR / "alert_records.json"


class AlertService:
    """预警推送服务。"""

    def __init__(self):
        self.alert_file = ALERT_FILE

    def generate_alerts_from_analysis(self) -> List[Dict[str, Any]]:
        """
        基于最新分析结果自动生成预警。

        根据热点演化模式与风险等级，自动分级预警。
        """
        if not SUMMARY_FILE.exists() or not HOTSPOT_FILE.exists():
            return []

        alerts = []
        with open(HOTSPOT_FILE, "r", encoding="utf-8") as f:
            hotspots_geojson = json.load(f)

        with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
            summary = json.load(f)

        trend = summary.get("trend", {})
        trend_type = trend.get("trend", "no trend")
        zmk = trend.get("zmk", 0)

        for feature in hotspots_geojson.get("features", []):
            props = feature.get("properties", {})
            risk_level = props.get("risk_level", "low")
            gi_score = props.get("gi_score", props.get("gi_z", 0))

            # 根据风险等级和趋势确定预警等级
            if risk_level == "high" and gi_score >= 2.58:
                alert_level = AlertLevel.RED.value
                alert_type = "加强的热点"
            elif risk_level == "high" and abs(zmk) > 2.58:
                alert_level = AlertLevel.YELLOW.value
                alert_type = "新增热点"
            elif risk_level in ["medium", "high"]:
                alert_level = AlertLevel.BLUE.value
                alert_type = "持续的热点"
            else:
                continue  # 低风险不预警

            alert = {
                "alert_id": f"ALERT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(alerts) + 1:04d}",
                "area_id": props.get("area_id"),
                "area_name": props.get("area_name"),
                "alert_level": alert_level,
                "alert_type": alert_type,
                "risk_level": risk_level,
                "gi_score": gi_score,
                "center_lon": props.get("center_lon", 0),
                "center_lat": props.get("center_lat", 0),
                "time_slice": props.get("time_slice", ""),
                "trajectory_count": props.get("trajectory_count", 0),
                "expected_period": self._estimate_high_risk_period(props),
                "control_suggestions": self._generate_control_suggestions(alert_level, risk_level),
                "created_at": datetime.now().isoformat(),
                "status": "pending",  # pending, sent, read, handled
                "read_at": None,
                "handled_at": None,
            }
            alerts.append(alert)

        # 保存预警记录
        self._save_alerts(alerts)
        return alerts

    def _estimate_high_risk_period(self, props: Dict[str, Any]) -> str:
        """估算高风险时段。"""
        time_slice = props.get("time_slice", "")
        if ":" in time_slice:
            try:
                # 尝试从时间窗口提取小时
                parts = time_slice.split("~")
                if len(parts) >= 1:
                    hour_str = parts[0].split()[-1].split(":")[0]
                    hour = int(hour_str)
                    if 7 <= hour < 9:
                        return "早高峰（7:00-9:00）"
                    elif 17 <= hour < 19:
                        return "晚高峰（17:00-19:00）"
                    elif 12 <= hour < 14:
                        return "午间小高峰（12:00-14:00）"
                    elif 21 <= hour < 23:
                        return "夜间平峰（21:00-23:00）"
            except (ValueError, IndexError):
                pass
        return "全天"

    def _generate_control_suggestions(
        self,
        alert_level: str,
        risk_level: str,
    ) -> List[str]:
        """生成管控建议。"""
        suggestions = []
        if alert_level == AlertLevel.RED.value:
            suggestions.append("一级管控：部署固定警力2名，配备AI抓拍设备1套")
            suggestions.append("设置临时减速带，联动共享电单车平台推送减速提醒")
            suggestions.append("24小时内启动专项整治，3天内评估效果")
        elif alert_level == AlertLevel.YELLOW.value:
            suggestions.append("二级管控：启动临时执勤，增派移动警力")
            suggestions.append("设施调整：检查交叉口、公交站等POI，识别设施缺陷")
            suggestions.append("7天内持续跟踪，评估干预效果")
        else:  # BLUE
            suggestions.append("三级管控：保持常态化巡查，跟踪后续趋势")
            suggestions.append("每月复查，对比分析效果")
        return suggestions

    def _save_alerts(self, alerts: List[Dict[str, Any]]):
        """保存预警记录。"""
        existing = self.load_all_alerts()
        existing.extend(alerts)
        with open(self.alert_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    def load_all_alerts(
        self,
        alert_level: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """加载预警记录。"""
        if not self.alert_file.exists():
            return []
        with open(self.alert_file, "r", encoding="utf-8") as f:
            alerts = json.load(f)
        if alert_level:
            alerts = [a for a in alerts if a.get("alert_level") == alert_level]
        if status:
            alerts = [a for a in alerts if a.get("status") == status]
        return alerts

    def mark_alert_read(self, alert_id: str):
        """标记预警为已读。"""
        alerts = self.load_all_alerts()
        for alert in alerts:
            if alert.get("alert_id") == alert_id:
                alert["status"] = "read"
                alert["read_at"] = datetime.now().isoformat()
                break
        with open(self.alert_file, "w", encoding="utf-8") as f:
            json.dump(alerts, f, ensure_ascii=False, indent=2)

    def mark_alert_handled(self, alert_id: str):
        """标记预警为已处置。"""
        alerts = self.load_all_alerts()
        for alert in alerts:
            if alert.get("alert_id") == alert_id:
                alert["status"] = "handled"
                alert["handled_at"] = datetime.now().isoformat()
                break
        with open(self.alert_file, "w", encoding="utf-8") as f:
            json.dump(alerts, f, ensure_ascii=False, indent=2)

    def get_alert_statistics(self) -> Dict[str, Any]:
        """获取预警统计信息。"""
        alerts = self.load_all_alerts()
        total = len(alerts)
        by_level = {}
        by_status = {}
        for alert in alerts:
            level = alert.get("alert_level", "unknown")
            status = alert.get("status", "unknown")
            by_level[level] = by_level.get(level, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
        return {
            "total": total,
            "by_level": by_level,
            "by_status": by_status,
            "pending_count": by_status.get("pending", 0),
            "read_count": by_status.get("read", 0),
            "handled_count": by_status.get("handled", 0),
        }

