"""
后端配置模块。

结合论文所述的多源数据体系，本配置同时包含业务元数据 MySQL
与轨迹空间数据 PostGIS 的连接参数。真实部署时建议通过环境变量
注入私密凭据。
"""
from dataclasses import dataclass
from pathlib import Path
import os


@dataclass
class BaseConfig:
    SECRET_KEY: str = os.getenv("CRIME_PLATFORM_SECRET", "dev-secret")
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    # 业务库（用户、反馈等）
    MYSQL_URI: str = os.getenv(
        "CRIME_PLATFORM_MYSQL",
        "mysql+pymysql://user:pass@localhost:3306/crime_meta",
    )
    # 轨迹空间库（PostGIS）
    POSTGIS_URI: str = os.getenv(
        "CRIME_PLATFORM_POSTGIS",
        "postgresql+psycopg2://user:pass@localhost:5432/crime_geo",
    )
    # UPLOAD_DIR 使用绝对路径，从项目根目录开始
    # 从backend/app/config.py到项目根目录需要向上2级
    _project_root = Path(__file__).resolve().parents[2]
    UPLOAD_DIR: str = os.getenv("CRIME_PLATFORM_UPLOAD", str(_project_root / "uploads"))


@dataclass
class DevelopmentConfig(BaseConfig):
    DEBUG: bool = True


@dataclass
class ProductionConfig(BaseConfig):
    DEBUG: bool = False


def get_config(name: str) -> BaseConfig:
    """根据名称返回配置对象。"""
    mapping = {
        "development": DevelopmentConfig,
        "production": ProductionConfig,
    }
    return mapping.get(name, DevelopmentConfig)()

