"""V2 分析流水线编排：匹配 → 行为 → 网格 → 评分 → 热点 → summary。

供 API 层（后台线程）调用，progress 回调用于向 #6 状态接口上报进度。
"""
import json
from datetime import datetime

from . import analysis_dir, batch_dir, ANALYSIS_DIR, RULE_VERSION
from .map_match_service import match_batch
from .behavior_service import run_behavior
from .grid_aggregation_service import run_grid, DEFAULT_GRID_SIZE
from .scoring_service import run_scoring
from .hotspot_service import run_hotspots, run_moran

import pandas as pd


def new_analysis_version(batch_id: str) -> str:
    """生成分析版本号：A-<时间戳>-<短随机>。"""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    import uuid
    return f"A-{ts}-{uuid.uuid4().hex[:4]}"


def latest_analysis_version() -> str | None:
    """返回最近一个已完成（含 summary.json）的分析版本。"""
    if not ANALYSIS_DIR.exists():
        return None
    candidates = []
    for d in ANALYSIS_DIR.iterdir():
        if d.is_dir() and (d / "summary.json").exists():
            candidates.append((d.name, (d / "summary.json").stat().st_mtime))
    if not candidates:
        return None
    return max(candidates, key=lambda t: t[1])[0]


def run_pipeline(analysis_version: str, batch_id: str, net_id: str | None = None,
                 cell_size: float | None = None,
                 progress=None) -> dict:
    """执行完整分析流水线，返回 summary dict。

    :param progress: callable(stage: str, pct: float, message: str)
    """
    def _report(stage: str, pct: float, message: str = ""):
        if progress:
            try:
                progress(stage, float(pct), message)
            except Exception:
                pass

    _report("match", 5, "IVMM 地图匹配开始")
    match_batch(batch_id, net_id=net_id, analysis_version=analysis_version)
    _report("match", 28, "IVMM 匹配完成")

    _report("behavior", 30, "三类行为识别开始")
    run_behavior(analysis_version)
    _report("behavior", 48, "行为识别完成")

    _report("grid", 50, "网格聚合开始")
    run_grid(analysis_version, cell_size or DEFAULT_GRID_SIZE)
    _report("grid", 68, "网格聚合完成")

    _report("score", 70, "熵权+TOPSIS 评分开始")
    scoring_meta = run_scoring(analysis_version, force=True)
    _report("score", 82, "评分完成")

    _report("hotspot", 85, "四图层热点计算开始")
    hotspot_meta = run_hotspots(analysis_version, force=True)
    moran_meta = run_moran(analysis_version)
    _report("hotspot", 95, "热点计算完成")

    _report("summary", 96, "汇总 summary")
    summary = build_summary(analysis_version, scoring_meta=scoring_meta,
                            hotspot_meta=hotspot_meta, moran_meta=moran_meta)
    _report("done", 100, "分析完成")
    return summary


def build_summary(analysis_version: str, scoring_meta: dict | None = None,
                  hotspot_meta=None, moran_meta: dict | None = None) -> dict:
    """聚合各阶段元数据，写入 analysis/<version>/summary.json 并返回。"""
    adir = analysis_dir(analysis_version)
    summary: dict = {
        "analysis_version": analysis_version,
        "rule_version": RULE_VERSION,
        "status": "completed",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    # 匹配元数据（含 batch_id / net_id / match_rate）
    mm_path = adir / "match_meta.json"
    if mm_path.exists():
        mm = json.loads(mm_path.read_text(encoding="utf-8"))
        summary["match"] = mm
        batch_id = mm.get("batch_id")
    else:
        batch_id = None

    # 批次摘要
    if batch_id:
        bp = batch_dir(batch_id) / "meta.json"
        if bp.exists():
            bm = json.loads(bp.read_text(encoding="utf-8"))
            summary["batch"] = {
                "batch_id": bm.get("batch_id"),
                "source_name": bm.get("source_name"),
                "rows_kept": bm.get("rows_kept"),
                "rows_isolated": bm.get("rows_isolated"),
                "vehicle_count": bm.get("vehicle_count"),
                "segment_count": bm.get("segment_count"),
                "time_start": bm.get("time_start"),
                "time_end": bm.get("time_end"),
                "bbox": bm.get("bbox"),
            }

    # 行为事件摘要
    bh_path = adir / "behavior_meta.json"
    if bh_path.exists():
        bh = json.loads(bh_path.read_text(encoding="utf-8"))
        summary["behavior"] = {
            "event_counts": bh.get("event_counts"),
            "total_events": bh.get("total_events"),
            "accel_thresholds": bh.get("accel_thresholds"),
        }

    # 网格数量
    gpath = adir / "grid_metrics.csv"
    if gpath.exists():
        df = pd.read_csv(gpath, encoding="utf-8-sig", dtype={"grid_id": str})
        summary["grid_count"] = int(len(df))
        quality_counts = df["quality_flag"].value_counts().to_dict() if "quality_flag" in df.columns else {}
        summary["quality_flag_counts"] = {k: int(v) for k, v in quality_counts.items()}
        if "cri" in df.columns:
            cri = pd.to_numeric(df["cri"], errors="coerce").dropna()
            summary["cri_stats"] = {
                "count": int(len(cri)),
                "mean": round(float(cri.mean()), 1) if len(cri) else None,
                "max": round(float(cri.max()), 1) if len(cri) else None,
            }

    # 评分权重
    if scoring_meta:
        summary["scoring"] = {
            "weights": scoring_meta.get("weights"),
            "rapid_available": scoring_meta.get("rapid_available"),
            "method": scoring_meta.get("method"),
        }
    else:
        wpath = adir / "weights.json"
        if wpath.exists():
            summary["scoring"] = json.loads(wpath.read_text(encoding="utf-8"))

    # 热点图层摘要（layer → selection_type + feature_count）
    if hotspot_meta is None:                       # 仅重建 summary 时从磁盘回退
        hm_path = adir / "hotspots" / "hotspots_meta.json"
        if hm_path.exists():
            hotspot_meta = json.loads(hm_path.read_text(encoding="utf-8"))
    if hotspot_meta is not None:
        layers = None
        if isinstance(hotspot_meta, dict):
            if isinstance(hotspot_meta.get("layers"), dict):
                layers = hotspot_meta["layers"]
            elif all(isinstance(v, dict) for v in hotspot_meta.values()):
                layers = hotspot_meta
        if layers:
            hdir = adir / "hotspots"
            out = {}
            for layer, meta in layers.items():
                entry = dict(meta) if isinstance(meta, dict) else {
                    "selection_type": str(meta)}
                gj_path = hdir / f"{layer}.geojson"
                if gj_path.exists():
                    try:
                        n = len(json.loads(gj_path.read_text(
                            encoding="utf-8")).get("features", []))
                        entry["feature_count"] = n
                    except Exception:  # noqa: BLE001 —— 摘要统计失败不阻塞
                        pass
                out[layer] = entry
            summary["hotspots"] = out

    # Moran / LISA / 趋势
    if moran_meta is None:                         # 仅重建 summary 时从磁盘回退
        mm_path = adir / "moran_meta.json"
        if mm_path.exists():
            moran_meta = json.loads(mm_path.read_text(encoding="utf-8"))
    if moran_meta is not None:
        summary["moran"] = moran_meta

    (adir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    return summary


def get_summary(analysis_version: str) -> dict | None:
    p = analysis_dir(analysis_version) / "summary.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def infer_task_state(analysis_version: str) -> dict:
    """服务重启后内存任务丢失，从磁盘产物推断状态。"""
    adir = analysis_dir(analysis_version)
    if (adir / "summary.json").exists():
        return {"status": "completed", "progress": 100.0, "stage": "done"}
    if (adir / "grid_metrics.csv").exists():
        return {"status": "interrupted", "progress": 70.0, "stage": "score"}
    if (adir / "matched_points.csv").exists():
        return {"status": "interrupted", "progress": 30.0, "stage": "behavior"}
    return {"status": "unknown", "progress": 0.0, "stage": ""}
