"""
风险分析服务（2.0）。

围绕 runtime_pipeline，将上传后的本地数据执行 Moran/Gi*、趋势
检验，并缓存为 GeoJSON/CSV/HTML。
"""
from typing import Any, Dict, Optional

from .runtime_pipeline import run_full_analysis, get_latest_summary


def execute_analysis(params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """触发一次完整分析。"""
    return run_full_analysis(params)


def latest_analysis_summary() -> Dict[str, Any]:
    """读取最近一次分析结果。"""
    return get_latest_summary()


