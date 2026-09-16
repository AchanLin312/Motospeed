"""
Mann-Kendall 趋势分析。

应用于论文 3.2.2 节的时空演化模式识别。
"""
from typing import Dict

import numpy as np

try:
    from pymannkendall import original_test
except Exception:  # pragma: no cover
    # 某些冻结/打包环境会在导入可选依赖时抛出非 ImportError。
    original_test = None


def mann_kendall_trend(series) -> Dict:
    """
    对时间序列执行 Mann-Kendall 检验。
    :param series: pandas.Series 或 list
    """
    if original_test is None:
        values = np.asarray(series, dtype=float)
        if len(values) < 2:
            return {"trend": "no trend", "h": False, "p": 1.0, "z": 0.0, "tau": 0.0}
        diff = np.diff(values)
        slope = np.nanmean(diff)
        trend = "increasing" if slope > 0 else "decreasing" if slope < 0 else "no trend"
        return {"trend": trend, "h": False, "p": 1.0, "z": slope, "tau": 0.0}

    result = original_test(series)
    return {
        "trend": result.trend,
        "h": result.h,
        "p": result.p,
        "z": result.z,
        "tau": result.Tau,
    }

