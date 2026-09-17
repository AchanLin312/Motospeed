"""M1 地图匹配服务：IVMM（改进型迭代 Viterbi 地图匹配，Yu et al. 2014 骨架）。

参数对齐需求手册（见 __init__.py）：
- alpha=5        每点最多候选路段数
- r=150 m        候选查询半径
- beta=50/200    观察分数尺度参数（链内相邻点间隔众数 <10s / >=10s）
- GL_threshold=10 传递分数尺度（|sp-gc| 衰减尺度，单位米）

对应验收：
- AC06 匹配使用无向路网拓扑（MultiGraph），方向信息保留
- AC07 匹配偏移按道路等级上限校验（ROAD_LEVEL_OFFSET_LIMITS）

算法（每条子链独立 Viterbi 动态规划）：
- 观察分数 obs(c)  = exp(-0.5*(d/β)^2)，d 为点到候选路段投影距离
- 传递分数 FT(c1,c2) = w1*ts + w2*mt（经典 IVMM 权重 w1=0.17, w2=0.83）
  - ts = exp(-(sp-gc)/GL)，gc=候选点直线距离，sp=路网最短路径距离（不可达 → 0）
  - mt = 0.5*(1+cos(Δθ))，观测航向 vs 候选边所在线段方向
- 累积：Viterbi score = log(max(obs,1e-12)) + Σ FT
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd
from shapely.geometry import Point
from shapely.strtree import STRtree

from . import (IVMM_ALPHA, IVMM_BETA_FAST, IVMM_BETA_SLOW, IVMM_FAR_M,
               IVMM_GL_THRESHOLD, IVMM_R, RULE_VERSION, TARGET_CRS,
               analysis_dir, batch_dir)
from .road_network_service import (ROAD_LEVEL_OFFSET_LIMITS, latest_network_id,
                                   load_network)

_EPS = 1e-12
_SP_CUTOFF_M = 600.0   # 传递最短路径搜索上限（相邻候选点直线距离通常 <100m）
_W1, _W2 = 0.17, 0.83  # 经典 IVMM 传递分数权重

# ---------------------------------------------------------------- 索引

class _NetIndex:
    """匹配用空间索引：只收 matchable 边的几何 + 属性。"""

    def __init__(self, G: nx.MultiGraph):
        self.geoms, self.refs = [], []
        for u, v, k, d in G.edges(keys=True, data=True):
            if not d.get("matchable", False):
                continue
            self.geoms.append(d["geometry"])
            self.refs.append((u, v, k, d))
        self.tree = STRtree(self.geoms)

    def candidates(self, pt_utm: Point, r: float = IVMM_R,
                   alpha: int = IVMM_ALPHA) -> list[dict]:
        """返回该点候选：按投影距离升序的最多 alpha 条不同路段。"""
        try:
            hit = self.tree.query(pt_utm.buffer(r), predicate="intersects")
        except Exception:
            return []
        best: dict[tuple, dict] = {}
        for idx in hit:
            g = self.geoms[idx]
            d_along = g.project(pt_utm)
            proj = g.interpolate(d_along)
            dist = pt_utm.distance(proj)
            ref = self.refs[idx]
            key = (ref[0], ref[1], ref[2])
            if key not in best or dist < best[key]["d"]:
                best[key] = {
                    "ref": key, "level": ref[3]["road_level"],
                    "oneway": ref[3]["oneway"], "edge_len": ref[3]["length_m"],
                    "d": dist, "proj": proj, "along": d_along,
                    "seg_bearing": _seg_bearing(g, d_along),
                }
        cands = sorted(best.values(), key=lambda c: c["d"])
        # 候选质量门槛：最近路段过远（园区内部/漂移点）不强行匹配
        if not cands or cands[0]["d"] > IVMM_FAR_M:
            return []
        return cands[:alpha]


def _seg_bearing(line, along: float) -> float | None:
    """投影点所在线段的方向角（沿边正向）。"""
    coords = list(line.coords)
    cum = 0.0
    for i in range(len(coords) - 1):
        x1, y1 = coords[i][0], coords[i][1]
        x2, y2 = coords[i + 1][0], coords[i + 1][1]
        seg_len = math.hypot(x2 - x1, y2 - y1)
        if seg_len <= 0.0:
            continue
        if cum + seg_len >= along or i == len(coords) - 2:
            return _bearing(x1, y1, x2, y2)
        cum += seg_len
    return None


def _bearing(x1: float, y1: float, x2: float, y2: float) -> float | None:
    dx, dy = x2 - x1, y2 - y1
    if dx == 0.0 and dy == 0.0:
        return None
    return math.degrees(math.atan2(dx, dy)) % 360.0


def _angdiff(a: float, b: float) -> float:
    """角差绝对值 0~180。"""
    return abs((a - b + 180.0) % 360.0 - 180.0)


# ---------------------------------------------------------------- 最短路径

_SP_CACHE: dict[tuple, dict] = {}


def _dijkstra_from(G: nx.MultiGraph, net_id: str, source, cutoff=_SP_CUTOFF_M) -> dict:
    key = (net_id, source)
    hit = _SP_CACHE.get(key)
    if hit is None:
        hit = nx.single_source_dijkstra_path_length(G, source, cutoff=cutoff, weight="length_m")
        _SP_CACHE[key] = hit
    return hit


def _sp_between(G: nx.MultiGraph, net_id: str, c1: dict, c2: dict) -> float | None:
    """两个候选投影点之间的路网最短路径距离；不可达返回 None。"""
    u1, v1, _ = c1["ref"]
    u2, v2, _ = c2["ref"]
    if c1["ref"] == c2["ref"]:
        return abs(c2["along"] - c1["along"])
    best = None
    for n1, d_to_u in ((u1, c1["along"]), (v1, c1["edge_len"] - c1["along"])):
        dists = _dijkstra_from(G, net_id, n1)
        for n2, d_from_v in ((u2, c2["along"]), (v2, c2["edge_len"] - c2["along"])):
            mid = dists.get(n2)
            if mid is None:
                continue
            total = d_to_u + mid + d_from_v
            if best is None or total < best:
                best = total
    return best


# ---------------------------------------------------------------- 单链匹配

def _beta_for_chain(dt_mode: float) -> float:
    return IVMM_BETA_FAST if dt_mode < 10.0 else IVMM_BETA_SLOW


def match_chain(index: _NetIndex, G: nx.MultiGraph, net_id: str,
                pts_utm: list[Point], obs_bearings: list[float | None],
                beta: float) -> list[dict]:
    """对一条子链 Viterbi 匹配；返回与输入等长的候选选择（None=未匹配）。"""
    n = len(pts_utm)
    cands = [index.candidates(p) for p in pts_utm]

    def log_obs(c: dict) -> float:
        return math.log(max(math.exp(-0.5 * (c["d"] / beta) ** 2), _EPS))

    # dp 层：key=点索引，value=[(score, backptr)]；空候选点不参与 DP（输出未匹配）
    layers: dict[int, list[tuple[float, int]]] = {}
    first_valid = next((i for i in range(n) if cands[i]), None)
    if first_valid is None:
        return [None] * n
    layers[first_valid] = [(log_obs(c), -1) for c in cands[first_valid]]
    last_i = first_valid
    for i in range(first_valid + 1, n):
        if not cands[i]:
            continue
        prev_layer = layers[last_i]
        cur = []
        for c in cands[i]:
            best_score, best_k = -math.inf, -1
            for k, pc in enumerate(cands[last_i]):
                gc = pc["proj"].distance(c["proj"])
                sp = _sp_between(G, net_id, pc, c)
                ts = (math.exp(-max(sp - gc, 0.0) / IVMM_GL_THRESHOLD)
                      if sp is not None else 0.0)
                ob = obs_bearings[i]
                if ob is not None and c["seg_bearing"] is not None:
                    mt = 0.5 * (1.0 + math.cos(math.radians(_angdiff(ob, c["seg_bearing"]))))
                else:
                    mt = 0.5
                total = prev_layer[k][0] + _W1 * ts + _W2 * mt
                if total > best_score:
                    best_score, best_k = total, k
            cur.append((best_score + log_obs(c), best_k))
        layers[i] = cur
        last_i = i

    # 回溯
    chosen: list[dict | None] = [None] * n
    k = max(range(len(layers[last_i])), key=lambda j: layers[last_i][j][0])
    chosen[last_i] = cands[last_i][k]
    i = last_i
    while i > first_valid:
        prev_i = i - 1
        while prev_i not in layers:
            prev_i -= 1
        k = layers[i][k][1]
        chosen[prev_i] = cands[prev_i][k]
        i = prev_i
    return chosen


# ---------------------------------------------------------------- 批次匹配

def match_batch(batch_id: str, net_id: str | None = None,
                analysis_version: str | None = None) -> dict:
    """对批次执行 IVMM 匹配，结果落盘到 analysis/<version>/matched_points.csv。"""
    t0 = time.time()
    net_id = net_id or latest_network_id()
    if net_id is None:
        raise FileNotFoundError("无可用路网版本，请先构建路网")
    G, net_meta = load_network(net_id)
    index = _NetIndex(G)

    bdir = batch_dir(batch_id)
    traj = pd.read_csv(bdir / "trajectory.csv", encoding="utf-8-sig",
                       dtype={"vehicle_id": str, "segment_id": str})
    traj = traj.sort_values(["segment_id", "point_order"]).reset_index(drop=True)

    gdf = gpd.GeoDataFrame(
        traj, geometry=gpd.points_from_xy(traj["lon"], traj["lat"]), crs="EPSG:4326")
    gdf_utm = gdf.to_crs(TARGET_CRS)

    rows: list[dict] = []
    beta_counts = {"fast": 0, "slow": 0}
    proj_pts_wgs = []  # (row_idx, shapely Point UTM)
    for seg_id, grp in gdf_utm.groupby("segment_id", sort=False):
        # 手册要求 beta 按链内时间间隔众数动态选取（逐链，而非全批次）
        dts = pd.to_numeric(grp["dt_s"], errors="coerce").dropna()
        dts = dts[dts > 0]
        dt_mode = float(dts.mode().iloc[0]) if len(dts) else 0.0
        beta = _beta_for_chain(dt_mode)
        beta_counts["fast" if beta == IVMM_BETA_FAST else "slow"] += 1
        pts = [Point(x, y) for x, y in zip(grp.geometry.x, grp.geometry.y)]
        n_pts = len(pts)
        obs_bearings: list[float | None] = []
        for i in range(n_pts):
            if i == 0 or n_pts == 1:
                obs_bearings.append(None)
            else:
                obs_bearings.append(_bearing(pts[i - 1].x, pts[i - 1].y,
                                             pts[i].x, pts[i].y))
        chosen = match_chain(index, G, net_id, pts, obs_bearings, beta)
        for local_i, (idx, row) in enumerate(grp.iterrows()):
            c = chosen[local_i]
            rec = {
                "_gidx": int(idx),
                "segment_id": seg_id,
                "point_order": int(row["point_order"]),
                "vehicle_id": row["vehicle_id"],
                "time": row["time"],
                "lon": row["lon"],
                "lat": row["lat"],
                "quality_flag": row.get("quality_flag", "ok"),
            }
            if c is None:
                rec.update({"matched_u": "", "matched_v": "", "matched_k": "",
                            "road_level": "", "oneway": "", "proj_dist_m": "",
                            "seg_bearing": "",
                            "obs_bearing": obs_bearings[local_i] or "",
                            "travel_dir": "", "matched": 0})
            else:
                proj_pts_wgs.append((idx, c["proj"]))
                rec.update({
                    "matched_u": c["ref"][0], "matched_v": c["ref"][1],
                    "matched_k": c["ref"][2], "road_level": c["level"],
                    "oneway": c["oneway"], "proj_dist_m": round(c["d"], 2),
                    "seg_bearing": round(c["seg_bearing"], 1) if c["seg_bearing"] is not None else "",
                    "obs_bearing": round(obs_bearings[local_i], 1) if obs_bearings[local_i] is not None else "",
                    "matched": 1,
                })
                if obs_bearings[local_i] is not None and c["seg_bearing"] is not None:
                    cosv = math.cos(math.radians(
                        _angdiff(obs_bearings[local_i], c["seg_bearing"])))
                    rec["travel_dir"] = "forward" if cosv >= 0 else "backward"
            rows.append(rec)

    out = pd.DataFrame(rows)
    # 投影点批量反投影回 WGS84 后按行合并
    if proj_pts_wgs:
        geo = gpd.GeoSeries([p for _, p in proj_pts_wgs], crs=TARGET_CRS).to_crs("EPSG:4326")
        proj_df = pd.DataFrame({
            "_gidx": [int(i) for i, _ in proj_pts_wgs],
            "proj_lon": [round(p.x, 7) for p in geo],
            "proj_lat": [round(p.y, 7) for p in geo],
        })
        out = out.merge(proj_df, on="_gidx", how="left")
        out["proj_lon"] = out["proj_lon"].fillna("")
        out["proj_lat"] = out["proj_lat"].fillna("")
    else:
        out["proj_lon"] = ""
        out["proj_lat"] = ""
    out = out.drop(columns=["_gidx"])

    matched_mask = out["matched"] == 1
    match_rate = float(matched_mask.mean()) if len(out) else 0.0

    if analysis_version is None:
        h = hashlib.md5(f"{batch_id}|{net_id}".encode()).hexdigest()[:8]
        analysis_version = f"AV-{datetime.now():%Y%m%d}-{h}"
    adir = analysis_dir(analysis_version)
    adir.mkdir(parents=True, exist_ok=True)
    out.to_csv(adir / "matched_points.csv", index=False, encoding="utf-8-sig")

    meta = {
        "analysis_version": analysis_version,
        "batch_id": batch_id,
        "net_id": net_id,
        "rule_version": RULE_VERSION,
        "algorithm": "IVMM (Viterbi, alpha=%d, r=%.0fm, beta=%.0f/%.0fm, GL=%.0fm)" % (
            IVMM_ALPHA, IVMM_R, IVMM_BETA_FAST, IVMM_BETA_SLOW, IVMM_GL_THRESHOLD),
        "beta_used": {"fast": beta_counts["fast"], "slow": beta_counts["slow"]},
        "points_total": int(len(out)),
        "points_matched": int(matched_mask.sum()),
        "match_rate": round(match_rate, 4),
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - t0, 1),
    }
    (adir / "match_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


# ---------------------------------------------------------------- AC07 校验

def validate_offsets(analysis_version: str) -> dict:
    """按道路等级校验匹配偏移分位数是否超出上限（AC07）。"""
    adir = analysis_dir(analysis_version)
    df = pd.read_csv(adir / "matched_points.csv", encoding="utf-8-sig",
                     dtype={"road_level": str})
    df = df[(df["matched"] == 1) & df["proj_dist_m"].notna()]
    report = {}
    for level, grp in df.groupby("road_level"):
        q = grp["proj_dist_m"].quantile([0.5, 0.95, 0.99])
        limit = ROAD_LEVEL_OFFSET_LIMITS.get(level)
        entry = {
            "count": int(len(grp)),
            "p50": round(float(q[0.5]), 1),
            "p95": round(float(q[0.95]), 1),
            "p99": round(float(q[0.99]), 1),
        }
        if limit:
            if "limit" in limit:
                entry["limit"] = limit["limit"]
                entry["pass"] = entry["p99"] <= limit["limit"]
            else:
                entry["limit_p95"], entry["limit_p99"] = limit["p95"], limit["p99"]
                entry["pass"] = (entry["p95"] <= limit["p95"]
                                 and entry["p99"] <= limit["p99"])
        report[level] = entry
    return report


# ---------------------------------------------------------------- 自测

if __name__ == "__main__":
    from . import BATCH_DIR
    batches = sorted(p for p in BATCH_DIR.iterdir() if p.is_dir())
    bid = batches[-1].name
    print(f"== 50 点样例最近边偏移检查（AC06 初验）==")
    G, m = load_network(latest_network_id())
    index = _NetIndex(G)
    traj = pd.read_csv(batch_dir(bid) / "trajectory.csv", encoding="utf-8-sig").sample(
        50, random_state=42)
    gs = gpd.GeoSeries(gpd.points_from_xy(traj["lon"], traj["lat"]), crs="EPSG:4326").to_crs(TARGET_CRS)
    ds = []
    for p in gs:
        cs = index.candidates(p, r=IVMM_R, alpha=1)
        if cs:
            ds.append(cs[0]["d"])
    ds_arr = pd.Series(ds)
    print(ds_arr.describe(percentiles=[0.5, 0.95]).to_string())
    print(f"\n== 全批次 IVMM 匹配 {bid} ==")
    meta = match_batch(bid)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    rep = validate_offsets(meta["analysis_version"])
    print(json.dumps(rep, ensure_ascii=False, indent=2))
