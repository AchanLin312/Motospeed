"""
指令化转译服务。

将算法分析结果转化为一线民警可执行的明确工作指令，
实现"算法输出 → 警务决策"的智能转译。
"""
from typing import Dict, Any, List, Optional
import json
from pathlib import Path


class InterpretationService:
    """分析结果指令化转译服务。"""

    def __init__(self):
        """初始化转译服务。"""
        self.output_dir = Path("outputs/runtime")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def interpret_analysis_results(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        将分析结果转译为警务指令。

        :param analysis_data: 分析结果数据
        :return: 包含解释和指令的字典
        """
        interpretations = {
            "indicators": {},
            "instructions": [],
            "recommendations": []
        }

        # 网格数量解释
        grid_count = analysis_data.get("grid_count", 0)
        interpretations["indicators"]["grid_count"] = {
            "value": grid_count,
            "explanation": f"分析区域被划分为 {grid_count} 个网格单元，网格数量代表分析区域的精细程度。网格越多，分析越细致，但计算时间也相应增加。",
            "instruction": f"当前分析覆盖 {grid_count} 个区域单元，建议重点关注热点集中的网格区域。"
        }

        # 热点数量解释
        hotspot_count = analysis_data.get("hotspot_count", 0)
        risk_level = "高" if hotspot_count > 10 else "中" if hotspot_count > 5 else "低"
        interpretations["indicators"]["hotspot_count"] = {
            "value": hotspot_count,
            "explanation": f"识别出 {hotspot_count} 个风险热点区域。热点数量反映当前超速行为的空间集中程度，数量越多表示风险分布越集中。",
            "instruction": f"发现 {hotspot_count} 个风险热点（风险等级：{risk_level}），建议立即开展重点区域巡查。",
            "alert_level": "red" if hotspot_count > 10 else "yellow" if hotspot_count > 5 else "blue"
        }

        # 全局Moran's I解释
        moran_i = analysis_data.get("global_moran", {}).get("moran_i")
        if moran_i is not None:
            if moran_i > 0.3:
                pattern = "高度集聚"
                strategy = "集中布控"
                instruction = f"空间自相关指数为 {moran_i:.3f}，表明超速行为呈{pattern}模式，建议采取{strategy}策略，重点加强热点区域的巡逻频次。"
            elif moran_i > 0.1:
                pattern = "中度集聚"
                strategy = "重点监控"
                instruction = f"空间自相关指数为 {moran_i:.3f}，表明超速行为呈{pattern}模式，建议采取{strategy}策略，对热点区域进行定期巡查。"
            elif moran_i > -0.1:
                pattern = "随机分布"
                strategy = "全域巡逻"
                instruction = f"空间自相关指数为 {moran_i:.3f}，表明超速行为呈{pattern}模式，建议采取{strategy}策略，均匀分配警力资源。"
            else:
                pattern = "分散分布"
                strategy = "分散布控"
                instruction = f"空间自相关指数为 {moran_i:.3f}，表明超速行为呈{pattern}模式，建议采取{strategy}策略，扩大巡查覆盖范围。"
            
            interpretations["indicators"]["global_moran"] = {
                "value": moran_i,
                "explanation": f"全局Moran's I指数为 {moran_i:.3f}。该指数反映空间自相关性：正值表示相似值聚集（热点集中），负值表示相异值聚集（分散分布），接近0表示随机分布。",
                "instruction": instruction,
                "pattern": pattern
            }

        # 趋势结果解释
        trend_data = analysis_data.get("trend", {})
        trend = trend_data.get("trend", "unknown")
        if trend == "increasing":
            trend_desc = "上升趋势"
            action = "加强治理"
            instruction = f"趋势分析显示超速行为呈{trend_desc}，风险正在上升，建议{action}，立即增派警力，开展专项整治行动。"
            alert_level = "red"
        elif trend == "decreasing":
            trend_desc = "下降趋势"
            action = "保持现有措施"
            instruction = f"趋势分析显示超速行为呈{trend_desc}，治理效果显著，建议{action}，继续维持当前勤务模式。"
            alert_level = "blue"
        elif trend == "no trend":
            trend_desc = "无明显趋势"
            action = "持续监控"
            instruction = f"趋势分析显示超速行为{trend_desc}，风险保持稳定，建议{action}，定期评估治理效果。"
            alert_level = "yellow"
        else:
            trend_desc = "未知趋势"
            action = "需要更多数据"
            instruction = f"趋势分析结果：{trend_desc}，建议{action}进行进一步分析。"
            alert_level = "yellow"

        interpretations["indicators"]["trend"] = {
            "value": trend,
            "explanation": f"趋势分析结果：{trend_desc}。该结果基于Mann-Kendall趋势检验，反映超速行为在时间维度上的变化方向。",
            "instruction": instruction,
            "alert_level": alert_level
        }

        # 生成分级指令
        instructions = []
        
        # 红色指令（紧急）
        if hotspot_count > 10 or (moran_i and moran_i > 0.3) or trend == "increasing":
            instructions.append({
                "level": "red",
                "title": "紧急处置指令",
                "content": f"发现 {hotspot_count} 个高风险热点区域，超速行为呈{'高度集聚' if moran_i and moran_i > 0.3 else '上升趋势'}，立即增派巡逻警力，开展专项整治。",
                "actions": [
                    "立即增派2-3组巡逻警力至热点区域",
                    "开展为期3天的专项整治行动",
                    "加强重点时段（早高峰7-9点、晚高峰17-19点）的巡查频次",
                    "协调交通设施管理部门优化信号灯配时"
                ],
                "priority": 1
            })

        # 黄色指令（预警）
        if 5 < hotspot_count <= 10 or (moran_i and 0.1 < moran_i <= 0.3) or trend == "no trend":
            instructions.append({
                "level": "yellow",
                "title": "预警监控指令",
                "content": f"发现 {hotspot_count} 个中风险热点区域，建议加强重点时段视频巡查和现场执法。",
                "actions": [
                    "加强重点时段视频巡查",
                    "安排1-2组警力进行定期巡查",
                    "对热点区域周边进行交通设施检查",
                    "开展交通安全宣传教育"
                ],
                "priority": 2
            })

        # 蓝色指令（常态）
        if hotspot_count <= 5 or trend == "decreasing":
            instructions.append({
                "level": "blue",
                "title": "常态管理指令",
                "content": f"当前风险水平较低（热点数量：{hotspot_count}），建议纳入日常重点巡逻线路，保持现有治理措施。",
                "actions": [
                    "将热点区域纳入日常重点巡逻线路",
                    "保持现有勤务模式和巡查频次",
                    "定期评估治理效果",
                    "建立风险监测机制"
                ],
                "priority": 3
            })

        interpretations["instructions"] = instructions

        # 生成策略建议
        recommendations = []
        
        if hotspot_count > 0:
            recommendations.append({
                "type": "巡逻策略",
                "content": f"针对 {hotspot_count} 个热点区域，建议采用'重点区域+周边辐射'的巡逻模式，早高峰（7-9点）和晚高峰（17-19点）各增加1-2组警力。",
                "implementation": "立即执行"
            })

        if moran_i and moran_i > 0.1:
            recommendations.append({
                "type": "设施优化",
                "content": "热点区域存在空间集聚特征，建议协调交通设施管理部门，优化信号灯配时，增设非机动车道标识，改善道路通行环境。",
                "implementation": "3-5个工作日内完成"
            })

        if trend == "increasing":
            recommendations.append({
                "type": "专项整治",
                "content": "超速行为呈上升趋势，建议开展为期一周的专项整治行动，重点查处热点区域的违法行为，形成有效震慑。",
                "implementation": "立即启动"
            })

        interpretations["recommendations"] = recommendations

        return interpretations

    def generate_instruction_report(self, analysis_data: Dict[str, Any]) -> str:
        """
        生成指令化报告文本。

        :param analysis_data: 分析结果数据
        :return: 报告文本
        """
        interpretations = self.interpret_analysis_results(analysis_data)
        
        report_lines = [
            "=" * 60,
            "警务决策指令报告",
            "=" * 60,
            ""
        ]

        # 指标解读
        report_lines.append("【核心指标解读】")
        report_lines.append("")
        
        for key, info in interpretations["indicators"].items():
            report_lines.append(f"• {key.replace('_', ' ').title()}: {info['value']}")
            report_lines.append(f"  解释：{info['explanation']}")
            report_lines.append(f"  指令：{info['instruction']}")
            report_lines.append("")

        # 分级指令
        report_lines.append("【分级处置指令】")
        report_lines.append("")
        
        for inst in sorted(interpretations["instructions"], key=lambda x: x["priority"]):
            level_name = {"red": "红色（紧急）", "yellow": "黄色（预警）", "blue": "蓝色（常态）"}[inst["level"]]
            report_lines.append(f"【{level_name}】{inst['title']}")
            report_lines.append(f"  {inst['content']}")
            report_lines.append("  具体行动：")
            for action in inst["actions"]:
                report_lines.append(f"    - {action}")
            report_lines.append("")

        # 策略建议
        report_lines.append("【策略建议】")
        report_lines.append("")
        
        for rec in interpretations["recommendations"]:
            report_lines.append(f"• {rec['type']}：{rec['content']}")
            report_lines.append(f"  实施时间：{rec['implementation']}")
            report_lines.append("")

        return "\n".join(report_lines)

    def save_interpretations(self, analysis_data: Dict[str, Any]) -> Path:
        """
        保存转译结果到文件。

        :param analysis_data: 分析结果数据
        :return: 保存的文件路径
        """
        interpretations = self.interpret_analysis_results(analysis_data)
        report_text = self.generate_instruction_report(analysis_data)
        
        # 保存JSON格式
        json_file = self.output_dir / "interpretations.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(interpretations, f, ensure_ascii=False, indent=2)
        
        # 保存文本报告
        txt_file = self.output_dir / "instruction_report.txt"
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(report_text)
        
        return json_file


# 全局实例
interpretation_service = InterpretationService()

