"""
数据上传服务（2.0）。

新的实现摒弃了 PostGIS 依赖，借助 runtime_pipeline 将 CSV
标准化后写入本地运行时目录，便于快速演示与调试。
"""
from pathlib import Path
from typing import Dict

import pandas as pd

from .runtime_pipeline import ingest_csv_file, ingest_dataframe


def handle_upload_file(file_path: Path, source_name: str) -> Dict:
    """读取磁盘文件并写入运行时数据仓。"""
    return ingest_csv_file(file_path, source_name)


def handle_upload_dataframe(df: pd.DataFrame, source_name: str) -> Dict:
    """供测试/脚本调用，直接接收 DataFrame。"""
    return ingest_dataframe(df, source_name)


