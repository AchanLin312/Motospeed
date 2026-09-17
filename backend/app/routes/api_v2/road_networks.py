"""#3 POST /road-networks 【管理】—— shapefile 上传构建路网版本
   #4 GET  /road-networks        —— 路网版本列表
"""
import tempfile
import zipfile
from pathlib import Path

from flask import request

from . import api_v2_bp
from .common import ok, err, admin_required
from ...services.v2.road_network_service import (
    build_from_shapefile, list_networks, latest_network_id,
)


def _extract_shapefile(zpath: Path, td: str) -> Path:
    """解压 zip，返回 .shp 路径（shapefile 组件须同目录）。"""
    with zipfile.ZipFile(zpath) as zf:
        names = zf.namelist()
        if not any(n.lower().endswith(".shp") for n in names):
            raise ValueError("压缩包内未找到 .shp 文件")
        zf.extractall(td)
    shps = list(Path(td).rglob("*.shp"))
    return shps[0]


@api_v2_bp.post("/road-networks")
@admin_required
def upload_road_network():
    """上传路网 shapefile（zip），bbox 裁剪建图落盘（幂等）。

    亦支持 JSON {"shapefile_path": "..."} 直接引用服务器本地文件。
    """
    f = request.files.get("file")
    try:
        if f is not None and f.filename:
            suffix = Path(f.filename).suffix
            with tempfile.TemporaryDirectory() as td:
                if suffix.lower() == ".zip":
                    zp = Path(td) / "net.zip"
                    f.save(str(zp))
                    shp = _extract_shapefile(zp, td)
                    name = request.form.get("name") or Path(f.filename).stem
                    meta = build_from_shapefile(shp, name=name)
                elif suffix.lower() == ".shp":
                    p = Path(td) / f.filename
                    f.save(str(p))
                    name = request.form.get("name") or p.stem
                    meta = build_from_shapefile(p, name=name)
                else:
                    return err("仅支持 .zip（shapefile 打包）或 .shp 上传", 400)
        else:
            payload = request.get_json(silent=True) or {}
            shp = payload.get("shapefile_path")
            if not shp:
                return err("缺少文件字段 file 或 JSON 字段 shapefile_path", 400)
            meta = build_from_shapefile(shp, name=payload.get("name") or "custom")
    except (ValueError, FileNotFoundError) as e:
        return err(str(e), 422)
    except zipfile.BadZipFile:
        return err("压缩包损坏，无法解压", 422)
    except Exception as e:  # noqa: BLE001
        return err(f"路网构建失败：{e}", 400)
    return ok(meta, 201)


@api_v2_bp.get("/road-networks")
def get_road_networks():
    nets = list_networks()
    return ok({"road_networks": nets, "latest": latest_network_id(),
               "count": len(nets)})
