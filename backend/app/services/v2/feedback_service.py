"""一线反馈模块（甲方第三次需求 五）：现场核查结果留存、台账、复核提示与效果对比。

存储（不引数据库，落盘即可复现）：
    outputs/runtime/v2/feedback/feedback.jsonl   每行一条反馈记录
    outputs/runtime/v2/feedback/photos/          随反馈上传的照片（重命名保存）

效果对比口径：以最近一次处置日 T 为界，网格内事件按 [T-14, T) 与 [T, T+14)
两个 14 天窗口计算"件/天"；治理后窗口超出数据覆盖范围时返回 insufficient，
不把"没有数据"当成"风险下降"。
"""
from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from . import V2_DIR, analysis_dir

log = logging.getLogger("v2.feedback")

FEEDBACK_DIR = V2_DIR / "feedback"
PHOTO_DIR = FEEDBACK_DIR / "photos"
RECORD_PATH = FEEDBACK_DIR / "feedback.jsonl"

CONCLUSIONS = ("成立", "部分成立", "不成立")
MAX_PHOTOS = 3
MAX_PHOTO_MB = 5
ALLOWED_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}
WINDOW_DAYS = 14

# 网格事件范围过滤口径（与 advice_service._reverse_oneway_ratio 保持一致）
_GRID_DLON = 0.0016
_GRID_DLAT = 0.0012

_CSV_COLUMNS = ["反馈编号", "分析版本", "网格编号", "处置时间", "核查结论",
                "现场情况", "已采取措施", "责任单位", "反馈人", "补充说明",
                "照片", "提交时间"]


def _ensure_dirs() -> None:
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)


def add_feedback(analysis_version: str, grid_id: str, form, photos) -> dict:
    """保存一条反馈；photos 为 (原始文件名, 字节) 列表，重命名后落盘。

    form 为 werkzeug 的 ImmutableMultiDict；scene_issues/measures 用换行分隔。
    校验失败抛 ValueError，由路由转换为 422。
    """
    conclusion = (form.get("conclusion") or "").strip()
    if conclusion not in CONCLUSIONS:
        raise ValueError(f"核查结论必须是 {'/'.join(CONCLUSIONS)} 之一")
    handled_at = (form.get("handled_at") or "").strip()
    try:
        datetime.strptime(handled_at, "%Y-%m-%d")
    except ValueError:
        raise ValueError("处置时间格式应为 YYYY-MM-DD")

    _ensure_dirs()
    saved_photos = []
    if len(photos) > MAX_PHOTOS:
        raise ValueError(f"照片最多上传 {MAX_PHOTOS} 张")
    for name, blob in photos:
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_PHOTO_EXT:
            raise ValueError(f"照片格式不支持: {name}")
        if len(blob) > MAX_PHOTO_MB * 1024 * 1024:
            raise ValueError(f"照片超过 {MAX_PHOTO_MB}MB: {name}")
        fname = f"{uuid.uuid4().hex}{ext}"
        (PHOTO_DIR / fname).write_bytes(blob)
        saved_photos.append(fname)

    def _split(key: str) -> list[str]:
        raw = form.get(key) or ""
        return [s.strip() for s in raw.split("\n") if s.strip()]

    rec = {
        "feedback_id": f"FB-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}",
        "analysis_version": analysis_version,
        "grid_id": grid_id,
        "handled_at": handled_at,
        "conclusion": conclusion,
        "scene_issues": _split("scene_issues"),
        "measures": _split("measures"),
        "responsible_unit": (form.get("responsible_unit") or "").strip(),
        "reporter": (form.get("reporter") or "").strip() or "值班民警",
        "note": (form.get("note") or "").strip(),
        "photos": saved_photos,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    with RECORD_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log.info("feedback added av=%s grid=%s conclusion=%s",
             analysis_version, grid_id, conclusion)
    return rec


def list_feedback(analysis_version: str | None = None, grid_id: str | None = None,
                  conclusion: str | None = None, date_from: str | None = None,
                  date_to: str | None = None, limit: int = 500) -> list[dict]:
    """反馈台账（按处置时间倒序）。"""
    if not RECORD_PATH.exists():
        return []
    rows = []
    for line in RECORD_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if analysis_version and rec.get("analysis_version") != analysis_version:
            continue
        if grid_id and rec.get("grid_id") != grid_id:
            continue
        if conclusion and rec.get("conclusion") != conclusion:
            continue
        if date_from and rec.get("handled_at", "") < date_from:
            continue
        if date_to and rec.get("handled_at", "") > date_to:
            continue
        rows.append(rec)
    rows.sort(key=lambda r: (r.get("handled_at", ""), r.get("created_at", "")),
              reverse=True)
    return rows[:limit]


def export_feedback(**filters) -> str:
    """台账导出 CSV（带 BOM，Excel 直接打开不乱码）。"""
    rows = list_feedback(**filters)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_CSV_COLUMNS)
    for r in rows:
        writer.writerow([
            r.get("feedback_id", ""), r.get("analysis_version", ""),
            r.get("grid_id", ""), r.get("handled_at", ""), r.get("conclusion", ""),
            "；".join(r.get("scene_issues", [])),
            "；".join(r.get("measures", [])),
            r.get("responsible_unit", ""), r.get("reporter", ""),
            r.get("note", ""), "；".join(r.get("photos", [])),
            r.get("created_at", ""),
        ])
    return "\ufeff" + buf.getvalue()


def feedback_stats(analysis_version: str, grid_id: str) -> dict:
    """网格核查状态：是否已核查、连续"不成立"复核提示、治理前后事件率对比。"""
    recs = list_feedback(analysis_version=analysis_version, grid_id=grid_id)
    latest = recs[0] if recs else None  # list_feedback 已按时间倒序
    checked = {"checked": bool(recs), "count": len(recs),
               "latest_conclusion": latest["conclusion"] if latest else None,
               "latest_handled_at": latest["handled_at"] if latest else None}

    # 连续 3 条"不成立"→ 建议人工复核判定规则（只提示，不自动改，甲方需求 五-4）
    streak = 0
    for r in recs:
        if r.get("conclusion") == "不成立":
            streak += 1
        else:
            break
    review_flag = {"flag": streak >= 3, "streak": streak}

    change = _event_rate_change(analysis_version, grid_id,
                                latest["handled_at"] if latest else None)
    return {"checked": checked, "review_flag": review_flag, "change": change}


def _event_rate_change(analysis_version: str, grid_id: str,
                       handled_at: str | None) -> dict:
    """以处置日 T 为界，对比 [T-14,T) 与 [T,T+14) 的网格事件率（件/天）。"""
    if not handled_at:
        return {"status": "insufficient", "note": "暂无反馈，无法对比",
                "before_per_day": None, "after_per_day": None, "pct": None}
    try:
        t = datetime.strptime(handled_at, "%Y-%m-%d").date()
    except ValueError:
        return {"status": "insufficient", "note": "处置时间无效",
                "before_per_day": None, "after_per_day": None, "pct": None}
    adir = analysis_dir(analysis_version)
    epath, gpath = adir / "events.csv", adir / "grid_metrics.csv"
    if not epath.exists() or not gpath.exists():
        return {"status": "insufficient", "note": "缺少分析结果数据",
                "before_per_day": None, "after_per_day": None, "pct": None}
    try:
        ev = pd.read_csv(epath, encoding="utf-8-sig",
                         usecols=["event_type", "start_time", "lon", "lat"])
        gm = pd.read_csv(gpath, encoding="utf-8-sig", dtype={"grid_id": str})
    except (ValueError, pd.errors.ParserError, OSError):
        return {"status": "insufficient", "note": "事件数据不可读",
                "before_per_day": None, "after_per_day": None, "pct": None}
    row = gm[gm["grid_id"] == grid_id]
    if row.empty:
        return {"status": "insufficient", "note": "网格不存在",
                "before_per_day": None, "after_per_day": None, "pct": None}
    lon = float(row.iloc[0]["center_lon"])
    lat = float(row.iloc[0]["center_lat"])
    ev = ev[(ev["lon"].between(lon - _GRID_DLON, lon + _GRID_DLON)) &
            (ev["lat"].between(lat - _GRID_DLAT, lat + _GRID_DLAT))]
    if ev.empty:
        return {"status": "insufficient", "note": "该网格无事件记录",
                "before_per_day": None, "after_per_day": None, "pct": None}
    ev = ev.assign(day=pd.to_datetime(ev["start_time"], errors="coerce").dt.date)
    ev = ev.dropna(subset=["day"])
    if ev.empty:
        return {"status": "insufficient", "note": "事件时间不可解析",
                "before_per_day": None, "after_per_day": None, "pct": None}

    before = ev[(ev["day"] >= t - timedelta(days=WINDOW_DAYS)) & (ev["day"] < t)]
    after = ev[(ev["day"] >= t) & (ev["day"] < t + timedelta(days=WINDOW_DAYS))]
    insufficient = {"status": "insufficient",
                    "note": "治理后窗口数据未覆盖，待后续批次积累后对比",
                    "before_per_day": round(len(before) / WINDOW_DAYS, 2),
                    "after_per_day": None, "pct": None}
    # 治理后窗口未完整覆盖到数据最后一天 → 不下结论
    if after.empty or ev["day"].max() < t + timedelta(days=WINDOW_DAYS - 1):
        return insufficient
    b = len(before) / WINDOW_DAYS
    a = len(after) / WINDOW_DAYS
    pct = round((a - b) / b * 100, 1) if b else None
    return {"status": "ok", "window_days": WINDOW_DAYS,
            "before_per_day": round(b, 2), "after_per_day": round(a, 2), "pct": pct}
