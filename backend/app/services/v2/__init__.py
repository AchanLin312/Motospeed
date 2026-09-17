"""V2 服务子包：外卖电动车多风险识别平台。

版本目录结构（不可变，D3）：
    outputs/runtime/v2/
        batches/<batch_id>/            # 轨迹批次（上传即固定）
            trajectory.csv             # 标准化轨迹点
            meta.json                  # 批次元数据
            isolated_rows.csv          # 被隔离的异常行
        road_networks/<net_id>/        # 路网版本
            network.gpkg               # 裁剪后路段（GeoPackage）
            meta.json
        analysis/<analysis_version>/   # 分析版本（引用 batch + 路网版本）
            matched_points.csv         # IVMM 匹配结果（点级）
            events.csv                 # 事件级结果（三类行为）
            grid_metrics.csv           # 网格指标
            weights.json               # 熵权结果
            hotspots/<layer>.geojson   # 四图层热点缓存
            advice/<grid_id>.json      # AI 建议缓存
            summary.json
            meta.json
"""
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
V2_DIR = ROOT_DIR / "outputs" / "runtime" / "v2"
BATCH_DIR = V2_DIR / "batches"
ROADNET_DIR = V2_DIR / "road_networks"
ANALYSIS_DIR = V2_DIR / "analysis"

for _d in (BATCH_DIR, ROADNET_DIR, ANALYSIS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# 亦庄默认范围（M0 勘验结论，外扩约 500m）
YIZHUANG_BBOX = (116.455, 39.705, 116.592, 39.828)  # (min_lon, min_lat, max_lon, max_lat)

# 投影：UTM 50N（D4）
TARGET_CRS = "EPSG:32650"

# 手册算法参数（V1.0 需求手册，rule_version）
RULE_VERSION = "v2.0-20240605"

# 候选参数（手册 IVMM 表 + M1 实测校准）
# beta 校准依据：观测点距路网中位 7.5m（M0 勘验），50/200 过松导致匹配偏移超 AC07 上限
IVMM_ALPHA = 5      # 最大候选路段数
IVMM_R = 100.0      # 邻域查询半径（米）
IVMM_BETA_FAST = 10.0   # 相邻点时间间隔众数 < 10s（贴合实测 GPS 精度 σ≈7.5m）
IVMM_BETA_SLOW = 8.0    # >= 10s（稀疏链间隔大、转移项失 informational，发射项需更紧）
IVMM_GL_THRESHOLD = 10.0
IVMM_FAR_M = 45.0   # 候选质量门槛：最近候选超过此距离视为不可匹配（园区内部/漂移点）

# 超速参数
OVERSPEED_THRESHOLD_KMH = 20.0
OVERSPEED_MIN_DURATION_S = 10.0
OVERSPEED_MIN_POINTS = 2

# 逆行参数
REVERSE_ALPHA_D = 45.0      # 单向路容许浮动角
REVERSE_LOW, REVERSE_HIGH = 135.0, 225.0  # 方向差区间
REVERSE_SUBCHAIN_RATIO = 0.5  # 子链超过 50% 逆行点判疑似逆行

# 急变速参数
RAPID_MAX_INTERVAL_S = 6.0    # 超过 6 秒不可判定（不插值）
RAPID_ACCEL_QUANTILE = 0.85   # 运动样本急加速阈值分位
RAPID_DECEL_QUANTILE = 0.15   # 运动样本急减速阈值分位


def batch_dir(batch_id: str) -> Path:
    return BATCH_DIR / batch_id


def roadnet_dir(net_id: str) -> Path:
    return ROADNET_DIR / net_id


def analysis_dir(version: str) -> Path:
    return ANALYSIS_DIR / version
