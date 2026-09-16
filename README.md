## 平台概览

> 当前版本：**v5.0（2025-11-23）** —— 项目优化：实现项目结构规范化、冗余数据清理和存储空间优化，确保核心功能稳定运行的同时大幅减少存储空间占用。

> 上一版本：**v4.2（2025-11-22）** —— 重大修复：修复v4.1版本的关键问题，特别是地图显示空白、按钮点击无反应、参数设置缺失等严重问题。新增超速阈值和网格大小手动设定功能，修复地图完全空白问题，修复指令生成和图片查看功能。

> 上一版本：**v4.1（2025-11-22）** —— 重大修复：修复v4.0版本的所有已知问题，确保系统稳定运行。修复按钮点击无反应、数据检查逻辑、图表生成下载、地图功能、数据上传、报告生成等问题，新增图片查看、反馈历史等功能。

> 上一版本：**v4.0（2025-11-22）** —— 重大升级：实现从"数据分析工具"到"警务决策支持系统"的跨越。新增可视化集成与指令化转译、地图功能全面升级、用户上传与警务日志升级三大核心功能，将算法输出直接转化为可执行的工作指令，大幅提升一线民警的操作效率和决策支持能力。

数治骑迹面向“共享电动自行车超速行为时空演化与预警机制”场景，贯彻论文提出的“科技驱动、数据赋能、协同共治”理念，以数字化手段支持公安交管的主动防控体系。平台以如下现实背景为出发点：

- 非机动车流量占城市交通 35% 以上，部分主干道每小时超过 5000 辆；
- 2024 年非机动车事故伤亡占交通事故总伤亡 41.7%，较五年前抬升 12.3 个百分点；
- 传统巡查难以覆盖超过 12% 的违法行为，急需依托新质生产力构建“新警力”。

因此，平台围绕“数据上传—空间识别—预警推送—策略建议—用户反馈”五大环节，提供从数据治理到业务落地的全链条能力。

### 4.0 版本亮点（重大升级）

- **可视化集成与指令化转译**：
  - **核心指标看板升级**：每个指标配备解释图标和指令转译，悬停显示详细说明，实现"一眼清、一键达"的业务体验。
  - **图表窗口集成**：采用可折叠标签页设计，集成综合仪表盘、趋势分析、时段分布三种图表，支持点击下钻、时间范围筛选、PNG/CSV导出。
  - **指令化转译面板**：新增"警务决策指令"专属面板，自动生成红/黄/蓝三级预警指令，将算法输出转化为可执行的工作指令。
- **地图功能全面升级**：
  - **多地图类型一体化集成**：三种专业地图（热点地图、LISA聚类图、演化模式分布图）在同一窗口无缝切换，通过图层管理实现平滑过渡。
  - **地图窗口交互增强**：支持垂直方向高度调整（拖拽手柄）、全屏模式、比例尺控件，地图区域可动态调整大小。
  - **专业地图快照功能**：支持一键快照、快照模板、元数据嵌入，提供简报/汇报/存档等多种导出模板。
- **用户上传与警务日志升级**：
  - **多媒体上传功能**：支持JPG、PNG、BMP、GIF等图片格式上传，自动生成缩略图，支持批量上传和即时预览。
  - **智能警务日志系统**：自动记录用户操作、分析任务、反馈记录，支持按时间范围、操作类型筛选导出为CSV格式，包含多媒体关联路径。

### 3.0 版本亮点（重大升级）

- **结构化报告生成**：新增 `services.report_generator`，支持生成 Word/PDF/Excel 格式的风险分析报告、热点分析报告、趋势分析报告，可直接用于工作例会与警务简报，包含执行摘要、空间自相关分析、时空热点分析、趋势分析、应对建议等完整章节。
- **三级预警推送系统**：新增 `services.alert_service`，实现红（加强的热点）、黄（新增热点）、蓝（持续的热点）三级预警自动分级，支持预警跟踪（已读/未读/已处置）、预警统计、多终端推送准备。
- **增强可视化能力**：新增 `services.visualization_service`，提供 LISA 聚类图（5类聚类模式可视化）、演化模式分布图（17类时空模式）、综合仪表盘（核心业务指标、TOP10风险区域）、趋势折线图、时段分布柱状图等高级可视化。
- **策略模板管理**：增强 `services.recommendation`，支持策略模板保存与自定义，自动生成多部门协同建议（联合城管、联动共享电单车企业、协调交通设施管理部门），实现差异化应对策略。
- **2.0 版本基础能力保留**：一键运行的 Runtime Pipeline、端到端可交互 API、可降级的空间统计、Gaode 底图联动、多端体验等核心能力全部保留并优化。

### 2.0 版本基础能力

- **一键运行的 Runtime Pipeline**：`services.runtime_pipeline` 自动将上传的 CSV 标准化为 GeoDataFrame，写入 `outputs/runtime` 目录并生成热点 GeoJSON/CSV/HTML，彻底摆脱 PostGIS/MySQL 依赖，仍保留数据库接口以便真实部署。
- **端到端可交互 API**：统一 `/api/upload`、`/api/analysis`、`/api/hotspots/geojson`、`/api/export`、`/api/feedback`、`/health` 等接口，所有路由已与 UI/前端同步，浏览器即可上传、分析、导出、反馈。
- **可降级的空间统计**：在缺失 libpysal/esda/pymannkendall 时自动切换到纯 numpy/Pandas 实现，仍输出 Moran/Gi* 结果，确保轻量环境也能得到完整可视化。
- **Gaode 底图联动**：后端 `folium` 与前端 Leaflet 共用高德瓦片，上传后立即产出 `outputs/risk_hotspots.html`，PyQt6/Vue 地图与 HTML 结果保持一致。
- **多端体验**：Flask API、Vue3 前端与 PyQt6 桌面端共用 `MapContainer` 交互逻辑，反馈模块支持 JSON 或 multipart 上传图片，离线环境则写入本地 JSON。

---

- **技术栈**：后端 Flask + SQLAlchemy（可选）+ runtime pipeline + 报告生成（python-docx、openpyxl），空间分析使用 pandas / geopandas / numpy / shapely / folium（在存在 libpysal、esda、pymannkendall 时自动切换为高精度实现）；前端 Vue3 + Element Plus + Leaflet；桌面端 PyQt6 + QtWebEngine；数据库采用 PostgreSQL + PostGIS（轨迹与热点）与 MySQL（业务元数据，可选）。
- **警务业务思维**：以“数据-行为-风险-预警”四位一体框架贯穿警务流程，支撑“事前预防—事中干预—事后评估”的主动防控闭环。
- **核心指标复刻论文**：85% 分位速度阈值 20 km/h、连续 10 s 超速判定、500 m×500 m 网格、1 h 时间步长等关键参数完全对齐论文实验设定。
- **地图与坐标**：全程采用 WGS-84（EPSG:4326）。Leaflet 与 QtWebEngine 内置高德密钥 `a7fd9560ffd58dcc12262f8f3d834b53`，可在 `frontend/src/components/MapContainer.vue` 与 `ui/map_template.html` 中替换。
- **UI 依赖**：默认采用 `PyQt6==6.5.0` 与 `PyQt6-WebEngine==6.5.0`，便于在 pip 中稳定安装，同时完全兼容本项目的 GUI 代码。

## 理论基础

> 摘自《论文.md》

- **国家治理导向**：紧扣《中共中央关于制定国民经济和社会发展第十五个五年规划的建议》提出的“提高公共安全治理水平”“由事后应对转向事前预防”要求，强调“新质生产力赋能公安交通治理现代化”。
- **数据驱动模型**：采用论文第 2 章的数据清洗算法（缺失截断、漂移剔除、地图匹配）构建高可信度轨迹数据集；以第 3 章的 Moran’s I、Getis-Ord Gi*、时空立方体与 Mann-Kendall 模型刻画风险的空间与演化特征。
- **警务业务宗旨**：围绕“振荡/新增/逐渐减少热点”分类提出差异化策略，实现“布控重点区域、优化设施、宣教人群、压降风险”的实战目标，服务“事前预警、事中干预、事后评估”三段式治理。

## 理论体系与算法细节

| 层级 | 主要内容 | 2.0 版本实现 |
| --- | --- | --- |
| 数据治理 | 缺失截断、漂移剔除、地图匹配、速度阈值判定 | `runtime_pipeline._prepare_geodataframe()` 自动识别列名并执行全部清洗逻辑，支持批次 ID、时间范围、经纬度合法性校验 |
| 空间自相关 | 全局 Moran’s I、局部 LISA、KNN 权重矩阵 | `spatial_analysis/moran_analysis.py` 既可调用 libpysal/esda，也可在缺依赖时退化为 numpy 版本，确保结果稳定 |
| 热点识别 | Getis-Ord Gi*、时空切片、风险分级 | `spatial_analysis/hotspot_analysis.py` 输出 Gi* Z 值、high/medium/low 分级，网格数不足时自动兜底 |
| 趋势检验 | Mann-Kendall | `spatial_analysis/trend_analysis.py` 默认调用 `pymannkendall.original_test`，缺依赖时改用差分趋势近似 |
| 地图渲染 | WGS-84 + 高德瓦片、热点多边形、指标提示 | `runtime_pipeline._build_hotspot_map()` 基于 folium 生成 HTML，Leaflet/PyQt6/后台 HTML 三端共用 |
| 策略推演 | “巡逻 + 设施 + 宣教”组合建议 | `services.recommendation` + PyQt UI，将热点等级 + 时间窗 +人群结构映射为可执行策略 |

<!-- Additional detail -->

### 数据流转说明

1. **上传阶段**：用户通过 `/api/upload` 或首页控制台提交 CSV，`runtime_pipeline.ingest_dataframe()` 会自动匹配 `order_id / time / lon / lat / speed` 等字段，生成统一 GeoDataFrame，并写入 `outputs/runtime/trajectory_points.csv`。
2. **网格化**：`_aggregate_to_grid()` 以可配置的度值（默认 0.0045° ≈ 500 m）构建栅格，聚合超速次数、轨迹数量、平均速度、时间窗口等指标，并生成带中心点的 `risk_grid_summary.geojson`。
3. **空间统计**：调用 Moran / Gi* / Trend，结果缓存于 `analysis_summary.json`，热点面数据写入 `hotspot_areas.geojson`，同时导出 CSV 与 HTML。
4. **可视化**：folium 生成的 `risk_hotspots.html` 可直接展示在浏览器控制台、PyQt6 或外部大屏；Vue 与 PyQt6 则实时请求 `/api/hotspots/geojson` 以保持同步。
5. **反馈闭环**：用户在页面或 API 上传反馈，若 MySQL 不可达则落地 `feedback_records.json`，下次加载时仍可在界面中查看。

### 指标与参数

- 采样网格：默认 0.0045° × 0.0045°（可传 `cell_size_deg` 自定义）。
- 超速阈值：20 km/h（`overspeed_threshold` 可调），超过即标记 `is_overspeed=1`。
- 时间维度：上传数据保留秒级时间戳，统计时在 GeoDataFrame 中记录 `time_start/time_end` 及 `time_slice`。
- 风险等级：Gi* Z 值 ≥ 2.58 为高风险，1.96~2.58 为中风险，1.65~1.96 为低风险，低于阈值则过滤。

## 目录结构

```
motospeed/
├─main.py / README.md / requirements.txt
├─data.csv / test_data.csv        # 示例数据
├─.vendor/                        # 本地补充依赖目录（便携启动兜底）
├─数治骑迹-便携版/                # 便携启动入口
│   ├─启动服务.bat
│   ├─启动桌面端.bat
│   └─使用说明.txt
├─说明文档/                        # 论文、讲稿、变更记录、流程图、维护文档
│   ├─流程图/
│   ├─项目维护/
│   └─历史归档/
├─backend/                        # Flask API
│   ├─run.py / requirements.txt
│   └─app/
│       ├─config.py
│       ├─models/__init__.py
│       ├─routes/                 # 上传 / 分析 / 反馈 REST API
│       │   ├─upload.py
│       │   ├─analysis.py
│       │   ├─feedback.py
│       │   └─__init__.py
│       ├─services/               # Runtime pipeline 与业务流程
│       │   ├─data_upload.py
│       │   ├─risk_analysis.py
│       │   ├─hotspot_export.py
│       │   ├─runtime_pipeline.py
│       │   ├─recommendation.py
│       │   ├─feedback_service.py
│       │   └─__init__.py
│       ├─utils/
│       │   ├─db.py               # PostGIS/MySQL 连接与 fallback
│       │   ├─geojson.py
│       │   └─__init__.py
│       └─uploads/data.csv        # 最近一次上传缓存
├─frontend/                       # Vue3 + Element Plus + Leaflet
│   └─src/
│       ├─main.js
│       └─components/MapContainer.vue
├─ui/                             # PyQt6 桌面端
│   ├─main_ui.py                  # 蓝白界面与交互逻辑
│   ├─map_template.html           # 内嵌 Gaode + Leaflet 模板
│   ├─services.py                 # 调用后端 API 与 runtime 文件
│   └─__init__.py
├─spatial_analysis/               # 空间统计核心算法
│   ├─hotspot_analysis.py         # Getis-Ord Gi*
│   ├─moran_analysis.py           # Global/Local Moran
│   ├─trend_analysis.py           # Mann-Kendall 趋势
│   └─__init__.py
├─scripts/
│   ├─generate_hotspot_map.py     # CLI 快速生成热点 HTML
│   ├─docs/                       # 文档转换与附录处理脚本
│   └─packaging/                  # 打包/清理脚本与 spec 文件
├─outputs/                        # 分析与可视化产物
│   ├─risk_hotspots.html
│   └─runtime/
│       ├─trajectory_points.csv
│       ├─hotspot_areas.geojson
│       ├─risk_grid_summary.geojson
│       ├─analysis_summary.json
│       ├─feedback_records.json
│       └─hotspots_*.csv          # 每轮分析导出的热点列表
├─uploads/data.csv                # API 上传的源文件同步目录
├─build/ dist/                    # PyInstaller 构建产物
└─frontend / ui / spatial_analysis
```

## 核心模块

### 基础模块（2.0 版本）

| 模块 | 说明 |
| --- | --- |
| 数据上传 | `services.data_upload` 依据论文 2.2 的流程，对 CSV 进行字段校验、时间转换、WGS-84 坐标检测，生成 GeoDataFrame 并写入 PostGIS `trajectory_points`。 |
| 风险识别 | `services.risk_analysis` 联动 `spatial_analysis`，以论文 3.1/3.2 的公式完成全局 Moran、局部 LISA、Gi* 热点、Mann-Kendall 趋势分析，输出 GeoJSON。 |
| 时空热点导出 | `services.hotspot_export` 支持按风险等级/时间过滤，导出包含中心坐标、Z 值、轨迹数的 CSV，便于融入警综平台或周工作例会。 |
| 用户反馈 | `routes.feedback` + `feedback_service` + PyQt6 反馈面板，实现前端/桌面端上传现场照片、经纬度与文字说明，形成“群众发现—数据回流—研判处置”闭环。 |
| 交互式 UI | `ui/main_ui.py` 设计为“左操作区 + 右结果区”蓝白主题，满足公安业务对可视化、列表、导出、状态提示的要求，同时支持地图拾取坐标。 |

### 3.0 新增模块

| 模块 | 说明 |
| --- | --- |
| **结构化报告生成** | `services.report_generator` 支持生成 Word/PDF/Excel 格式的风险分析报告、热点分析报告，包含执行摘要、空间自相关分析、时空热点分析、趋势分析、应对建议、技术参数等完整章节，可直接用于工作例会与警务简报。 |
| **三级预警推送** | `services.alert_service` 实现红（加强的热点）、黄（新增热点）、蓝（持续的热点）三级预警自动分级，支持预警跟踪（已读/未读/已处置）、预警统计、多终端推送准备，面向一线警务实战。 |
| **增强可视化** | `services.visualization_service` 提供 LISA 聚类图（5类聚类模式：高-高/高-低/低-高/低-低/不具有显著性）、演化模式分布图（17类时空模式）、综合仪表盘（核心业务指标、TOP10风险区域）、趋势折线图、时段分布柱状图等高级可视化。 |
| **策略模板管理** | `services.recommendation`（增强版）支持策略模板保存与自定义，自动生成多部门协同建议（联合城管、联动共享电单车企业、协调交通设施管理部门），实现差异化应对策略，将论文 4.1 的热点分类策略转为可配置的规则引擎。 |

## 快速开始

1. **准备环境（建议 Python 3.11+）**
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate  # Windows
   pip install -r backend/requirements.txt
   ```
   > 亦可使用仓库根目录 `requirements.txt`，内容与 backend 版本保持一致。
2. **一键运行后端**
   ```bash
   cd backend
   python run.py  # 自动加载 test_data.csv，并在 outputs/runtime 生成热点成果
   ```
3. **体验 API**
   ```bash
   curl -F "file=@../data.csv" http://127.0.0.1:5000/api/upload
   curl -X POST http://127.0.0.1:5000/api/analysis
   curl http://127.0.0.1:5000/api/hotspots/geojson
   curl http://127.0.0.1:5000/api/export
   curl -X POST -H "Content-Type: application/json" \
        -d "{\"content\":\"现场处置\",\"lon\":113.02,\"lat\":28.19}" \
        http://127.0.0.1:5000/api/feedback
   ```
4. **桌面端 / 前端**
   - PyQt6：`cd ui && python main_ui.py`，默认读取后端生成的热点结果与反馈列表。
   - Vue3：`cd frontend && npm install && npm run dev`，Leaflet 地图自动调用 `/api/hotspots/geojson`。

> 实际部署可在 `.env` 中提供 PostGIS/MySQL 连接串，此时上传/分析仍会保存在数据库中；缺省状态下使用本地 `outputs/runtime` 存储。

## API 速查

### 基础 API（2.0 版本）

| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/upload` | POST | 上传 CSV（字段自动识别），写入 runtime 目录并返回批次信息 |
| `/api/analysis` | POST/GET | POST 触发全量分析，GET 查看最近一次的 Moran/Gi*/趋势摘要 |
| `/api/hotspots/geojson` | GET | 按风险等级/时间筛选热点 GeoJSON，前端与 PyQt6 直接消费 |
| `/api/export` | GET | 导出热点 CSV，返回服务器文件路径以便二次处理 |
| `/api/feedback` | POST/GET | JSON 或 multipart 上传反馈，数据库不可用时写入 `outputs/runtime/feedback_records.json` |
| `/health` | GET | 健康检查 |

### 4.0 新增 API

#### 指令化转译
| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/interpretation/latest` | GET | 获取最新分析结果的指令化转译 |
| `/api/interpretation/generate` | POST | 基于分析结果生成指令化转译 |
| `/api/interpretation/report` | GET | 获取指令化报告文本 |

#### 地图快照
| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/snapshots/create` | POST | 创建地图快照 |
| `/api/snapshots/list` | GET | 列出所有快照 |
| `/api/snapshots/download/<snapshot_id>` | GET | 下载快照文件 |

#### 日志导出
| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/logs/export` | POST | 导出日志为CSV文件 |
| `/api/logs/statistics` | GET | 获取日志统计信息 |

#### 图片上传（升级）
| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/upload/image` | POST | 上传图片文件（JPG、PNG、BMP、GIF） |
| `/api/upload/images` | GET | 列出所有上传的图片 |

### 3.0 新增 API

#### 报告生成
| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/reports/risk-analysis` | POST | 生成风险分析综合报告（Word/Excel/PDF），包含执行摘要、空间自相关、热点分析、趋势分析、应对建议 |
| `/api/reports/risk-analysis/download` | GET | 下载风险分析报告文件 |
| `/api/reports/hotspot-export` | POST | 生成热点导出报告（用于周工作例会），Excel 格式 |

#### 预警推送
| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/alerts/generate` | POST | 基于最新分析结果自动生成三级预警（红/黄/蓝） |
| `/api/alerts` | GET | 获取预警列表，支持按预警等级、状态筛选 |
| `/api/alerts/<alert_id>/read` | POST | 标记预警为已读 |
| `/api/alerts/<alert_id>/handle` | POST | 标记预警为已处置 |
| `/api/alerts/statistics` | GET | 获取预警统计信息（总数、按等级分布、按状态分布） |

#### 可视化增强
| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/visualizations/lisa-cluster-map` | POST | 生成 LISA 聚类图（5类聚类模式可视化） |
| `/api/visualizations/evolution-pattern-map` | POST | 生成演化模式分布图（17类时空模式） |
| `/api/visualizations/dashboard` | GET | 获取综合仪表盘数据（核心指标、TOP10风险区域） |
| `/api/visualizations/trend-chart` | GET | 获取趋势折线图数据（支持按区域、时间范围筛选） |
| `/api/visualizations/time-distribution` | GET | 获取时段分布柱状图数据（0-24时超速次数分布） |

#### 图表生成（3.6 新增）
| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/charts/dashboard` | POST | 生成综合仪表盘图表（PNG 格式） |
| `/api/charts/trend` | POST | 生成趋势折线图（PNG 格式，支持 days 参数） |
| `/api/charts/time-distribution` | POST | 生成时段分布柱状图（PNG 格式） |
| `/api/charts/list` | GET | 列出所有已生成的图表文件 |
| `/api/charts/dashboard/download` | GET | 下载综合仪表盘图表 |

## 对应论文章节

- **1.1-1.2**：平台简介、痛点描述、警务宗旨与论文研究背景保持一致，强调“新质生产力 + 公安科技”的总体定位。
- **2.2 数据处理**：数据上传模块严格执行论文的缺失截断、漂移剔除、地图匹配思路，保证分析粒度与实验可比。
- **3.1 空间自相关**：`spatial_analysis/moran_analysis.py` 与论文公式完全一致，支持 KNN 权重与行标准化。
- **3.2 时空热点**：`hotspot_analysis.py` + `trend_analysis.py` 输出振荡、新增、逐渐减少热点，并与 PyQt6/Vue 同步展示。
- **4.1-4.2**：`recommendation.py`、`ui/main_ui.py`、Leaflet 地图承载预警推送与策略建议；用户反馈模块对应论文平台原型的用户反馈子系统。
- **附：交互式成果**：`scripts/generate_hotspot_map.py` 与 `outputs/risk_hotspots.html` 将论文案例落地为 WGS-84 HTML，可直接用于科研答辩或警务简报。

## 端到端使用指南

1. **示例体验**
   - 启动后端 (`python backend/run.py`) → 浏览器打开 `http://127.0.0.1:5000/`。
   - 上传 `data.csv` 或自有轨迹 → 点击“运行分析”。
   - 稍后即可在“热点地图”“热点列表”看到最新结果，导出 CSV/GeoJSON/HTML 以供外部系统引用。
   - 使用反馈区填写热点 ID + 坐标 + 文本，验证数据回流链路。
2. **接入真实数据**
   - 配置 PostGIS / MySQL 连接，放开 `utils/db.py` 里的 Session 对象，`runtime_pipeline` 仍可作为离线缓存。
   - 根据填报格式调整 `_pick_column` 候选列表或 `_prepare_geodataframe` 元数据字段。
3. **拓展研发**
   - 在 `spatial_analysis/` 中加入新的空间统计或机器学习模型，`run_full_analysis` 会自动串联。
   - 前端可通过 `/api/analysis` 获取摘要，或接入 WebSocket 推送实时热点。

## 3.0 版本使用示例

### 生成结构化报告

```bash
# 生成 Word 格式风险分析报告
curl -X POST http://127.0.0.1:5000/api/reports/risk-analysis \
     -H "Content-Type: application/json" \
     -d '{"format": "word", "include_charts": true}'

# 生成 Excel 格式热点导出报告（用于周工作例会）
curl -X POST http://127.0.0.1:5000/api/reports/hotspot-export \
     -H "Content-Type: application/json" \
     -d '{"risk_level": "high", "format": "excel"}'
```

### 三级预警推送

```bash
# 自动生成预警
curl -X POST http://127.0.0.1:5000/api/alerts/generate

# 查看预警列表（按等级筛选）
curl "http://127.0.0.1:5000/api/alerts?alert_level=red"

# 标记预警为已读
curl -X POST http://127.0.0.1:5000/api/alerts/ALERT-20251122120000-0001/read

# 获取预警统计
curl http://127.0.0.1:5000/api/alerts/statistics
```

### 增强可视化

```bash
# 生成 LISA 聚类图
curl -X POST http://127.0.0.1:5000/api/visualizations/lisa-cluster-map

# 生成演化模式分布图
curl -X POST http://127.0.0.1:5000/api/visualizations/evolution-pattern-map

# 获取综合仪表盘数据
curl http://127.0.0.1:5000/api/visualizations/dashboard

# 获取趋势折线图数据（近30天）
curl "http://127.0.0.1:5000/api/visualizations/trend-chart?days=30"

# 获取时段分布柱状图数据
curl http://127.0.0.1:5000/api/visualizations/time-distribution
```

### 图表生成（3.6 新增）

```bash
# 生成综合仪表盘图表
curl -X POST http://127.0.0.1:5000/api/charts/dashboard

# 生成趋势折线图（近30天）
curl -X POST http://127.0.0.1:5000/api/charts/trend \
     -H "Content-Type: application/json" \
     -d '{"days": 30}'

# 生成时段分布柱状图
curl -X POST http://127.0.0.1:5000/api/charts/time-distribution

# 列出所有已生成的图表
curl http://127.0.0.1:5000/api/charts/list
```

## 未来拓展

- 引入多源数据（违法、事故、外卖）扩展风险画像。
- 结合大语言模型与时空图神经网络，实现自然语言警情输入。
- 接入任务编排/告警调度模块，打造“数据预警-信号干预-警力调度-违法查处”闭环。
- 实现 WebSocket 实时推送预警信息至警务终端 APP。
- 集成更多可视化图表库（ECharts、D3.js）提升交互体验。***
