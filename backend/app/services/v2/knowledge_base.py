"""M6 治理知识库（手册 13 章）。

- 初始资产 kb_data/KB-1.0.json，首次调用 bootstrap() 复制到
  outputs/runtime/v2/knowledge_base/（13.3 版本化：新版本不覆盖旧版本）
- match_rules() 按网格指标 + 热点上下文匹配触发规则，返回规则全文
- 每条 AI 建议保存实际使用的 rule_id + basis_id（AC23）

触发条件映射（手册 13.1 "触发条件" 列 → 本项目数据字段）：
    KB-G01  综合指数高且 Gi* 显著        → comprehensive 图层 gi_z>=1.65 且 cri>=P75
    KB-G02  三类中至少两类指数较高       → 三类指数中 >=2 个达到全网格 P75
    KB-S01  超速指数为三类最高           → overspeed_index 为三者最大
    KB-S02  事件持续时间或超阈幅度较高   → 网格级无幅度数据，以 overspeed_count 高频近似
    KB-R01  单向路疑似逆行占比较高       → 逆行主导 且 网格内逆行事件 oneway(F/T) 占比>=0.5
    KB-R02  双向路疑似逆行占比较高       → 逆行主导 且 其余（双向 B / 无 oneway 数据）
    KB-A01  急加速明显多于急减速         → rapid 主导 且 accel/decel >= 1.5
    KB-A02  急减速明显多于急加速         → rapid 主导 且 decel/accel >= 1.5
    KB-A03  急加速和急减速均高           → rapid 主导 且 其余情形
    KB-E01  外卖风险集中且重复出现       → vehicle_count>=3 且 total_events>=5
    KB-E02  任一风险达到高等级           → 任一指数 >= P90 或热点 risk_level=="high"
    KB-D01  有效里程或轨迹数不足         → quality_flag != valid
    KB-D02  selection_type 兜底网格      → 任一图层 selection_type==top_risk_fallback
    KB-Q01  急变速可判定比例低           → 网格级无判定率数据，以 insufficient_data 近似
    KB-F01  已形成治理建议               → 恒触发（生成建议即成立）
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import V2_DIR

KB_DIR = V2_DIR / "knowledge_base"          # 运行时知识库版本目录
KB_DATA_DIR = Path(__file__).parent / "kb_data"   # 初始资产（随代码交付）

GI_SIGNIFICANT_Z = 1.65     # α=0.10 显著（与热点图层 Z 分级一致）
DOMINANT_RATIO = 1.5        # A01/A02 "明显多于" 判定比例


def bootstrap() -> None:
    """KB_DIR 为空时导入初始版本 KB-1.0（幂等）。"""
    KB_DIR.mkdir(parents=True, exist_ok=True)
    for src in sorted(KB_DATA_DIR.glob("KB-*.json")):
        dst = KB_DIR / src.name
        if not dst.exists():
            shutil.copy2(src, dst)


def list_versions() -> list[str]:
    bootstrap()
    return sorted(p.stem for p in KB_DIR.glob("KB-*.json"))


def latest_version() -> str:
    versions = list_versions()
    if not versions:
        raise FileNotFoundError("知识库为空，请检查 kb_data 资产")
    return versions[-1]


def load(version: str | None = None) -> dict:
    """加载知识库版本 {"version", "rules", "basis"}；缺省取最新。"""
    v = version or latest_version()
    path = KB_DIR / f"{v}.json"
    if not path.exists():
        raise FileNotFoundError(f"知识库版本不存在: {v}")
    return json.loads(path.read_text(encoding="utf-8"))


def get_rules(version: str | None = None,
              enabled_only: bool = True) -> list[dict]:
    kb = load(version)
    rules = kb.get("rules", [])
    if enabled_only:
        rules = [r for r in rules if r.get("enabled", True)]
    return rules


def get_basis(version: str | None = None) -> dict:
    return load(version).get("basis", {})


# ---------------------------------------------------------------------------
# 规则匹配
# ---------------------------------------------------------------------------

def _pctl(values: list[float], q: float) -> float:
    """简单分位数（0-1），空值返回 0。"""
    vs = sorted(v for v in values if v is not None)
    if not vs:
        return 0.0
    k = (len(vs) - 1) * q
    f, c = int(k), min(int(k) + 1, len(vs) - 1)
    return vs[f] + (vs[c] - vs[f]) * (k - f)


def _num(row: dict, key: str) -> float:
    v = row.get(key)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def match_rules(grid_row: dict, ctx: dict,
                version: str | None = None) -> list[dict]:
    """匹配该网格触发的知识库规则。

    参数：
        grid_row: grid_metrics.csv 单行（dict，含 quality_flag/三类计数与率）
        ctx: 上下文 {"hotspots": {layer: {gi_z, selection_type, risk_level}},
                      "reverse_oneway_ratio": float|None,
                      "index_p75"/"index_p90": {行为: 阈值}}
    返回：按 priority 升序的规则全文列表（dict）。
    """
    rules = get_rules(version)
    by_id = {r["rule_id"]: r for r in rules}

    idx = {k: _num(grid_row, f"{k}_index")
           for k in ("overspeed", "reverse", "rapid")}
    p75 = ctx.get("index_p75") or {k: 0.0 for k in idx}
    p90 = ctx.get("index_p90") or {k: 0.0 for k in idx}
    pos_idx = {k: v for k, v in idx.items() if v > 0}

    hotspot = ctx.get("hotspots") or {}
    comp = hotspot.get("comprehensive") or {}
    quality = str(grid_row.get("quality_flag") or "valid")
    acc = _num(grid_row, "rapid_accel_count")
    dec = _num(grid_row, "rapid_decel_count")

    dominant = max(pos_idx, key=pos_idx.get) if pos_idx else None
    n_high = sum(1 for k in idx if idx[k] > 0 and idx[k] >= p75.get(k, 0.0))
    oneway_ratio = ctx.get("reverse_oneway_ratio")

    hit: set[str] = set()

    # KB-G01 综合：指数高 + Gi* 显著
    gi_z = comp.get("gi_z")
    if gi_z is not None and gi_z >= GI_SIGNIFICANT_Z and \
            idx["overspeed"] + idx["reverse"] + idx["rapid"] > 0 and \
            _num(grid_row, "cri") >= ctx.get("cri_p75", 0.0):
        hit.add("KB-G01")

    # KB-G02 混合风险：三类中至少两类较高
    if n_high >= 2:
        hit.add("KB-G02")

    # KB-S01 超速主导；KB-S02 持续超速（事件数高频近似）
    if dominant == "overspeed":
        hit.add("KB-S01")
    if _num(grid_row, "overspeed_count") >= 10:
        hit.add("KB-S02")

    # KB-R01/R02 逆行主导，按网格内逆行事件的单向构成细分
    if dominant == "reverse":
        if oneway_ratio is not None and oneway_ratio >= 0.5:
            hit.add("KB-R01")
        else:
            hit.add("KB-R02")

    # KB-A01/A02/A03 急变速主导，按加减速构成细分
    if dominant == "rapid":
        if acc > 0 and dec > 0:
            r1, r2 = max(acc, dec) / min(acc, dec), None
            if r1 >= DOMINANT_RATIO:
                hit.add("KB-A01" if acc > dec else "KB-A02")
            else:
                hit.add("KB-A03")          # 两者相近：均高
        elif acc > 0:
            hit.add("KB-A01")
        elif dec > 0:
            hit.add("KB-A02")

    # KB-E01 外卖平台协同：风险集中且重复出现
    if _num(grid_row, "vehicle_count") >= 3 and _num(grid_row, "total_events") >= 5:
        hit.add("KB-E01")

    # KB-E02 教育培训：任一风险达到高等级
    if any(idx[k] >= p90.get(k, 0.0) and idx[k] > 0 for k in idx) or \
            any((h or {}).get("risk_level") == "high" for h in hotspot.values()):
        hit.add("KB-E02")

    # KB-D01 低暴露量
    if quality != "valid":
        hit.add("KB-D01")

    # KB-D02 非显著兜底网格
    if any((h or {}).get("selection_type") == "top_risk_fallback"
           for h in hotspot.values()):
        hit.add("KB-D02")

    # KB-Q01 数据质量不足（急变速可判定比例低的网格级近似）
    if quality == "insufficient_data":
        hit.add("KB-Q01")

    # KB-F01 效果复核：已形成治理建议 → 恒触发
    hit.add("KB-F01")

    matched = [by_id[rid] for rid in sorted(hit) if rid in by_id]
    matched.sort(key=lambda r: r.get("priority", 99))
    return matched
