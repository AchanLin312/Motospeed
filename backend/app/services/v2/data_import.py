"""V2 数据导入服务（M0）。

职责（需求手册"数据接入"）：
- 新版轨迹 CSV 字段校验（缺失 → 阻断并列出可接受别名）
- 异常行隔离（时间/坐标无效），超比例阻断
- 标准化：POSITIONTIME 时间基准（TS 比 POSITIONTIME 早 30 天，弃用）、
  Speed 为 m/s 须换算 km/h（AC03）、TID=1 链首切分子链（M0 勘验结论）
- 不可变批次落盘：outputs/runtime/v2/batches/<batch_id>/
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from . import RULE_VERSION, YIZHUANG_BBOX, BATCH_DIR, batch_dir

# 必需字段：别名表（手册要求：缺失时列出缺失字段和可接受别名）
FIELD_ALIASES: Dict[str, List[str]] = {
    "time": ["POSITIONTIME", "position_time", "Time", "time", "时间", "定位时间"],
    "lon": ["X_position", "longitude", "lon", "x", "经度"],
    "lat": ["Y_position", "latitude", "lat", "y", "纬度"],
    "vehicle_id": ["BICYCLEID", "bicycle_id", "bike_id", "vehicle_id", "ID"],
}
OPTIONAL_ALIASES: Dict[str, List[str]] = {
    "device_id": ["NEW_BICYCLEID", "device_id"],
    "company_id": ["COMPANYID", "company_id"],
    "lock_id": ["LOCKID", "lock_id"],
    "lock_status": ["LOCKSTATUS", "lock_status"],
    "segment_flag": ["TID", "tid"],          # M0 勘验：TID=1 为轨迹链首
    "raw_speed_mps": ["Speed", "speed"],     # 原始速度 m/s（仅作交叉校验）
    "raw_distance": ["Distance", "distance"],
    "raw_duration": ["Time_consuming", "time_consuming"],
    "ts_raw": ["TS"],
}

# 分析坐标（M0 勘验定论）：X/Y 为 WGS-84 且贴合路网（中位距 7.5m）；
# BICYCLE_LNG/LAT 为 GCJ-02 加密坐标（恒定偏移约 525m），不用于分析。
ANALYSIS_COORD_NOTE = "X_position/Y_position (WGS-84); BICYCLE_LNG/LAT=GCJ-02 弃用"

MAX_ISOLATED_RATIO = 0.30   # 异常行超过 30% 阻断分析
MAX_PLAUSIBLE_SPEED_MPS = 30.0  # 108 km/h 以上视为 GPS 漂移
SEGMENT_GAP_S = 180.0       # 链内时间间隔超过 180s 切新子链


class ImportValidationError(Exception):
    """字段缺失或异常行超比例（业务端展示 message）。"""


def _pick(df: pd.DataFrame, aliases: List[str]) -> Optional[str]:
    """返回匹配的实际列名，未命中返回 None。"""
    lowered = {c.lower(): c for c in df.columns}
    for a in aliases:
        hit = lowered.get(a.lower())
        if hit is not None:
            return hit
    return None


def _haversine_m(lon1, lat1, lon2, lat2) -> np.ndarray:
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371000.0 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def import_trajectory_csv(file_path: Path, source_name: str = "") -> Dict[str, Any]:
    """导入新版轨迹 CSV，返回批次信息。任何阻断性错误抛 ImportValidationError。"""
    raw = pd.read_csv(file_path, sep=None, engine="python")
    raw.columns = [str(c).strip() for c in raw.columns]
    return import_dataframe(raw, source_name or Path(file_path).name)


def import_dataframe(raw: pd.DataFrame, source_name: str = "") -> Dict[str, Any]:
    # ---- 1. 字段校验（阻断） ----
    resolved: Dict[str, str] = {}
    missing: List[Dict[str, str]] = []
    for std, aliases in FIELD_ALIASES.items():
        col = _pick(raw, aliases)
        if col is None:
            missing.append({"field": std, "accepted_aliases": aliases})
        else:
            resolved[std] = col
    if missing:
        raise ImportValidationError(
            "CSV 字段缺失，无法创建分析版本: "
            + "; ".join(f"{m['field']}（可接受别名: {'/'.join(m['accepted_aliases'])}）" for m in missing)
        )

    df = pd.DataFrame({std: raw[col] for std, col in resolved.items()})
    for std, aliases in OPTIONAL_ALIASES.items():
        col = _pick(raw, aliases)
        if col is not None:
            df[std] = raw[col].values

    total_in = len(df)

    # ---- 2. 清洗与异常隔离 ----
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")

    bad_time = df["time"].isna()
    bad_coord = df["lon"].isna() | df["lat"].isna() | df["lon"].isna()
    out_of_range = df["lon"].notna() & ~df["lon"].between(YIZHUANG_BBOX[0] - 0.2, YIZHUANG_BBOX[2] + 0.2)
    out_of_range |= df["lat"].notna() & ~df["lat"].between(YIZHUANG_BBOX[1] - 0.2, YIZHUANG_BBOX[3] + 0.2)
    bad = bad_time | bad_coord | out_of_range

    isolated = df[bad].copy()
    isolated["isolate_reason"] = np.where(bad_time[bad], "invalid_time",
                                          np.where(out_of_range[bad], "coord_out_of_range", "invalid_coord"))
    df = df[~bad].copy()
    isolated_ratio = len(isolated) / max(total_in, 1)
    if total_in and isolated_ratio > MAX_ISOLATED_RATIO:
        raise ImportValidationError(
            f"时间或坐标无效行占比 {isolated_ratio:.0%} 超过阈值 {MAX_ISOLATED_RATIO:.0%}，阻止分析"
        )

    # ---- 3. 排序 + 子链切分（TID=1 链首 或 大间隔） ----
    df = df.sort_values(["vehicle_id", "time"], kind="mergesort").reset_index(drop=True)
    df["lock_status"] = pd.to_numeric(df.get("lock_status"), errors="coerce").fillna(0).astype(int)
    df["segment_flag"] = pd.to_numeric(df.get("segment_flag"), errors="coerce").fillna(0).astype(int)

    dt = df.groupby("vehicle_id")["time"].diff().dt.total_seconds()
    new_chain = (df["segment_flag"] == 1) | (dt.fillna(SEGMENT_GAP_S + 1) > SEGMENT_GAP_S)
    df["segment_seq"] = (new_chain | (df["vehicle_id"] != df["vehicle_id"].shift())).groupby(
        df["vehicle_id"]).cumsum()
    df["segment_id"] = df["vehicle_id"].astype(str) + "-" + df["segment_seq"].astype(str)
    df["point_order"] = df.groupby("segment_id").cumcount()

    # ---- 4. 相邻点运动学重算（不信任 Distance/Time_consuming，AC03） ----
    grp = df.groupby("segment_id")
    df["dt_s"] = grp["time"].diff().dt.total_seconds()
    df["dist_m"] = _haversine_m(
        df["lon"].shift(), df["lat"].shift(), df["lon"], df["lat"])
    df.loc[df["point_order"] == 0, ["dt_s", "dist_m"]] = np.nan
    df["calc_speed_mps"] = df["dist_m"] / df["dt_s"].replace(0, np.nan)

    # Speed 交叉校验（m/s；AC03：Speed×3.6 应与距离/时间重算一致）
    if "raw_speed_mps" in df.columns:
        df["raw_speed_mps"] = pd.to_numeric(df["raw_speed_mps"], errors="coerce")
        chk = df["raw_speed_mps"].notna() & df["calc_speed_mps"].notna() & (df["calc_speed_mps"] > 0.3)
        rel = ((df.loc[chk, "raw_speed_mps"] - df.loc[chk, "calc_speed_mps"]).abs()
               / df.loc[chk, "calc_speed_mps"])
        speed_check = {"matched_rows": int(chk.sum()),
                       "median_rel_err": float(rel.median()) if len(rel) else None}
    else:
        speed_check = {"matched_rows": 0, "median_rel_err": None}

    # 统一速度：优先重算值，缺失时回退原始 Speed 列
    df["speed_mps"] = df["calc_speed_mps"]
    fallback = df["speed_mps"].isna() & df.get("raw_speed_mps", pd.Series(np.nan, index=df.index)).notna() \
        & (df["dt_s"].fillna(1) > 0) & (df["point_order"] > 0)
    df.loc[fallback, "speed_mps"] = df.loc[fallback, "raw_speed_mps"]
    df["speed_kmh"] = df["speed_mps"] * 3.6

    # 漂移标记（不删除，行为识别阶段跳过）
    df["quality_flag"] = "ok"
    df.loc[df["speed_mps"] > MAX_PLAUSIBLE_SPEED_MPS, "quality_flag"] = "drift"

    # ---- 5. 落盘（不可变批次） ----
    batch_id = f"B-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    bdir = batch_dir(batch_id)
    bdir.mkdir(parents=True, exist_ok=True)

    out_cols = ["vehicle_id", "device_id", "company_id", "lock_id", "segment_id", "point_order",
                "time", "lon", "lat", "speed_mps", "speed_kmh", "dist_m", "dt_s",
                "calc_speed_mps", "quality_flag", "segment_flag", "lock_status", "ts_raw",
                "raw_speed_mps", "raw_distance", "raw_duration"]
    out = df[[c for c in out_cols if c in df.columns]].copy()
    out["time"] = out["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    out.to_csv(bdir / "trajectory.csv", index=False, encoding="utf-8-sig")
    if len(isolated):
        iso = isolated.copy()
        iso["time"] = pd.to_datetime(iso["time"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
        iso.to_csv(bdir / "isolated_rows.csv", index=False, encoding="utf-8-sig")

    t_min, t_max = df["time"].min(), df["time"].max()
    meta = {
        "batch_id": batch_id,
        "source_name": source_name,
        "rule_version": RULE_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analysis_coord": ANALYSIS_COORD_NOTE,
        "rows_total": int(total_in),
        "rows_kept": int(len(df)),
        "rows_isolated": int(len(isolated)),
        "isolated_ratio": round(float(isolated_ratio), 4),
        "vehicle_count": int(df["vehicle_id"].nunique()),
        "segment_count": int(df["segment_id"].nunique()),
        "time_start": t_min.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(t_min) else None,
        "time_end": t_max.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(t_max) else None,
        "speed_unit_check": speed_check,
        "bbox": [float(df["lon"].min()), float(df["lat"].min()),
                 float(df["lon"].max()), float(df["lat"].max())],
    }
    (bdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def list_batches() -> List[Dict[str, Any]]:
    out = []
    if not BATCH_DIR.exists():
        return out
    for d in sorted(BATCH_DIR.iterdir(), reverse=True):
        m = d / "meta.json"
        if d.is_dir() and m.exists():
            out.append(json.loads(m.read_text(encoding="utf-8")))
    return out


def get_batch_meta(batch_id: str) -> Optional[Dict[str, Any]]:
    m = batch_dir(batch_id) / "meta.json"
    return json.loads(m.read_text(encoding="utf-8")) if m.exists() else None


def load_batch_trajectory(batch_id: str) -> Optional[pd.DataFrame]:
    f = batch_dir(batch_id) / "trajectory.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f)
    df["time"] = pd.to_datetime(df["time"])
    return df
