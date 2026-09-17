"""M2 行为识别服务：超速 / 疑似逆行 / 急加速急减速。

规则（需求手册 V1.0，RULE_VERSION 对齐）：
1. 超速：速度 > 20 km/h 且连续持续 >= 10 s（逐点判定，连续段 end-start 达标即事件）
2. 疑似逆行（仅对已匹配点）：
   - 单向路（oneway=F 沿绘制方向 / T 反向，M0 实证）：观测航向与规定方向角差
     落在 [135°, 225°] → 逆行点
   - 双向路（B）：叉积判定车辆位于道路前进方向左侧（中国靠右行驶）→ 逆行点
   - 子链内逆行点占比 > 50% → 疑似逆行事件（子链级）
3. 急变速：相邻点间隔 <= 6 s 才可判定（不插值）；
   - 运动样本（前后点均 >= 0.5 m/s）的加速度分布：P85 = 急加速阈值、P15 = 急减速阈值
   - 排除急启动：v_from < 0.5 m/s 的加速对不判急加速
输出：analysis/<version>/events.csv + behavior_meta.json
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import (OVERSPEED_MIN_DURATION_S, OVERSPEED_MIN_POINTS,
               OVERSPEED_THRESHOLD_KMH, RAPID_ACCEL_QUANTILE,
               RAPID_DECEL_QUANTILE, RAPID_MAX_INTERVAL_S,
               REVERSE_ALPHA_D, REVERSE_HIGH, REVERSE_LOW,
               REVERSE_SUBCHAIN_RATIO, RULE_VERSION, analysis_dir, batch_dir)

MOVING_SPEED_MPS = 0.5  # 运动样本下限（排除静止抖动与急启动）

_EVENT_TYPES = ("overspeed", "reverse", "rapid_accel", "rapid_decel")


# ---------------------------------------------------------------- 工具

def _angdiff(a: float, b: float) -> float:
    """角差绝对值 0~180。"""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _bearing_vec(theta_deg: float) -> tuple[float, float]:
    """北基准顺时针方位角 → 单位向量 (x, y)（UTM 东/北）。"""
    r = math.radians(theta_deg)
    return math.sin(r), math.cos(r)


# ---------------------------------------------------------------- 超速

def detect_overspeed(traj: pd.DataFrame,
                     threshold_kmh: float = OVERSPEED_THRESHOLD_KMH,
                     min_duration_s: float = OVERSPEED_MIN_DURATION_S,
                     min_points: int = OVERSPEED_MIN_POINTS) -> list[dict]:
    """全轨迹超速事件。traj 需含 segment_id/point_order/time/speed_kmh/
    vehicle_id/lon/lat，按 segment 分组逐点扫描连续超速段。"""
    events: list[dict] = []
    df = traj.copy()
    df["_t"] = pd.to_datetime(df["time"], format="mixed")
    df = df.sort_values(["segment_id", "point_order"])
    for seg_id, grp in df.groupby("segment_id", sort=False):
        times = grp["_t"].tolist()
        speeds = pd.to_numeric(grp["speed_kmh"], errors="coerce").tolist()
        runs, cur = [], None
        for i, v in enumerate(speeds):
            if pd.notna(v) and v > threshold_kmh:  # 严格大于（AC：20.00 不触发）
                if cur is None:
                    cur = [i, i]
                else:
                    cur[1] = i
            elif cur is not None:
                runs.append(cur)
                cur = None
        if cur is not None:
            runs.append(cur)
        for s, e in runs:
            duration = (times[e] - times[s]).total_seconds()
            if duration < min_duration_s or (e - s + 1) < min_points:
                continue
            peak_i = max(range(s, e + 1), key=lambda j: speeds[j])
            peak = grp.iloc[peak_i]
            events.append({
                "event_type": "overspeed",
                "vehicle_id": grp["vehicle_id"].iloc[0],
                "segment_id": seg_id,
                "start_time": times[s].strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": times[e].strftime("%Y-%m-%d %H:%M:%S"),
                "duration_s": round(duration, 1),
                "value_main": round(float(speeds[peak_i]), 2),  # 峰值 km/h
                "lon": float(peak["lon"]),
                "lat": float(peak["lat"]),
                "detail": json.dumps({
                    "peak_kmh": round(float(speeds[peak_i]), 2),
                    "threshold_kmh": threshold_kmh,
                    "n_points": e - s + 1,
                }, ensure_ascii=False),
            })
    return events


# ---------------------------------------------------------------- 疑似逆行

def _is_reverse_point(oneway: str, obs_bearing: float,
                      seg_bearing: float) -> bool | None:
    """单点逆行判定。oneway=B 用叉积左侧判定；F/T 用角差区间。
    返回 None 表示信息不足（角度缺失）。"""
    if obs_bearing is None or seg_bearing is None or pd.isna(obs_bearing) or pd.isna(seg_bearing):
        return None
    oneway = str(oneway or "B").upper()
    if oneway == "B":
        vx, vy = _bearing_vec(float(obs_bearing))
        rx, ry = _bearing_vec(float(seg_bearing))
        cross = vx * ry - vy * rx
        return cross > 0.0  # 车辆位于道路前进方向左侧（靠右行驶原则）
    road_dir = float(seg_bearing) if oneway == "F" else (float(seg_bearing) + 180.0) % 360.0
    diff = _angdiff(float(obs_bearing), road_dir)
    return REVERSE_LOW <= diff <= REVERSE_HIGH  # [135,225]，AC：134.9/225.1 不判


def detect_reverse(matched: pd.DataFrame,
                   ratio_threshold: float = REVERSE_SUBCHAIN_RATIO) -> list[dict]:
    """疑似逆行事件（子链级）。matched 需含 matched/oneway/obs_bearing/
    seg_bearing/road_level/vehicle_id/segment_id/time/lon/lat。"""
    events: list[dict] = []
    df = matched.copy()
    df["_t"] = pd.to_datetime(df["time"], format="mixed")
    df = df.sort_values(["segment_id", "point_order"])
    for seg_id, grp in df.groupby("segment_id", sort=False):
        flags: list[bool] = []
        for _, r in grp.iterrows():
            if int(r.get("matched", 0)) != 1:
                continue
            f = _is_reverse_point(r.get("oneway"), r.get("obs_bearing"),
                                  r.get("seg_bearing"))
            if f is not None:
                flags.append(f)
        n_judge = len(flags)
        if n_judge == 0:
            continue
        n_rev = sum(flags)
        ratio = n_rev / n_judge
        if ratio <= ratio_threshold:  # 严格大于（AC：50% 不触发）
            continue
        road = grp.iloc[0]
        mid = grp.iloc[len(grp) // 2]
        events.append({
            "event_type": "reverse",
            "vehicle_id": grp["vehicle_id"].iloc[0],
            "segment_id": seg_id,
            "start_time": grp["_t"].iloc[0].strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": grp["_t"].iloc[-1].strftime("%Y-%m-%d %H:%M:%S"),
            "duration_s": round((grp["_t"].iloc[-1] - grp["_t"].iloc[0]).total_seconds(), 1),
            "value_main": round(ratio, 4),  # 逆行点占比
            "lon": float(mid["lon"]),
            "lat": float(mid["lat"]),
            "detail": json.dumps({
                "ratio": round(ratio, 4), "n_reverse": n_rev, "n_judged": n_judge,
                "oneway": road.get("oneway"),
                "road_level": road.get("road_level", ""),
            }, ensure_ascii=False),
        })
    return events


# ---------------------------------------------------------------- 急变速

def compute_accel_thresholds(traj: pd.DataFrame) -> dict:
    """全批运动样本加速度分布 → P85/P15 阈值。"""
    df = traj.copy()
    df["_t"] = pd.to_datetime(df["time"], format="mixed")
    df = df.sort_values(["segment_id", "point_order"])
    accels: list[float] = []
    for _, grp in df.groupby("segment_id", sort=False):
        t = grp["_t"].tolist()
        v = pd.to_numeric(grp["speed_mps"], errors="coerce").tolist()
        for i in range(1, len(grp)):
            dt = (t[i] - t[i - 1]).total_seconds()
            if dt <= 0 or dt > RAPID_MAX_INTERVAL_S:  # AC：6.1s 不可判定
                continue
            v0, v1 = v[i - 1], v[i]
            if pd.isna(v0) or pd.isna(v1):
                continue
            if v0 >= MOVING_SPEED_MPS and v1 >= MOVING_SPEED_MPS:  # 运动样本
                accels.append((v1 - v0) / dt)
    if not accels:
        return {"accel_threshold_mps2": None, "decel_threshold_mps2": None,
                "n_motion_samples": 0}
    s = pd.Series(accels)
    return {
        "accel_threshold_mps2": round(float(s.quantile(RAPID_ACCEL_QUANTILE)), 3),
        "decel_threshold_mps2": round(float(s.quantile(RAPID_DECEL_QUANTILE)), 3),
        "n_motion_samples": int(len(accels)),
    }


def detect_rapid(traj: pd.DataFrame, accel_th: float,
                 decel_th: float) -> list[dict]:
    """急加速/急减速事件（单采样间隔级）。"""
    if accel_th is None or decel_th is None:
        return []
    events: list[dict] = []
    df = traj.copy()
    df["_t"] = pd.to_datetime(df["time"], format="mixed")
    df = df.sort_values(["segment_id", "point_order"])
    for seg_id, grp in df.groupby("segment_id", sort=False):
        t = grp["_t"].tolist()
        v = pd.to_numeric(grp["speed_mps"], errors="coerce").tolist()
        for i in range(1, len(grp)):
            dt = (t[i] - t[i - 1]).total_seconds()
            if dt <= 0 or dt > RAPID_MAX_INTERVAL_S:
                continue
            v0, v1 = v[i - 1], v[i]
            if pd.isna(v0) or pd.isna(v1):
                continue
            a = (v1 - v0) / dt
            p = grp.iloc[i]
            if a > accel_th:
                if v0 < MOVING_SPEED_MPS:
                    continue  # 排除急启动
                etype = "rapid_accel"
            elif a < decel_th:
                etype = "rapid_decel"
            else:
                continue
            events.append({
                "event_type": etype,
                "vehicle_id": grp["vehicle_id"].iloc[0],
                "segment_id": seg_id,
                "start_time": t[i - 1].strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": t[i].strftime("%Y-%m-%d %H:%M:%S"),
                "duration_s": round(dt, 1),
                "value_main": round(a, 3),  # m/s²
                "lon": float(p["lon"]),
                "lat": float(p["lat"]),
                "detail": json.dumps({
                    "a_mps2": round(a, 3),
                    "from_kmh": round(v0 * 3.6, 2), "to_kmh": round(v1 * 3.6, 2),
                    "dt_s": round(dt, 1),
                }, ensure_ascii=False),
            })
    return events


# ---------------------------------------------------------------- 主入口

def run_behavior(analysis_version: str) -> dict:
    """读取匹配结果与轨迹，输出三类行为事件（events.csv + behavior_meta.json）。"""
    adir = analysis_dir(analysis_version)
    matched = pd.read_csv(adir / "matched_points.csv", encoding="utf-8-sig",
                          dtype={"vehicle_id": str, "segment_id": str})
    mm = json.loads((adir / "match_meta.json").read_text(encoding="utf-8"))
    traj = pd.read_csv(batch_dir(mm["batch_id"]) / "trajectory.csv",
                       encoding="utf-8-sig",
                       dtype={"vehicle_id": str, "segment_id": str})

    events: list[dict] = []
    th = compute_accel_thresholds(traj)
    events += detect_overspeed(traj)
    events += detect_reverse(matched)
    events += detect_rapid(traj, th["accel_threshold_mps2"], th["decel_threshold_mps2"])

    out = pd.DataFrame(events)
    if len(out):
        out = out.sort_values(["event_type", "start_time"]).reset_index(drop=True)
        out.insert(0, "event_id", [f"EV-{i + 1:06d}" for i in range(len(out))])
    out.to_csv(adir / "events.csv", index=False, encoding="utf-8-sig")

    counts = out["event_type"].value_counts().to_dict() if len(out) else {}
    meta = {
        "analysis_version": analysis_version,
        "rule_version": RULE_VERSION,
        "params": {
            "overspeed_kmh": OVERSPEED_THRESHOLD_KMH,
            "overspeed_min_s": OVERSPEED_MIN_DURATION_S,
            "reverse_deg": [REVERSE_LOW, REVERSE_HIGH],
            "reverse_ratio": REVERSE_SUBCHAIN_RATIO,
            "rapid_max_interval_s": RAPID_MAX_INTERVAL_S,
            "accel_quantile": RAPID_ACCEL_QUANTILE,
            "decel_quantile": RAPID_DECEL_QUANTILE,
            "moving_speed_mps": MOVING_SPEED_MPS,
        },
        "accel_thresholds": th,
        "event_counts": {k: int(v) for k, v in counts.items()},
        "total_events": int(len(out)),
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }
    (adir / "behavior_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def _batch_of(adir: Path) -> str:
    meta = json.loads((adir / "match_meta.json").read_text(encoding="utf-8"))
    return meta["batch_id"]


# ---------------------------------------------------------------- 8 组边界自测

def _selftest() -> None:
    import numpy as np

    t0 = datetime(2024, 6, 5, 8, 0, 0)

    def mk_traj(speeds_kmh: list[float], dt_s: list[float], speed_mps=None):
        times = []
        acc = 0.0
        for d in dt_s:
            times.append(t0.timestamp() + acc)
            acc += d
        times.append(t0.timestamp() + acc)
        n = len(speeds_kmh)
        return pd.DataFrame({
            "segment_id": ["S1"] * n, "point_order": range(n),
            "vehicle_id": ["V1"] * n,
            "time": [datetime.fromtimestamp(t).isoformat(sep=" ") for t in times[:n]],
            "lon": [116.5 + i * 1e-5 for i in range(n)],
            "lat": [39.75 + i * 1e-5 for i in range(n)],
            "speed_kmh": speeds_kmh,
            "speed_mps": speed_mps if speed_mps is not None else [s / 3.6 for s in speeds_kmh],
        })

    # 组1 速度边界：19.99/20.00 不触发，20.01 触发
    df = mk_traj([19.99, 20.00, 20.01, 20.01], [5, 5, 5, 5])
    ev = detect_overspeed(df, threshold_kmh=20.0, min_duration_s=0.0, min_points=1)
    assert len(ev) == 1 and ev[0]["start_time"].endswith("08:00:10"), "组1失败"
    print("组1 超速速度边界 OK")

    # 组2 时长边界：9.9s 不触发 / 10.0s 触发 / 10.1s 触发
    for dt, expect in ((4.95, 0), (5.0, 1), (5.05, 1)):
        df = mk_traj([20.01, 20.01, 20.01], [dt, dt])
        ev = detect_overspeed(df, threshold_kmh=20.0, min_duration_s=10.0, min_points=2)
        assert len(ev) == expect, f"组2失败 dt={dt}"
    print("组2 超速时长边界 OK")

    # 组3 角差边界（单向路 F）：134.9 不判 / 135 判 / 180 判 / 225 判 / 225.1 不判
    for obs, expect in ((134.9, False), (135.0, True), (180.0, True),
                        (225.0, True), (225.1, False)):
        assert _is_reverse_point("F", obs, 0.0) is expect, f"组3失败 obs={obs}"
    print("组3 逆行角差边界 OK")

    # 组4 子链占比边界（双向叉积左侧）：49.9% 不判 / 50% 不判 / 50.1% 判
    # 道路向北(seg=0)，车辆向东(obs=90) → cross>0 左侧=逆行点
    def build_md(n_rev: int) -> pd.DataFrame:
        return pd.DataFrame({
            "segment_id": "S1", "point_order": range(1000), "vehicle_id": "V1",
            "time": "2024-06-05 08:00:00", "matched": 1, "oneway": "B",
            "obs_bearing": [90.0] * n_rev + [270.0] * (1000 - n_rev),
            "seg_bearing": 0.0,
            "road_level": "branch", "lon": 116.5, "lat": 39.75,
        })
    for n_rev, expect in ((499, 0), (500, 0), (501, 1)):
        ev = detect_reverse(build_md(n_rev))
        assert len(ev) == expect, f"组4失败 n_rev={n_rev}"
    print("组4 逆行占比边界 OK")

    # 组5 采样间隔边界：5.9/6.0 有效 / 6.1 无效（10→5 m/s 减速对）
    for dt, expect in ((5.9, 1), (6.0, 1), (6.1, 0)):
        df = mk_traj([36.0, 18.0], [dt, dt], speed_mps=[10.0, 5.0])
        ev = detect_rapid(df, accel_th=99.0, decel_th=-0.01)
        assert len(ev) == expect, f"组5失败 dt={dt}"
    print("组5 急变速间隔边界 OK")

    # 组6 P85/P15 阈值计算
    rng = np.random.default_rng(7)
    n = 1000
    sp = np.abs(rng.normal(5, 1, n)).tolist()
    df = mk_traj((np.array(sp) * 3.6).tolist(), [5.0] * n, speed_mps=sp)
    th = compute_accel_thresholds(df)
    assert th["n_motion_samples"] == n - 1, "组6失败：运动样本数"
    assert th["accel_threshold_mps2"] > 0 and th["decel_threshold_mps2"] < 0, "组6失败：阈值符号"
    print(f"组6 P85/P15 阈值 OK ({th})")

    # 组7 急启动排除：v_from=0.3 m/s 的加速对不判
    df = mk_traj([1.0, 20.0], [5, 5], speed_mps=[0.3, 5.0])
    ev = detect_rapid(df, accel_th=0.5, decel_th=-99.0)
    assert len(ev) == 0, "组7失败"
    print("组7 急启动排除 OK")

    # 组8 综合冒烟：超速 + 逆行 + 急减速同链
    df = mk_traj([10, 30, 5, 22, 22, 22], [5, 5, 5, 5, 5, 5])
    ev = detect_overspeed(df, threshold_kmh=20.0, min_duration_s=10.0, min_points=2)
    assert len(ev) == 1, "组8失败：超速"
    ev = detect_rapid(df, accel_th=0.5, decel_th=-0.5)
    assert any(e["event_type"] == "rapid_decel" for e in ev), "组8失败：急减速"
    print("组8 综合冒烟 OK")

    print("\n全部 8 组边界用例通过 ✓")


if __name__ == "__main__":
    _selftest()
