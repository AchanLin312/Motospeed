"""
指令化转译相关 API。

v4.0 新增：将分析结果转化为一线民警可执行的明确工作指令。
"""
from flask import Blueprint, jsonify, request

from ..services.interpretation_service import interpretation_service
from ..services.runtime_pipeline import get_latest_summary

interpretation_bp = Blueprint("interpretation", __name__)


@interpretation_bp.get("")
@interpretation_bp.get("/latest")
def get_latest_interpretation():
    """获取最新分析结果的指令化转译。"""
    try:
        # 加载最新分析结果
        analysis_data = get_latest_summary()
        if not analysis_data:
            return jsonify({"error": "暂无分析结果"}), 404

        # 生成转译结果
        interpretations = interpretation_service.interpret_analysis_results(analysis_data)
        
        return jsonify({
            "success": True,
            "interpretations": interpretations
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@interpretation_bp.post("/generate")
def generate_interpretation():
    """基于分析结果生成指令化转译。"""
    try:
        analysis_data = request.get_json()
        if not analysis_data:
            # 如果没有提供数据，使用最新分析结果
            analysis_data = get_latest_summary()
            if not analysis_data:
                return jsonify({"error": "请提供分析结果或先执行分析"}), 400

        # 生成转译结果
        interpretations = interpretation_service.interpret_analysis_results(analysis_data)
        
        # 保存转译结果
        saved_path = interpretation_service.save_interpretations(analysis_data)
        
        return jsonify({
            "success": True,
            "interpretations": interpretations,
            "saved_path": str(saved_path)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@interpretation_bp.get("/report")
def get_instruction_report():
    """获取指令化报告文本。"""
    try:
        analysis_data = get_latest_summary()
        if not analysis_data:
            return jsonify({"error": "暂无分析结果"}), 404

        report_text = interpretation_service.generate_instruction_report(analysis_data)
        
        return jsonify({
            "success": True,
            "report": report_text
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

