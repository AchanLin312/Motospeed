"""M3 熵权+TOPSIS 综合评分服务（CRI = Comprehensive Risk Index）。

验收对照：
- AC16 熵权法：三项事件率 → 权重，权重和 = 1；同一分析版本缓存不重算
- AC17 CRI 0-100 + 三类危险指数 0-100；急变速样本不足时综合指数不可用（留空，不记 0）

方法：
- 质量门控：仅 quality_flag=valid 的网格（暴露≥1km 且子链≥5）参与定权与
  评分；低暴露网格的率值视为"无数据"（留空而非 0），防止分母爆炸的统计
  噪声（如 5m 暴露 3 起事件 → 6 万次/100km）污染权重与理想解。
- 熵权：正向指标 p_ij = x_ij / Σ_j x_ij，e_j = -1/ln(n)·Σ p·ln p，
  差异系数 d_j = 1 - e_j，权重 w_j = d_j / Σd。列无差异（常数/全零）→ d=0 → w=0。
- TOPSIS：向量归一 → 加权 → 正/负理想解 → 相对接近度 closeness，CRI = closeness×100。
- 三类危险指数：该类事件率列 max 归一 ×100（max=0 → 全 0）。
- 急变速可用性：behavior_meta.json 的 n_motion_samples < RAPID_MIN_SAMPLES 时
  rapid_rate 视为不可用（按常数列处理，权重归 0），CRI 列留空不记 0。

输出：改写 grid_metrics.csv（增列 cri/三指数/cri_available）+ weights.json
"""
from __future__ import annotations

import json
import math
from datetime import datetime

import numpy as np
import pandas as pd

from . import RULE_VERSION, analysis_dir

INDICATORS = ("overspeed_rate", "reverse_rate", "rapid_rate")
RAPID_MIN_SAMPLES = 30   # 急变速可信运动样本下限（低于此 rapid 指标不可用）


def _entropy_weights(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """熵权法。返回 (weights, entropy, diff_coeff)。"""
    n, m = X.shape
    entropy = np.ones(m)
    for j in range(m):
        col = X[:, j].astype(float)
        s = col.sum()
        if s <= 0 or n < 2 or np.all(col == col[0]):
            continue                     # 全零 / 常数列：e=1 → d=0 → w=0
        p = col / s
        nz = p[p > 0]
        entropy[j] = -float((nz * np.log(nz)).sum()) / math.log(n)
    diff = 1.0 - entropy
    total = diff.sum()
    weights = diff / total if total > 0 else np.full(m, 1.0 / m)
    return weights, entropy, diff


def _topsis(X: np.ndarray, w: np.ndarray) -> np.ndarray:
    """TOPSIS 相对接近度（0~1）。全零行（分母为 0）记 0。"""
    norm = np.sqrt((X.astype(float) ** 2).sum(axis=0))
    norm[norm == 0] = 1.0
    v = X / norm * w
    vp, vm = v.max(axis=0), v.min(axis=0)
    dp = np.sqrt(((v - vp) ** 2).sum(axis=1))
    dm = np.sqrt(((v - vm) ** 2).sum(axis=1))
    denom = dp + dm
    return np.where(denom > 0, dm / np.where(denom > 0, denom, 1.0), 0.0)


def _index_0_100(col: np.ndarray) -> np.ndarray:
    """单类危险指数：max 归一 ×100（max=0 → 全 0）。"""
    mx = float(np.nanmax(col)) if len(col) else 0.0
    return np.round(col / mx * 100, 1) if mx > 0 else np.zeros(len(col))


def run_scoring(analysis_version: str, force: bool = False) -> dict:
    """对分析版本执行熵权+TOPSIS 评分，结果写回 grid_metrics.csv 与 weights.json。"""
    adir = analysis_dir(analysis_version)
    wpath = adir / "weights.json"
    if wpath.exists() and not force:          # AC16：同版本缓存不重算
        return json.loads(wpath.read_text(encoding="utf-8"))

    gpath = adir / "grid_metrics.csv"
    if not gpath.exists():
        raise FileNotFoundError("缺少 grid_metrics.csv，请先执行网格聚合")
    df = pd.read_csv(gpath, encoding="utf-8-sig", dtype={"grid_id": str})

    # 急变速可用性（AC17）
    rapid_available, n_motion = True, None
    bpath = adir / "behavior_meta.json"
    if bpath.exists():
        bm = json.loads(bpath.read_text(encoding="utf-8"))
        th = bm.get("accel_thresholds") or {}
        n_motion = th.get("n_motion_samples")
        if n_motion is not None and int(n_motion) < RAPID_MIN_SAMPLES:
            rapid_available = False

    # 质量过滤：仅有效网格（暴露≥1km 且子链≥5）参与定权与评分。
    # 低暴露网格的率值为统计噪声（如 5m 暴露 3 起事件 → 6 万次/100km），
    # 视为"无数据"而非 0，避免污染熵权与理想解。
    if "quality_flag" in df.columns:
        valid_mask = df["quality_flag"].eq("valid")
    else:                       # 兼容旧版 grid_metrics.csv
        valid_mask = pd.Series(True, index=df.index)
    n_valid_grids = int(valid_mask.sum())

    # 率值列不在全表上 fillna(0)：低暴露网格的空率值需保持"空"原样回写
    # CSV（无数据语义），仅在构造 X 时对 valid 行做数值化兜底。
    X = (df.loc[valid_mask, list(INDICATORS)]
           .apply(pd.to_numeric, errors="coerce").fillna(0.0)
           .to_numpy(float))
    if not rapid_available:
        X[:, INDICATORS.index("rapid_rate")] = 0.0   # 常数列 → 权重 0

    if n_valid_grids >= 2:
        weights, entropy, diff = _entropy_weights(X)
        closeness = _topsis(X, weights)
    else:
        # 有效网格不足，无法定权：CRI/指数整体不可用
        weights = np.full(len(INDICATORS), np.nan)
        entropy = np.full(len(INDICATORS), np.nan)
        diff = np.full(len(INDICATORS), np.nan)
        closeness = None

    scoring_available = closeness is not None
    if scoring_available:
        idx = df.index[valid_mask]
        df.loc[idx, "overspeed_index"] = _index_0_100(X[:, 0])
        df.loc[idx, "reverse_index"] = _index_0_100(X[:, 1])
        df.loc[idx, "rapid_index"] = _index_0_100(X[:, 2])
        if rapid_available:
            df.loc[idx, "cri"] = np.round(closeness * 100, 1)
        else:
            df.loc[idx, "cri"] = np.nan
    else:
        df["overspeed_index"] = np.nan
        df["reverse_index"] = np.nan
        df["rapid_index"] = np.nan
        df["cri"] = np.nan
    # 非 valid 网格：无数据（留空，不记 0）
    df.loc[~valid_mask, ["overspeed_index", "reverse_index",
                         "rapid_index", "cri"]] = np.nan
    df["cri_available"] = bool(rapid_available and scoring_available)
    df.to_csv(gpath, index=False, encoding="utf-8-sig")

    meta = {
        "analysis_version": analysis_version,
        "rule_version": RULE_VERSION,
        "method": "entropy-weight + TOPSIS (vector normalization)",
        "indicators": list(INDICATORS),
        "n_valid_grids": n_valid_grids,
        "n_grids_total": int(len(df)),
        "entropy": [round(float(e), 6) for e in entropy],
        "diff_coeff": [round(float(d), 6) for d in diff],
        "weights": {k: round(float(w), 6)
                    for k, w in zip(INDICATORS, weights)},
        "weight_sum": round(float(weights.sum()), 6),
        "rapid_available": rapid_available,
        "n_motion_samples": n_motion,
        "rapid_min_samples": RAPID_MIN_SAMPLES,
        "cri_scale": "0-100 (closeness x 100)",
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }
    wpath.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return meta


# ---------------------------------------------------------------- 边界自测

def _selftest() -> None:
    # 组A：全零列 / 常数列权重为 0，权重和 = 1
    X = np.array([
        [10.0, 0.0, 5.0],
        [20.0, 0.0, 5.0],
        [30.0, 0.0, 5.0],
        [40.0, 0.0, 5.0],
    ])
    w, e, d = _entropy_weights(X)
    assert abs(w.sum() - 1.0) < 1e-9, "组A失败：权重和≠1"
    assert w[1] == 0.0 and w[2] == 0.0, f"组A失败：常数列权重应为0 got {w}"
    assert w[0] > 0.99, f"组A失败：唯一有效列权重应≈1 got {w}"

    # 组B：TOPSIS 全零行 closeness=0；最大行 closeness 最高
    cl = _topsis(X, np.array([1 / 3, 1 / 3, 1 / 3]))
    assert cl[0] < cl[1] < cl[2] < cl[3], f"组B失败：单调性 {cl}"

    # 组C：单行数据（n=1）不崩溃，熵权均分
    w1, _, _ = _entropy_weights(np.array([[3.0, 1.0, 2.0]]))
    assert abs(w1.sum() - 1.0) < 1e-9, "组C失败"

    # 组D：rapid 不可用 → rapid 列置 0 后权重为 0，CRI 不受污染
    Xd = X.copy()
    Xd[:, 2] = 0.0
    wd, _, _ = _entropy_weights(Xd)
    assert wd[2] == 0.0, f"组D失败：rapid权重应0 got {wd}"

    # 组E：指数归一边界 —— 全零列指数全 0；最大值行指数 100
    assert _index_0_100(np.zeros(3)).max() == 0.0, "组E失败：全零列"
    ix = _index_0_100(X[:, 0])
    assert ix[-1] == 100.0 and ix[0] == 25.0, f"组E失败：归一 {ix}"

    print("scoring 自测 5 组通过 ✓ (熵权/常数列/TOPSIS单调/rapid不可用/指数归一)")


if __name__ == "__main__":
    _selftest()
