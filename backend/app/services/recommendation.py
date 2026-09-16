"""
应对建议规则引擎（3.0 增强）。

结合论文 4.1 “振荡/新增/逐渐减少热点”策略，总结为规则。
支持策略模板管理、多部门协同建议。
"""
import json
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional

from .runtime_pipeline import RUNTIME_DIR

TEMPLATE_FILE = RUNTIME_DIR / "strategy_templates.json"


class RecommendationService:
    """应对建议服务（3.0 增强版）。"""

    def __init__(self):
        self.template_file = TEMPLATE_FILE
        self._init_default_templates()

    def _init_default_templates(self):
        """初始化默认策略模板。"""
        if not self.template_file.exists():
            default_templates = {
                "high_risk": {
                    "name": "高风险区域策略模板",
                    "police": "部署固定警力2名，配备AI抓拍设备1套",
                    "facility": "设置临时减速带，拓宽非机动车道",
                    "education": "开展'文明骑行'主题宣传，联动共享电单车平台推送减速提醒",
                    "duration": "24小时内启动，3天内评估效果",
                },
                "medium_risk": {
                    "name": "中风险区域策略模板",
                    "police": "加强巡逻频次，在高峰时段增派移动警力",
                    "facility": "检查交叉口、公交站等POI，识别设施缺陷",
                    "education": "在高校与商圈周边开展交通守法宣教",
                    "duration": "7天内持续跟踪，评估干预效果",
                },
                "low_risk": {
                    "name": "低风险区域策略模板",
                    "police": "保持常态化巡查",
                    "facility": "定期检查基础设施",
                    "education": "保持宣传引导",
                    "duration": "每月复查，对比分析效果",
                },
                "new_hotspot": {
                    "name": "新增热点策略模板",
                    "police": "启动临时执勤，增派移动警力",
                    "facility": "设施调整：检查交叉口、公交站等POI",
                    "education": "加强现场宣传引导",
                    "duration": "7天内持续跟踪，评估干预效果",
                },
                "oscillating_hotspot": {
                    "name": "振荡热点策略模板",
                    "police": "周期性加强巡逻，识别周期性规律",
                    "facility": "针对周期性时段优化设施配置",
                    "education": "在周期性高发时段加强宣传",
                    "duration": "持续跟踪周期性变化",
                },
            }
            self.template_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.template_file, "w", encoding="utf-8") as f:
                json.dump(default_templates, f, ensure_ascii=False, indent=2)

    def generate_recommendations(
        self,
        hotspot: Dict,
        use_template: bool = True,
    ) -> Dict[str, List[str]]:
        """
        生成应对建议（3.0 增强版）。

        Returns:
            包含警力配置、设施优化、宣传引导、多部门协同的建议字典
        """
        recommendations = {
            "police": [],
            "facility": [],
            "education": [],
            "multi_department": [],
        }

        risk_level = hotspot.get("risk_level", "medium")
        time_slice = hotspot.get("time_slice", "")
        avg_speed = hotspot.get("avg_speed", 0)
        young_male_ratio = hotspot.get("male_young_ratio", 0)
        gi_score = hotspot.get("gi_score", hotspot.get("gi_z", 0))

        # 判断演化模式
        evolution_pattern = self._detect_evolution_pattern(hotspot)

        if use_template:
            # 使用策略模板
            templates = self._load_templates()
            template_key = self._select_template(risk_level, evolution_pattern)
            template = templates.get(template_key, templates.get("medium_risk", {}))

            recommendations["police"].append(template.get("police", ""))
            recommendations["facility"].append(template.get("facility", ""))
            recommendations["education"].append(template.get("education", ""))
            recommendations["multi_department"].append(
                f"执行周期：{template.get('duration', '持续跟踪')}"
            )
        else:
            # 基于规则的动态生成
            if risk_level == "high":
                recommendations["police"].append(
                    "持续强化基础设施巡检，设置临时物理隔离，压降高频违法行为。"
                )
            if time_slice:
                try:
                    hour = int(str(time_slice).split(":")[0][-2:])
                    if 21 <= hour or hour < 6:
                        recommendations["police"].append(
                            "夜间时段增派警力与移动照明，联动周边社区加强巡查。"
                        )
                except (ValueError, IndexError):
                    pass
            if avg_speed > 20:
                recommendations["facility"].append(
                    "布设移动测速与语音提示装置，推动共享单车平台推送减速提醒。"
                )
            if young_male_ratio > 0.6:
                recommendations["education"].append(
                    "在高校与商圈周边面向18-30岁男性开展交通守法宣教。"
                )

        # 多部门协同建议
        if risk_level == "high":
            recommendations["multi_department"].extend([
                "联合城管：清理占道经营，优化非机动车道通行环境",
                "联动共享电单车企业：推送减速提醒，限制高风险区域投放",
                "协调交通设施管理部门：增设减速带、标识标牌",
            ])
        elif risk_level == "medium":
            recommendations["multi_department"].extend([
                "联动共享电单车企业：推送减速提醒",
                "协调交通设施管理部门：检查并优化设施配置",
            ])

        # 清理空建议
        for key in recommendations:
            recommendations[key] = [r for r in recommendations[key] if r]

        if not any(recommendations.values()):
            recommendations["police"].append("保持常态化巡查，跟踪该区域后续趋势。")

        return recommendations

    def _detect_evolution_pattern(self, hotspot: Dict) -> str:
        """检测演化模式（简化版）。"""
        risk_level = hotspot.get("risk_level", "low")
        gi_score = hotspot.get("gi_score", hotspot.get("gi_z", 0))
        if risk_level == "high" and gi_score >= 2.58:
            return "new_hotspot"  # 简化：假设为新增热点
        elif risk_level == "high":
            return "oscillating_hotspot"
        return "low_risk"

    def _select_template(self, risk_level: str, evolution_pattern: str) -> str:
        """选择策略模板。"""
        if evolution_pattern == "new_hotspot":
            return "new_hotspot"
        elif evolution_pattern == "oscillating_hotspot":
            return "oscillating_hotspot"
        elif risk_level == "high":
            return "high_risk"
        elif risk_level == "medium":
            return "medium_risk"
        else:
            return "low_risk"

    def _load_templates(self) -> Dict:
        """加载策略模板。"""
        with open(self.template_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_template(self, template_key: str, template: Dict):
        """保存策略模板。"""
        templates = self._load_templates()
        templates[template_key] = template
        with open(self.template_file, "w", encoding="utf-8") as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)

    def get_all_templates(self) -> Dict:
        """获取所有策略模板。"""
        return self._load_templates()


# 向后兼容的函数接口
def generate_recommendations(hotspot: Dict) -> List[str]:
    """向后兼容的简单接口。"""
    service = RecommendationService()
    recs = service.generate_recommendations(hotspot, use_template=False)
    result = []
    result.extend(recs["police"])
    result.extend(recs["facility"])
    result.extend(recs["education"])
    return result

