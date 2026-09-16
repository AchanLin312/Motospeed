"""
地图快照服务。

提供地图快照功能，支持导出PNG/PDF格式的地图图片，
用于警务简报和汇报。
"""
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import json


class MapSnapshotService:
    """地图快照服务。"""

    def __init__(self):
        """初始化快照服务。"""
        self.output_dir = Path("outputs/snapshots")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_snapshot_metadata(
        self,
        map_type: str,
        view_bounds: Optional[Dict[str, float]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        生成快照元数据。

        :param map_type: 地图类型（hotspot/lisa/evolution）
        :param view_bounds: 视图边界
        :param filters: 筛选条件
        :return: 元数据字典
        """
        return {
            "map_type": map_type,
            "timestamp": datetime.now().isoformat(),
            "view_bounds": view_bounds or {},
            "filters": filters or {},
            "data_version": self._get_data_version()
        }

    def _get_data_version(self) -> str:
        """获取数据版本。"""
        summary_file = Path("outputs/runtime/analysis_summary.json")
        if summary_file.exists():
            try:
                with open(summary_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("batch_id", "unknown")
            except:
                pass
        return "unknown"

    def save_snapshot_info(
        self,
        snapshot_path: Path,
        metadata: Dict[str, Any]
    ) -> Path:
        """
        保存快照信息。

        :param snapshot_path: 快照文件路径
        :param metadata: 元数据
        :return: 信息文件路径
        """
        info_file = snapshot_path.with_suffix(".json")
        with open(info_file, "w", encoding="utf-8") as f:
            json.dump({
                "snapshot_file": str(snapshot_path),
                "metadata": metadata
            }, f, ensure_ascii=False, indent=2)
        return info_file

    def list_snapshots(self) -> list:
        """
        列出所有快照。

        :return: 快照列表
        """
        snapshots = []
        for info_file in self.output_dir.glob("*.json"):
            try:
                with open(info_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    snapshots.append({
                        "snapshot_file": data.get("snapshot_file"),
                        "metadata": data.get("metadata", {}),
                        "info_file": str(info_file)
                    })
            except:
                continue
        return sorted(snapshots, key=lambda x: x["metadata"].get("timestamp", ""), reverse=True)


# 全局实例
map_snapshot_service = MapSnapshotService()

