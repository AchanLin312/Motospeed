"""M1 路网服务：shapefile 导入 → 亦庄 bbox 裁剪 → WGS84→UTM 50N → 无向图 → 版本管理。

关键设计（计划 D3/D4/D8，对应 AC06/AC07）：
- 无向拓扑参与匹配：networkx.MultiGraph（保留平行边，如双向分离道路）
- 方向信息不丢：每条边保留 oneway（B=双向 / F=正向单向 / T=反向单向，M0 实证）
  以及 forward/reverse 方位角，供 IVMM 候选投影与逆行判定使用
- 不可变版本目录：outputs/runtime/v2/road_networks/<net_id>/（D3）
- 幂等：同一 shapefile + 同一 bbox 重复构建返回同一 net_id，不重复落盘
"""
from __future__ import annotations

import hashlib
import json
import math
import pickle
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import networkx as nx
from shapely.geometry import LineString, MultiLineString, box

from . import (ROADNET_DIR, ROOT_DIR, RULE_VERSION, TARGET_CRS, YIZHUANG_BBOX,
               roadnet_dir)

# ---------------------------------------------------------------- 源与常量

DEFAULT_SOURCE = ROOT_DIR / "甲方新需求" / "亦庄_ori" / "亦庄_ori" / "北京市.shp"

# OSM fclass → 道路等级（用于偏移校验与逆行参数分级）
ROAD_LEVEL_MAP = {
    "motorway": "expressway",
    "motorway_link": "expressway_ramp",
    "trunk": "expressway",
    "trunk_link": "expressway_ramp",
    "primary": "arterial",
    "primary_link": "arterial_link",
    "secondary": "sub_arterial",
    "secondary_link": "sub_arterial_link",
    "tertiary": "branch",
    "tertiary_link": "branch",
    "unclassified": "branch",
    "residential": "branch",
    "living_street": "branch",
    "road": "branch",
    "busway": "branch",
    "service": "service_road",
    "track": "track",
    "track_grade1": "track",
    "track_grade2": "track",
    "track_grade3": "track",
    "track_grade4": "track",
    "track_grade5": "track",
    "path": "non_motor",
    "footway": "non_motor",
    "pedestrian": "non_motor",
    "steps": "non_motor",
    "cycleway": "non_motor",
    "bridleway": "non_motor",
}

# 道路等级偏移上限校验表（AC07：匹配偏移分位数不得超上限，单位：米）
ROAD_LEVEL_OFFSET_LIMITS = {
    "expressway_ramp": {"limit": 30.0},
    "arterial": {"p95": 25.0, "p99": 35.0},
    "arterial_link": {"p95": 25.0, "p99": 35.0},
    "sub_arterial": {"p95": 20.0, "p99": 30.0},
    "sub_arterial_link": {"p95": 20.0, "p99": 30.0},
    "branch": {"p95": 15.0, "p99": 20.0},
}

# 匹配可参与的道路等级（外卖电动车不匹配到人行道/楼梯等）
MATCHABLE_LEVELS = {
    "expressway", "expressway_ramp", "arterial", "arterial_link",
    "sub_arterial", "sub_arterial_link", "branch", "service_road", "track",
}

# 节点合并精度（UTM 米制，0.01m）
_NODE_PRECISION = 2


# ---------------------------------------------------------------- 工具函数

def _fmt_node(x: float, y: float) -> tuple[float, float]:
    return (round(float(x), _NODE_PRECISION), round(float(y), _NODE_PRECISION))


def _bearing(x1: float, y1: float, x2: float, y2: float) -> float | None:
    """UTM 平面方位角：以正北为 0°，顺时针 0~360°。零向量返回 None。"""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0.0 and dy == 0.0:
        return None
    return math.degrees(math.atan2(dx, dy)) % 360.0


def _iter_lines(geom) -> list[LineString]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, MultiLineString):
        return [g for g in geom.geoms if g is not None and not g.is_empty]
    if isinstance(geom, LineString):
        return [geom]
    return []


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- 图构建

def _build_graph(net: gpd.GeoDataFrame) -> tuple[nx.MultiGraph, list[dict]]:
    """将 UTM 路段构建为无向 MultiGraph，逐边保留方向/等级/几何属性。"""
    G = nx.MultiGraph()
    records: list[dict] = []
    for i, row in net.iterrows():
        for g in _iter_lines(row.geometry):
            coords = list(g.coords)
            if len(coords) < 2 or g.length <= 0.0:
                continue
            x1, y1 = coords[0][0], coords[0][1]
            x2, y2 = coords[-1][0], coords[-1][1]
            u, v = _fmt_node(x1, y1), _fmt_node(x2, y2)
            if u == v and len(coords) == 2 and g.length < 0.5:
                continue  # 退化零长边
            oneway = str(row.get("oneway") or "B").upper()
            fclass = row.get("fclass")
            level = ROAD_LEVEL_MAP.get(str(fclass), "unknown")
            fb = _bearing(x1, y1, x2, y2)
            rb = None if fb is None else (fb + 180.0) % 360.0
            maxspeed = row.get("maxspeed")
            attrs = {
                "osm_id": row.get("osm_id"),
                "fclass": fclass,
                "road_level": level,
                "matchable": level in MATCHABLE_LEVELS,
                "oneway": oneway,
                "name": row.get("name"),
                "maxspeed": float(maxspeed) if maxspeed else None,
                "length_m": round(float(g.length), 3),
                "forward_bearing": fb,
                "reverse_bearing": rb,
                "geometry": LineString(coords),
            }
            key = G.add_edge(u, v, **attrs)
            records.append({
                "u": f"{u[0]},{u[1]}",
                "v": f"{v[0]},{v[1]}",
                "k": int(key),
                "osm_id": attrs["osm_id"],
                "fclass": fclass,
                "road_level": level,
                "oneway": oneway,
                "name": attrs["name"],
                "length_m": attrs["length_m"],
                "geometry": g,
            })
    return G, records


# ---------------------------------------------------------------- 版本管理

def build_from_shapefile(shapefile_path: Path | str = DEFAULT_SOURCE,
                         bbox: tuple = YIZHUANG_BBOX,
                         name: str = "yizhuang") -> dict:
    """导入 shapefile → bbox 裁剪 → UTM 投影 → 建图 → 不可变落盘。

    幂等：相同（源文件 + bbox）生成相同 net_id，已存在则直接返回已有 meta。
    返回路网 meta dict。
    """
    t0 = time.time()
    shapefile_path = Path(shapefile_path)
    if not shapefile_path.exists():
        raise FileNotFoundError(f"路网源文件不存在: {shapefile_path}")

    # 幂等 net_id：源文件指纹 + bbox
    st = shapefile_path.stat()
    h = hashlib.md5(
        f"{shapefile_path}|{st.st_size}|{st.st_mtime_ns}|{bbox}".encode()
    ).hexdigest()[:8]
    net_id = f"RN-{datetime.now():%Y%m%d}-{h}"
    out_dir = roadnet_dir(net_id)
    meta_path = out_dir / "meta.json"
    if meta_path.exists():  # 不可变目录，已构建直接返回
        return json.loads(meta_path.read_text(encoding="utf-8"))

    # 1) 读取 + 统一 WGS84（M0 勘验：源数据 datum 为 WGS84，仅 crs 标注缺失）
    raw = gpd.read_file(shapefile_path)
    raw = raw[raw.geometry.notna() & ~raw.geometry.is_empty].copy()
    raw = raw.set_crs("EPSG:4326", allow_override=True)

    # 2) bbox 裁剪（保留与 bbox 相交的整条路段，不切割以维持拓扑完整）
    bbox_geom = box(*bbox)
    hit_idx = raw.sindex.query(bbox_geom, predicate="intersects")
    clipped = raw.iloc[sorted(hit_idx)].copy()
    if clipped.empty:
        raise ValueError(f"bbox {bbox} 内无任何路段")

    # 3) WGS84 → UTM 50N（D4）
    net = clipped.to_crs(TARGET_CRS)

    # 4) 构图
    G, records = _build_graph(net)
    if G.number_of_edges() == 0:
        raise ValueError("构图结果为空")

    # 5) 不可变落盘
    out_dir.mkdir(parents=True, exist_ok=True)
    edges_gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=TARGET_CRS)
    edges_gdf.to_file(out_dir / "network.gpkg", driver="GPKG", layer="edges")
    with open(out_dir / "graph.pkl", "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

    meta = {
        "net_id": net_id,
        "name": name,
        "source": str(shapefile_path.relative_to(ROOT_DIR))
        if shapefile_path.is_relative_to(ROOT_DIR) else str(shapefile_path),
        "source_features": int(len(raw)),
        "clipped_features": int(len(net)),
        "bbox_wgs84": [float(v) for v in bbox],
        "crs": TARGET_CRS,
        "node_count": int(G.number_of_nodes()),
        "edge_count": int(G.number_of_edges()),
        "total_length_km": round(
            sum(d["length_m"] for _, _, d in G.edges(data=True)) / 1000.0, 2),
        "road_level_counts": dict(Counter(
            d["road_level"] for _, _, d in G.edges(data=True))),
        "oneway_counts": dict(Counter(
            d["oneway"] for _, _, d in G.edges(data=True))),
        "offset_limits": ROAD_LEVEL_OFFSET_LIMITS,
        "rule_version": RULE_VERSION,
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "build_seconds": round(time.time() - t0, 1),
    }
    _write_json(meta_path, meta)
    _GRAPH_CACHE[net_id] = (G, meta)
    return meta


_GRAPH_CACHE: dict[str, tuple] = {}


def load_network(net_id: str, force_reload: bool = False) -> tuple:
    """加载路网 → (MultiGraph, meta)，带进程内缓存。"""
    if not force_reload and net_id in _GRAPH_CACHE:
        return _GRAPH_CACHE[net_id]
    d = roadnet_dir(net_id)
    gpath, mpath = d / "graph.pkl", d / "meta.json"
    if not gpath.exists() or not mpath.exists():
        raise FileNotFoundError(f"路网版本不存在: {net_id}")
    with open(gpath, "rb") as f:
        G = pickle.load(f)
    meta = json.loads(mpath.read_text(encoding="utf-8"))
    _GRAPH_CACHE[net_id] = (G, meta)
    return G, meta


def list_networks() -> list[dict]:
    """列出所有路网版本（按 built_at 升序）。"""
    out = []
    for meta_path in sorted(ROADNET_DIR.glob("*/meta.json")):
        try:
            out.append(json.loads(meta_path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return sorted(out, key=lambda m: m.get("built_at", ""))


def latest_network_id() -> str | None:
    nets = list_networks()
    return nets[-1]["net_id"] if nets else None


def get_or_build_default() -> tuple:
    """取最新路网；无则从默认 shapefile 构建（bootstrap 用）。"""
    net_id = latest_network_id()
    if net_id is None:
        meta = build_from_shapefile()
        net_id = meta["net_id"]
    return load_network(net_id)


# ---------------------------------------------------------------- 自测

if __name__ == "__main__":
    _meta = build_from_shapefile()
    print(json.dumps(_meta, ensure_ascii=False, indent=2))
    _G, _m = load_network(_meta["net_id"])
    print(f"reload ok: nodes={_G.number_of_nodes()} edges={_G.number_of_edges()}")
