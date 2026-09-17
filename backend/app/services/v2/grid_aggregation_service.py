"""M3 网格聚合服务：UTM 米制网格 + 暴露量分配 + 三类事件率。

验收对照：
- AC14 暴露量 = 有效里程按网格相交长度分配；事件率单位 次/100km
- AC15 网格默认 250m，支持 100/250/500 配置（UTM 米制网格）

输入：analysis/<version>/matched_points.csv + events.csv
输出：analysis/<version>/grid_metrics.csv + grid_meta.json

有效里程定义：同一 segment 内相邻两个匹配点的投影坐标连线段，
距离 ≤200m 且时间间隔 ≤30min 计入有效里程（否则视为断链不累计），
线段与网格的相交长度即为该网格获得的暴露里程。
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, box

from . import RULE_VERSION, TARGET_CRS, analysis_dir

GRID_SIZE_CHOICES = (100.0, 250.0, 500.0)
DEFAULT_GRID_SIZE = 250.0

_BREAK_DIST_M = 200.0   # 相邻匹配投影点距离超过此值 → 断链
_BREAK_DT_S = 1800.0    # 相邻点时间间隔超过 30min → 断链

_EVENT_COL = {"overspeed": "overspeed_count", "reverse": "reverse_count",
              "rapid": "rapid_count"}


def _cell_of(x: float, y: float, x0: float, y0: float, size: float) -> tuple[int, int]:
    return int((x - x0) // size), int((y - y0) // size)


def run_grid(analysis_version: str, cell_size: float = DEFAULT_GRID_SIZE) -> dict:
    """对指定分析版本执行网格聚合，写回 grid_metrics.csv / grid_meta.json。"""
    if cell_size not in GRID_SIZE_CHOICES:
        raise ValueError(f"cell_size 必须为 {GRID_SIZE_CHOICES} 之一")
    adir = analysis_dir(analysis_version)

    matched = pd.read_csv(adir / "matched_points.csv", encoding="utf-8-sig",
                          dtype={"vehicle_id": str, "segment_id": str})
    ev = pd.read_csv(adir / "events.csv", encoding="utf-8-sig",
                     dtype={"vehicle_id": str, "segment_id": str}) if (
        adir / "events.csv").exists() else pd.DataFrame()

    # ---- 匹配投影点 → UTM
    mp = matched[(matched["matched"] == 1)].copy()
    mp["proj_lon"] = pd.to_numeric(mp["proj_lon"], errors="coerce")
    mp["proj_lat"] = pd.to_numeric(mp["proj_lat"], errors="coerce")
    mp = mp[mp["proj_lon"].notna() & mp["proj_lat"].notna()]
    mp = mp.sort_values(["segment_id", "point_order"]).reset_index(drop=True)
    if mp.empty:
        raise ValueError("无可用匹配点，请先执行 IVMM 匹配")
    gdf = gpd.GeoDataFrame(
        mp, geometry=gpd.points_from_xy(mp["proj_lon"], mp["proj_lat"]),
        crs="EPSG:4326").to_crs(TARGET_CRS)
    xs, ys = gdf.geometry.x.values, gdf.geometry.y.values

    # ---- 暴露量：相邻匹配点连线段按网格相交长度分配
    size = float(cell_size)
    x0 = math.floor(xs.min() / size) * size
    y0 = math.floor(ys.min() / size) * size
    exposure_m: dict[tuple, float] = defaultdict(float)
    veh_grids: dict[tuple, set] = defaultdict(set)
    seg_grids: dict[tuple, set] = defaultdict(set)   # 每格轨迹子链数（质量标记用）

    seg_ids = gdf["segment_id"].values
    veh_ids = gdf["vehicle_id"].values
    times = pd.to_datetime(gdf["time"], format="mixed").values.astype("datetime64[s]")

    def _distribute(line: LineString, c0: int, r0: int, c1: int, r1: int,
                    vid: str, seg: str) -> None:
        for c in range(min(c0, c1), max(c0, c1) + 1):
            for r in range(min(r0, r1), max(r0, r1) + 1):
                cell = box(x0 + c * size, y0 + r * size,
                           x0 + (c + 1) * size, y0 + (r + 1) * size)
                inter = line.intersection(cell)
                if not inter.is_empty:
                    exposure_m[(c, r)] += inter.length
                    veh_grids[(c, r)].add(vid)
                    seg_grids[(c, r)].add(seg)

    for i in range(1, len(gdf)):
        if seg_ids[i] != seg_ids[i - 1]:
            continue
        dt = float((times[i] - times[i - 1]) / np.timedelta64(1, "s"))
        if dt <= 0 or dt > _BREAK_DT_S:
            continue
        dist = math.hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1])
        if dist <= 0 or dist > _BREAK_DIST_M:
            continue
        c0, r0 = _cell_of(xs[i - 1], ys[i - 1], x0, y0, size)
        c1, r1 = _cell_of(xs[i], ys[i], x0, y0, size)
        if c0 == c1 and r0 == r1:               # 同格：直接累计，免几何求交
            exposure_m[(c0, r0)] += dist
            veh_grids[(c0, r0)].add(veh_ids[i])
            seg_grids[(c0, r0)].add(seg_ids[i])
        else:
            _distribute(LineString([(xs[i - 1], ys[i - 1]), (xs[i], ys[i])]),
                        c0, r0, c1, r1, veh_ids[i], seg_ids[i])

    # ---- 事件落格（事件坐标为观测点，转 UTM）
    ev_counts: dict[tuple, dict] = defaultdict(lambda: defaultdict(int))
    if len(ev) and {"lon", "lat", "event_type"}.issubset(ev.columns):
        eg = gpd.GeoDataFrame(
            ev, geometry=gpd.points_from_xy(ev["lon"], ev["lat"]),
            crs="EPSG:4326").to_crs(TARGET_CRS)
        for (x, y, etype, vid) in zip(eg.geometry.x, eg.geometry.y,
                                      ev["event_type"], ev["vehicle_id"]):
            c, r = _cell_of(x, y, x0, y0, size)
            ev_counts[(c, r)][etype] += 1
            veh_grids[(c, r)].add(vid)
    keys = sorted(set(exposure_m) | set(ev_counts))
    if not keys:
        raise ValueError("网格聚合结果为空")

    # ---- 网格 center/角点 批量逆投影为 WGS84（供前端绘制）
    centers = [((c + 0.5) * size + x0, (r + 0.5) * size + y0) for c, r in keys]
    corners = [((c * size + x0, r * size + y0),
                ((c + 1) * size + x0, (r + 1) * size + y0)) for c, r in keys]
    cg = gpd.GeoSeries(gpd.points_from_xy([p[0] for p in centers],
                                          [p[1] for p in centers]),
                       crs=TARGET_CRS).to_crs("EPSG:4326")
    ll = gpd.GeoSeries(gpd.points_from_xy([c[0] for c, _ in corners],
                                          [c[1] for c, _ in corners]),
                       crs=TARGET_CRS).to_crs("EPSG:4326")
    ur = gpd.GeoSeries(gpd.points_from_xy([u[0] for _, u in corners],
                                          [u[1] for _, u in corners]),
                       crs=TARGET_CRS).to_crs("EPSG:4326")

    rows = []
    for i, (c, r) in enumerate(keys):
        exp_km = exposure_m.get((c, r), 0.0) / 1000.0
        cnt = ev_counts.get((c, r), {})
        ov = cnt.get("overspeed", 0)
        rv = cnt.get("reverse", 0)
        ra_acc = cnt.get("rapid_accel", 0)
        ra_dec = cnt.get("rapid_decel", 0)
        ra = ra_acc + ra_dec + cnt.get("rapid", 0)
        n_seg = len(seg_grids.get((c, r), set()))
        if exp_km >= 1.0 and n_seg >= 5:
            quality = "valid"               # 有效（≥1km 且 ≥5 条子链）
        elif exp_km > 0 or (ov + rv + ra) > 0:
            quality = "low_exposure"        # 低暴露量
        else:
            quality = "insufficient_data"   # 数据不足
        rows.append({
            "grid_id": f"G{c:04d}_{r:04d}", "col": c, "row": r,
            "center_lon": round(float(cg.iloc[i].x), 6),
            "center_lat": round(float(cg.iloc[i].y), 6),
            "min_lon": round(float(ll.iloc[i].x), 6),
            "min_lat": round(float(ll.iloc[i].y), 6),
            "max_lon": round(float(ur.iloc[i].x), 6),
            "max_lat": round(float(ur.iloc[i].y), 6),
            "vehicle_count": len(veh_grids.get((c, r), set())),
            "segment_count": n_seg,
            "exposure_km": round(exp_km, 3),
            "overspeed_count": ov, "reverse_count": rv,
            "rapid_accel_count": ra_acc, "rapid_decel_count": ra_dec,
            "rapid_count": ra,
            "total_events": ov + rv + ra,
            # 率值仅在有效网格上计算：低暴露网格分母极小（如 5m 暴露 3 起事件
            # → 6 万次/100km），属统计噪声，留空表示"无数据"而非 0
            "overspeed_rate": round(ov / exp_km * 100, 2) if quality == "valid" else "",
            "reverse_rate": round(rv / exp_km * 100, 2) if quality == "valid" else "",
            "rapid_rate": round(ra / exp_km * 100, 2) if quality == "valid" else "",
            "quality_flag": quality,
        })
    out = pd.DataFrame(rows)
    out.to_csv(adir / "grid_metrics.csv", index=False, encoding="utf-8-sig")

    meta = {
        "analysis_version": analysis_version,
        "rule_version": RULE_VERSION,
        "cell_size_m": size,
        "grid_origin_utm": [x0, y0],
        "n_grids": int(len(out)),
        "quality_counts": out["quality_flag"].value_counts().to_dict(),
        "total_exposure_km": round(float(out["exposure_km"].sum()), 2),
        "total_events": int(out["total_events"].sum()),
        "event_counts": {
            "overspeed": int(out["overspeed_count"].sum()),
            "reverse": int(out["reverse_count"].sum()),
            "rapid": int(out["rapid_count"].sum()),
        },
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }
    (adir / "grid_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta
