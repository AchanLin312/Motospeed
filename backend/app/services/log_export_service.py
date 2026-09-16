"""
日志导出服务。

支持将用户操作、反馈、分析记录导出为CSV格式，
便于警务工作留痕和日志撰写。
"""
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import csv
import json
import base64
from io import StringIO


class LogExportService:
    """日志导出服务。"""

    def __init__(self):
        """初始化日志服务。"""
        # 使用绝对路径，从项目根目录开始
        # __file__ 是 backend/app/services/log_export_service.py
        # parents[0] = backend/app/services/
        # parents[1] = backend/app/
        # parents[2] = backend/
        # parents[3] = 项目根目录
        current_file = Path(__file__).resolve()
        project_root = current_file.parents[3]  # 从backend/app/services/到项目根目录
        
        # 验证路径是否正确（检查是否存在backend目录）
        if not (project_root / "backend").exists():
            # 如果路径不正确，尝试从当前文件向上查找
            for parent in current_file.parents:
                if (parent / "backend").exists():
                    project_root = parent
                    break
        
        self.output_dir = project_root / "outputs" / "logs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.output_dir / "operation_logs.json"

    def log_operation(
        self,
        operation_type: str,
        user: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        记录操作日志。

        :param operation_type: 操作类型（upload/analysis/export/feedback等）
        :param user: 用户标识
        :param details: 操作详情
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "operation_type": operation_type,
            "user": user or "system",
            "details": details or {}
        }

        # 读取现有日志
        logs = []
        if self.log_file.exists():
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except:
                logs = []

        # 添加新日志
        logs.append(log_entry)

        # 保存日志
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

    def export_logs_to_csv(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        operation_types: Optional[List[str]] = None,
        include_feedback: bool = True,
        include_images: bool = True
    ) -> Path:
        """
        导出日志为CSV文件。

        :param start_date: 开始日期（ISO格式）
        :param end_date: 结束日期（ISO格式）
        :param operation_types: 操作类型筛选
        :param include_feedback: 是否包含反馈内容
        :param include_images: 是否包含图片路径
        :return: CSV文件路径
        """
        # 读取操作日志
        logs = []
        if self.log_file.exists():
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except:
                pass

        # 读取反馈记录
        feedback_logs = []
        if include_feedback:
            import os
            project_root = Path(__file__).resolve().parents[3]
            feedback_file = project_root / "outputs" / "runtime" / "feedback_records.json"
            if feedback_file.exists():
                try:
                    with open(feedback_file, "r", encoding="utf-8") as f:
                        feedback_logs = json.load(f)
                except:
                    pass

        # 筛选日志
        filtered_logs = []
        for log in logs:
            timestamp = log.get("timestamp", "")
            op_type = log.get("operation_type", "")
            
            # 日期筛选
            if start_date and timestamp < start_date:
                continue
            if end_date and timestamp > end_date:
                continue
            
            # 类型筛选
            if operation_types and op_type not in operation_types:
                continue
            
            filtered_logs.append(log)

        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成CSV
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = self.output_dir / f"operation_logs_{timestamp_str}.csv"
        
        with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            
            # 写入表头
            headers = [
                "时间戳", "操作类型", "执行人员", "操作详情", "相关数据"
            ]
            if include_feedback:
                headers.extend(["反馈内容", "反馈位置", "反馈图片"])
            writer.writerow(headers)
            
            # 写入操作日志
            for log in filtered_logs:
                details = log.get("details", {})
                row = [
                    log.get("timestamp", ""),
                    log.get("operation_type", ""),
                    log.get("user", ""),
                    json.dumps(details, ensure_ascii=False),
                    details.get("data_path", "") or details.get("file_path", "")
                ]
                
                if include_feedback:
                    # 查找相关反馈
                    related_feedback = [
                        fb for fb in feedback_logs
                        if fb.get("timestamp", "").startswith(log.get("timestamp", "")[:10])
                    ]
                    if related_feedback:
                        fb = related_feedback[0]
                        row.extend([
                            fb.get("content", ""),
                            f"{fb.get('lon', '')},{fb.get('lat', '')}",
                            fb.get("image_path", "") if include_images else ""
                        ])
                    else:
                        row.extend(["", "", ""])
                
                writer.writerow(row)
            
            # 写入独立反馈记录
            if include_feedback:
                for fb in feedback_logs:
                    if not any(
                        fb.get("timestamp", "").startswith(log.get("timestamp", "")[:10])
                        for log in filtered_logs
                    ):
                        row = [
                            fb.get("timestamp", ""),
                            "feedback",
                            fb.get("user", "anonymous"),
                            "用户反馈",
                            ""
                        ]
                        row.extend([
                            fb.get("content", ""),
                            f"{fb.get('lon', '')},{fb.get('lat', '')}",
                            fb.get("image_path", "") if include_images else ""
                        ])
                        writer.writerow(row)

        return csv_file

    def get_log_statistics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取日志统计信息。

        :param start_date: 开始日期
        :param end_date: 结束日期
        :return: 统计信息
        """
        logs = []
        if self.log_file.exists():
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except:
                pass

        # 筛选
        filtered_logs = [
            log for log in logs
            if (not start_date or log.get("timestamp", "") >= start_date)
            and (not end_date or log.get("timestamp", "") <= end_date)
        ]

        # 统计
        stats = {
            "total_operations": len(filtered_logs),
            "by_type": {},
            "by_user": {},
            "daily_activity": {}
        }

        for log in filtered_logs:
            op_type = log.get("operation_type", "unknown")
            user = log.get("user", "unknown")
            date = log.get("timestamp", "")[:10] if log.get("timestamp") else "unknown"
            
            stats["by_type"][op_type] = stats["by_type"].get(op_type, 0) + 1
            stats["by_user"][user] = stats["by_user"].get(user, 0) + 1
            stats["daily_activity"][date] = stats["daily_activity"].get(date, 0) + 1

        return stats


# 全局实例
log_export_service = LogExportService()

