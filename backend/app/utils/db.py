"""
数据库连接工具。

提供 SQLAlchemy engine/session，分别面向 PostGIS 与 MySQL，
以支撑论文中“多源数据协同管理”的需求。
"""
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from ..config import get_config

_config = get_config("development")


def _safe_create_engine(uri: str) -> Optional[sessionmaker]:
    """尝试创建数据库 engine，失败时返回 None。"""
    try:
        engine = create_engine(uri, echo=False, future=True)
        return sessionmaker(bind=engine)
    except (ModuleNotFoundError, ImportError, SQLAlchemyError):
        return None


PostgisSession = _safe_create_engine(_config.POSTGIS_URI)
MysqlSession = _safe_create_engine(_config.MYSQL_URI)


