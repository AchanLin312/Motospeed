"""
反馈存储服务（2.0）。

优先尝试写入 MySQL，若数据库不可达则退回到本地 JSON，
确保 `/api/feedback` 在离线环境也能响应。
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.exc import SQLAlchemyError

from ..utils.db import MysqlSession
from .runtime_pipeline import record_feedback_locally, load_feedback_records


def _to_float(value: Optional[float]) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def save_feedback(
    content: str,
    area_id: Optional[str],
    user_type: str,
    lon: Optional[float],
    lat: Optional[float],
    photo_path: Optional[str] = None,
) -> dict:
    payload = {
        "content": content,
        "area_id": area_id,
        "user_type": user_type,
        "lon": _to_float(lon),
        "lat": _to_float(lat),
        "photo_path": photo_path,
    }
    if MysqlSession is None:
        feedback_id = record_feedback_locally(payload)
        return {"feedback_id": feedback_id, "storage": "local"}
    try:
        sql = """
            INSERT INTO feedbacks (content, area_id, user_type, lon, lat, photo_path, created_at)
            VALUES (:content, :area_id, :user_type, :lon, :lat, :photo_path, :created_at)
        """
        params = {
            **payload,
            "created_at": datetime.utcnow(),
        }
        with MysqlSession() as session:
            result = session.execute(sql, params)
            session.commit()
            feedback_id = result.lastrowid if hasattr(result, "lastrowid") else 0
            return {"feedback_id": feedback_id, "storage": "mysql"}
    except SQLAlchemyError:
        feedback_id = record_feedback_locally(payload)
        return {"feedback_id": feedback_id, "storage": "local"}


def list_feedback_records() -> List[Dict[str, Any]]:
    """返回反馈记录列表，若 MySQL 不可达则读取本地 JSON。"""
    if MysqlSession is None:
        return load_feedback_records()
    try:
        sql = """
            SELECT feedback_id, content, area_id, user_type, lon, lat, photo_path, created_at
            FROM feedbacks
            ORDER BY created_at DESC
            LIMIT 200
        """
        with MysqlSession() as session:
            result = session.execute(sql)
            return [dict(row) for row in result]
    except SQLAlchemyError:
        return load_feedback_records()


def delete_feedback_record(feedback_id: str) -> bool:
    """删除反馈记录。"""
    from pathlib import Path
    from ..services.runtime_pipeline import RUNTIME_DIR
    import json
    
    # 尝试从MySQL删除
    if MysqlSession is not None:
        try:
            sql = "DELETE FROM feedbacks WHERE feedback_id = :feedback_id"
            with MysqlSession() as session:
                result = session.execute(sql, {"feedback_id": feedback_id})
                session.commit()
                if result.rowcount > 0:
                    return True
        except SQLAlchemyError:
            pass  # 如果MySQL失败，尝试从本地JSON删除
    
    # 从本地JSON删除
    feedback_file = RUNTIME_DIR / "feedback_records.json"
    if not feedback_file.exists():
        return False
    
    try:
        with open(feedback_file, "r", encoding="utf-8") as f:
            records = json.load(f)
        
        # 查找要删除的记录（保存photo_path用于后续删除图片）
        deleted_record = None
        for r in records:
            if str(r.get("feedback_id", "")) == str(feedback_id) or str(r.get("id", "")) == str(feedback_id):
                deleted_record = r
                break
        
        if deleted_record:
            # 删除记录
            records = [
                r for r in records
                if str(r.get("feedback_id", "")) != str(feedback_id) and str(r.get("id", "")) != str(feedback_id)
            ]
            
            # 保存更新后的记录
            with open(feedback_file, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            
            # 尝试删除关联的图片文件
            if deleted_record.get("photo_path"):
                photo_path = Path(deleted_record["photo_path"])
                if photo_path.exists():
                    try:
                        photo_path.unlink()
                    except:
                        pass
            
            return True
        return False
    except Exception:
        return False


