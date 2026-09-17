"""#9 GET /grids/<grid_id> —— 网格详情（指标 + 评分 + 建议可用性）"""
import json

import pandas as pd
from flask import request

from . import api_v2_bp
from .common import ok, err, resolve_analysis_version
from ...services.v2 import analysis_dir


@api_v2_bp.get("/grids/<grid_id>")
def get_grid(grid_id: str):
    av = resolve_analysis_version(request.args.get("analysis_version"))
    if av is None:
        return err("尚无已完成的分析版本，请先执行 #5 POST /analysis", 404)

    gpath = analysis_dir(av) / "grid_metrics.csv"
    if not gpath.exists():
        return err(f"分析 {av} 缺少网格指标，请先执行分析", 409)
    df = pd.read_csv(gpath, encoding="utf-8-sig", dtype={"grid_id": str})
    row = df[df["grid_id"] == grid_id]
    if row.empty:
        return err(f"网格不存在: {grid_id}", 404)
    rec = row.iloc[0].where(pd.notna(row.iloc[0]), None).to_dict()

    advice_path = analysis_dir(av) / "advice" / f"{grid_id}.json"
    rec["advice_available"] = advice_path.exists()
    if advice_path.exists():
        rec["advice_id"] = json.loads(
            advice_path.read_text(encoding="utf-8")).get("advice_id")

    return ok({"analysis_version": av, "grid": rec})
