"""M6 AI 治理建议服务：RAG 编排 + 缓存 + 白名单 + 兜底（手册 12 章）。

流程（generate_advice）：
    1. 缓存命中（相同缓存键）→ 不重复调用 LLM（AC21）
    2. 读 grid_metrics 网格行 → 热点图层上下文 → 知识库规则匹配
    3. 按白名单构造外发 payload（AC22，禁止车辆/设备标识、逐点坐标、原始轨迹）
    4. LLM 可用 → OpenAI 兼容调用（45s 超时）→ 结构校验 → 一次自动修复
       不可用/超时/校验失败 → 本地规则模板兜底（AC24）
    5. 落盘 analysis/<av>/advice/<grid_id>.json，保存 rule_id + basis_id（AC23）

缓存键（12.2）：analysis_version + grid_id + risk_layer + knowledge_base_version
              + prompt_version + model_name 的 SHA-256。
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import analysis_dir, batch_dir
from . import knowledge_base as kb
from . import llm_provider

log = logging.getLogger("v2.advice")

PROMPT_VERSION = "P-1.0"

ADVICE_SECTIONS = ("risk_summary", "field_actions", "road_environment_checks",
                   "platform_coordination", "education_actions", "verification")

# 兜底模板：规则 → 输出部分的映射（12.4 六部分）
_SECTION_OF_RULE = {
    "KB-G01": "field_actions", "KB-G02": "field_actions",
    "KB-S01": "field_actions", "KB-S02": "field_actions",
    "KB-R01": "field_actions", "KB-A01": "field_actions",
    "KB-R02": "road_environment_checks", "KB-A02": "road_environment_checks",
    "KB-A03": "road_environment_checks",
    "KB-E01": "platform_coordination",
    "KB-E02": "education_actions",
    "KB-F01": "verification", "KB-D01": "verification",
    "KB-D02": "verification", "KB-Q01": "verification",
}
_DEFAULT_SENTENCE = {
    "field_actions": "早高峰在事件集中位置安排现场观察，记录主要风险行为与流向。",
    "road_environment_checks": "现场核查标志标线、通行空间与视距等道路环境问题。",
    "platform_coordination": "结合风险情况与配送企业沟通安全提醒与培训安排。",
    "education_actions": "围绕主导风险行为对骑手开展针对性安全提示。",
    "verification": "保留本次指标与热点结果，取得可比数据后按相同参数复算复核。",
}

_BEHAVIOR_LABEL = {"overspeed": "超速", "reverse": "疑似逆行", "rapid": "急变速"}


# ---------------------------------------------------------------------------
# 上下文读取
# ---------------------------------------------------------------------------

def _load_metrics(adir: Path, grid_id: str) -> tuple[dict, pd.DataFrame]:
    gpath = adir / "grid_metrics.csv"
    if not gpath.exists():
        raise FileNotFoundError("缺少 grid_metrics.csv，请先完成网格聚合与评分")
    df = pd.read_csv(gpath, encoding="utf-8-sig", dtype={"grid_id": str})
    row = df[df["grid_id"] == grid_id]
    if row.empty:
        raise KeyError(f"网格不存在: {grid_id}")
    return row.iloc[0].to_dict(), df


def _index_series(df: pd.DataFrame, behavior: str) -> pd.Series:
    """三类指数：优先 scoring 写回的 *_index，缺失时用事件率近似。"""
    for col in (f"{behavior}_index", f"{behavior}_rate"):
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=df.index)


def _hotspot_context(adir: Path, grid_id: str) -> dict:
    """该网格在四图层中的 {gi_z, selection_type, risk_level} 上下文。"""
    ctx: dict[str, dict] = {}
    hdir = adir / "hotspots"
    for gj in sorted(hdir.glob("*.geojson")) if hdir.exists() else []:
        layer = gj.stem
        try:
            data = json.loads(gj.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for f in data.get("features", []):
            props = f.get("properties") or {}
            if props.get("grid_id") == grid_id:
                ctx[layer] = {
                    "gi_z": props.get("gi_z"),
                    "selection_type": props.get("selection_type"),
                    "risk_level": props.get("risk_level"),
                }
                break
    return ctx


def _reverse_oneway_ratio(adir: Path, grid_row: dict) -> float | None:
    """该网格内逆行事件中单向路（oneway F/T）占比（KB-R01/R02 细分）。"""
    epath = adir / "events.csv"
    if not epath.exists():
        return None
    try:
        ev = pd.read_csv(epath, encoding="utf-8-sig", usecols=["event_type", "lon", "lat", "oneway"])
    except (ValueError, pd.errors.ParserError):
        return None
    ev = ev[ev["event_type"] == "reverse"]
    if ev.empty:
        return None
    lon, lat = grid_row.get("center_lon"), grid_row.get("center_lat")
    ev = ev[(ev["lon"].between(lon - 0.0016, lon + 0.0016)) &
            (ev["lat"].between(lat - 0.0012, lat + 0.0012))]
    if ev.empty:
        return None
    oneway = ev["oneway"].astype(str).str.upper()
    return float(oneway.isin(["F", "T"]).mean())


def _period(adir: Path) -> str:
    """数据时间范围（批次真实时间窗，不编造）。"""
    try:
        mm = json.loads((adir / "match_meta.json").read_text(encoding="utf-8"))
        bm = json.loads((batch_dir(mm["batch_id"]) / "meta.json").read_text(encoding="utf-8"))
        return f"{bm.get('time_start')}/{bm.get('time_end')}"
    except (OSError, KeyError, json.JSONDecodeError):
        return "未知时间范围"


# ---------------------------------------------------------------------------
# 白名单 payload（12.3 / AC22）
# ---------------------------------------------------------------------------

def _whitelist_payload(grid: dict, hotspot_ctx: dict, risk_layer: str,
                       period: str, rule_ids: list[str]) -> dict:
    """按白名单逐字段构造外发请求（不得序列化整个对象/原始行）。"""
    def _idx(behavior: str) -> float:
        v = grid.get(f"{behavior}_index")
        try:
            return round(float(v), 1)
        except (TypeError, ValueError):
            return 0.0

    def _events(behavior: str) -> int:
        col = {"rapid": "rapid_count"}.get(behavior, f"{behavior}_count")
        try:
            return int(grid.get(col) or 0)
        except (TypeError, ValueError):
            return 0

    def _rate(behavior: str) -> float | None:
        v = grid.get(f"{behavior}_rate")
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return None

    # 低精度位置摘要：网格中心保留 3 位小数（约百米级，非逐点坐标）
    loc = {"lat": round(float(grid.get("center_lat") or 0), 3),
           "lon": round(float(grid.get("center_lon") or 0), 3)}
    layer_hit = hotspot_ctx.get(risk_layer) or {}
    risk_level = layer_hit.get("risk_level") or "unknown"
    return {
        "analysis_version": grid.get("analysis_version"),
        "grid_id": grid.get("grid_id"),
        "period": period,
        "risk_level": risk_level,
        "selection_type": layer_hit.get("selection_type") or "statistical_hotspot",
        "composite_risk_index": _idx("composite") if "composite_index" in grid else
        (None if pd.isna(grid.get("cri")) else round(float(grid.get("cri")), 1)),
        "indicators": {
            "overspeed": {"index": _idx("overspeed"),
                          "events": _events("overspeed"),
                          "rate_per_100km": _rate("overspeed")},
            "suspected_reverse": {"index": _idx("reverse"),
                                  "events": _events("reverse"),
                                  "rate_per_100km": _rate("reverse")},
            "rapid_speed_change": {"index": _idx("rapid"),
                                   "events": _events("rapid"),
                                   "rate_per_100km": _rate("rapid")},
        },
        "exposure": {
            "distance_km": round(float(grid.get("exposure_km") or 0), 2),
            "trajectory_segments": int(grid.get("segment_count") or 0),
        },
        "location_hint": loc,
        "retrieved_rules": rule_ids,
    }


# ---------------------------------------------------------------------------
# 本地规则模板兜底（12.2 / AC24）
# ---------------------------------------------------------------------------

def _fallback_advice(grid: dict, rules: list[dict]) -> dict:
    """由触发规则模板按六部分组装本地建议。"""
    idx = {k: grid.get(f"{k}_index") or 0 for k in ("overspeed", "reverse", "rapid")}
    pos = {k: float(v) for k, v in idx.items() if v}
    dominant = _BEHAVIOR_LABEL.get(max(pos, key=pos.get), "综合风险") if pos else "综合风险"
    sections = {k: [] for k in ADVICE_SECTIONS if k != "risk_summary"}
    for r in rules:
        key = _SECTION_OF_RULE.get(r["rule_id"], "field_actions")
        sections[key].append(r["action_text"])
    for key, sentence in _DEFAULT_SENTENCE.items():
        if not sections[key]:
            sections[key].append(sentence)
    caution_note = "；".join(dict.fromkeys(
        r["caution"] for r in rules if r.get("caution")))
    return {
        "risk_summary": (
            f"该网格当前主要由{dominant}风险驱动，"
            f"综合风险指数 {round(float(grid.get('cri') or 0), 1)}。"
            "本建议由本地知识库规则模板生成。"),
        **sections,
        "basis_ids": list(dict.fromkeys(
            r["basis_id"] for r in rules if r.get("basis_id"))),
        "caution_note": caution_note,
    }


# ---------------------------------------------------------------------------
# 提示词组装
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """你是交通安全治理辅助助手，基于网格风险指标和治理知识库生成治理建议。
必须遵守：
1. 不得把疑似逆行写成已确认违法，不得把急变速直接写成事故或违法。
2. 不得根据轨迹分析建议处罚某个车辆或人员。
3. 建议仅限当前数据支持的单日早高峰场景，不得声称全天或长期趋势。
4. 知识库没有依据时说明需现场核实，不得编造法规条款、事故数据、路口设施或警力配置。
5. 只输出一个 JSON 对象，字段为：
   risk_summary（字符串，1-3句话）、field_actions、road_environment_checks、
   platform_coordination、education_actions、verification（均为字符串数组，
   不得虚构警力数量）、basis_ids（字符串数组，只准使用给定知识库条目编号）。"""


def _build_user_prompt(payload: dict, rules: list[dict], basis: dict) -> str:
    rule_lines = [
        f"- {r['rule_id']} {r['title']}（依据 {r['basis_id']}，注意：{r['caution']}）："
        f"触发条件[{r['risk_condition']}]；建议[{r['action_text']}]"
        for r in rules]
    used_basis_ids = {r["basis_id"] for r in rules if r.get("basis_id")}
    basis_lines = [
        f"- {bid} {b['name']}：{b['content']}"
        for bid, b in basis.items() if bid in used_basis_ids]
    return (
        "网格汇总数据（白名单内）：\n"
        + json.dumps(payload, ensure_ascii=False, indent=1)
        + "\n\n知识库触发规则：\n" + "\n".join(rule_lines)
        + "\n\n可用依据条款（basis_ids 只能从中选取）：\n" + "\n".join(basis_lines)
        + "\n\n请生成治理建议 JSON（六部分 + basis_ids），内容必须基于上述规则与数据。")


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def _cache_key(analysis_version: str, grid_id: str, risk_layer: str,
               kb_version: str, model_name: str) -> str:
    raw = "|".join((analysis_version, grid_id, risk_layer, kb_version,
                    PROMPT_VERSION, model_name))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _default_risk_layer(hotspot_ctx: dict) -> str:
    """用户未指定图层时，取该网格 Gi* 最显著的图层；否则 none。"""
    best, best_z = "none", None
    for layer, hit in hotspot_ctx.items():
        z = hit.get("gi_z")
        if z is not None and (best_z is None or z > best_z):
            best, best_z = layer, z
    return best


def _advice_path(adir: Path, grid_id: str) -> Path:
    return adir / "advice" / f"{grid_id}.json"


def generate_advice(analysis_version: str, grid_id: str,
                    risk_layer: str | None = None, force: bool = False) -> dict:
    """生成（或读取缓存）某网格的治理建议。抛 FileNotFoundError/KeyError 由路由转换。"""
    adir = analysis_dir(analysis_version)
    grid, df = _load_metrics(adir, grid_id)
    grid["analysis_version"] = analysis_version

    hotspot_ctx = _hotspot_context(adir, grid_id)
    layer = risk_layer or _default_risk_layer(hotspot_ctx)

    cfg = llm_provider.llm_config()
    model_name = cfg["model"] or "rule_fallback"
    kb_version = kb.latest_version()
    ckey = _cache_key(analysis_version, grid_id, layer, kb_version, model_name)

    # AC21：相同缓存键直接返回，不重复调用
    path = _advice_path(adir, grid_id)
    if path.exists() and not force:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("cache_key") == ckey:
            cached["cached"] = True
            return cached

    # 上下文与规则匹配
    index_p75 = {b: round(float(_index_series(df, b).quantile(0.75)), 4)
                 for b in ("overspeed", "reverse", "rapid")}
    index_p90 = {b: round(float(_index_series(df, b).quantile(0.90)), 4)
                 for b in ("overspeed", "reverse", "rapid")}
    ctx = {
        "hotspots": hotspot_ctx,
        "reverse_oneway_ratio": _reverse_oneway_ratio(adir, grid),
        "index_p75": index_p75, "index_p90": index_p90,
        "cri_p75": round(float(pd.to_numeric(df.get("cri"), errors="coerce")
                               .fillna(0.0).quantile(0.75)), 4) if "cri" in df else 0.0,
    }
    rules = kb.match_rules(grid, ctx, version=kb_version)
    basis = kb.get_basis(kb_version)

    period = _period(adir)
    payload = _whitelist_payload(grid, hotspot_ctx, layer, period,
                                 [r["rule_id"] for r in rules])

    # LLM 调用 → 校验 → 一次修复 → 兜底
    source, llm_status = "rule_fallback", "unavailable"
    advice = None
    if cfg["configured"]:
        fallback = _fallback_advice(grid, rules)
        obj = llm_provider.chat_json(
            _SYSTEM_PROMPT, _build_user_prompt(payload, rules, basis))
        if obj is None:
            llm_status = "failed"
        else:
            problems = llm_provider.validate_advice(obj)
            if problems:
                obj = llm_provider.autofix_advice(obj, fallback)
                llm_status = "autofixed" if obj is not None else "invalid"
            else:
                llm_status = "ok"
            if obj is not None:
                source, advice = "llm", obj
    else:
        fallback = _fallback_advice(grid, rules)
    if advice is None:
        advice = fallback

    record = {
        "advice_id": f"ADV-{datetime.now().strftime('%Y%m%d%H%M%S')}-"
                     f"{hashlib.sha256(f'{analysis_version}{grid_id}'.encode()).hexdigest()[:4]}",
        "analysis_version": analysis_version,
        "grid_id": grid_id,
        "risk_layer": layer,
        "cache_key": ckey,
        "source": source,
        "llm_status": llm_status,
        "model_name": model_name,
        "knowledge_base_version": kb_version,
        "prompt_version": PROMPT_VERSION,
        "retrieved_rules": [
            {"rule_id": r["rule_id"], "title": r["title"],
             "action_text": r["action_text"], "caution": r.get("caution", ""),
             "basis_id": r.get("basis_id")} for r in rules],
        "payload": payload,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        **{k: advice[k] for k in ADVICE_SECTIONS if k in advice},
        "basis_ids": advice.get("basis_ids", []),
        "caution_note": advice.get("caution_note", ""),
        "cached": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    log.info("advice generated av=%s grid=%s source=%s rules=%s",
             analysis_version, grid_id, source, len(rules))
    return record


def clear_advice(analysis_version: str, grid_id: str) -> bool:
    """管理员清除单条缓存后可重新生成（12.2）。"""
    path = _advice_path(analysis_dir(analysis_version), grid_id)
    if path.exists():
        path.unlink()
        return True
    return False


def get_basis(analysis_version: str, grid_id: str) -> dict:
    """#11 依据溯源：从建议记录取 basis_ids，读对应知识库版本全文（13.3）。"""
    path = _advice_path(analysis_dir(analysis_version), grid_id)
    if not path.exists():
        raise FileNotFoundError(f"该网格尚未生成建议: {grid_id}")
    rec = json.loads(path.read_text(encoding="utf-8"))
    basis = kb.get_basis(rec.get("knowledge_base_version"))
    details = [
        {"basis_id": bid, **(basis.get(bid) or {})}
        for bid in rec.get("basis_ids", [])
    ]
    return {
        "advice_id": rec.get("advice_id"),
        "grid_id": grid_id,
        "analysis_version": analysis_version,
        "knowledge_base_version": rec.get("knowledge_base_version"),
        "source": rec.get("source"),
        "retrieved_rules": rec.get("retrieved_rules", []),
        "basis": details,
    }
