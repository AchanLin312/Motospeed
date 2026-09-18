## 平台概览

数治骑迹面向“共享电动自行车超速行为时空演化与预警机制”场景，贯彻论文提出的“科技驱动、数据赋能、协同共治”理念，以数字化手段支持公安交管的主动防控体系。平台以如下现实背景为出发点：

- 非机动车流量占城市交通 35% 以上，部分主干道每小时超过 5000 辆；
- 2024 年非机动车事故伤亡占交通事故总伤亡 41.7%，较五年前抬升 12.3 个百分点；
- 传统巡查难以覆盖超过 12% 的违法行为，急需依托新质生产力构建“新警力”。

当前主线为 **V2 改造版**（外卖电动车多风险识别与治理辅助平台）：围绕甲方需求手册 15 接口实现“**数据接入 → 轨迹地图匹配 → 风险行为识别 → 网格聚合评分 → 热点研判 → 全局自相关 → 智能处置建议 → 成果导出**”的完整链路，采用文件式版本化存储，每轮分析产出独立可追溯的成果目录。

---

- **技术栈**：后端 Flask（V2 服务层 + 空间分析库 pandas / geopandas / numpy / shapely / libpysal / esda / pymannkendall）；页面端为服务端模板 `index_v5.html`（Element Plus + Leaflet，经 Flask `/` 直接提供）；桌面端 PyQt6 + QtWebEngine 全屏内嵌 V2 工作台；LLM 集成 DeepSeek（处置建议生成，知识库驱动）。
- **警务业务思维**：以“数据-行为-风险-预警”四位一体框架贯穿警务流程，支撑“事前预防—事中干预—事后评估”的主动防控闭环。
- **核心指标对齐论文与甲方手册**：85% 分位速度阈值 20 km/h、连续 10 s 超速判定、500 m×500 m 网格、Gi* 含自身值（star=True）等关键参数完全对齐甲方《任务清单与算法参考 V2.0》与论文实验设定。
- **地图与坐标**：全程采用 WGS-84（EPSG:4326）。Leaflet 内置高德密钥 `a7fd9560ffd58dcc12262f8f3d834b53`，可在 `frontend/src/components/MapContainer.vue` 中替换。
- **UI 依赖**：默认采用 `PyQt6==6.5.0` 与 `PyQt6-WebEngine==6.5.0`，便于在 pip 中稳定安装。

## 理论基础

> 摘自《论文.md》

- **国家治理导向**：紧扣《中共中央关于制定国民经济和社会发展第十五个五年规划的建议》提出的“提高公共安全治理水平”“由事后应对转向事前预防”要求，强调“新质生产力赋能公安交通治理现代化”。
- **数据驱动模型**：采用论文第 2 章的数据清洗算法（缺失截断、漂移剔除、地图匹配）构建高可信度轨迹数据集；以第 3 章的 Moran’s I、Getis-Ord Gi*、时空立方体与 Mann-Kendall 模型刻画风险的空间与演化特征。
- **警务业务宗旨**：围绕“振荡/新增/逐渐减少热点”分类提出差异化策略，实现“布控重点区域、优化设施、宣教人群、压降风险”的实战目标，服务“事前预警、事中干预、事后评估”三段式治理。

## 理论体系与算法细节

| 层级 | 主要内容 | V2 实现 |
| --- | --- | --- |
| 数据治理 | 轨迹地图匹配、路段级定位、速度估计 | `services/v2/map_match_service.py` 将 GPS 点匹配到路网路段，输出路段级轨迹 |
| 行为识别 | 超速（85 分位阈值 + 持续时长）、逆行、急加速/急减速 | `services/v2/behavior_service.py` 基于匹配轨迹逐点判定四类风险行为 |
| 网格聚合 | 500 m 栅格、事件计数、暴露度 | `services/v2/grid_aggregation_service.py` 聚合各类事件并产出 `grid_metrics.csv` |
| 网格评分 | 综合风险评分（CRI） | `services/v2/scoring_service.py` 按暴露度加权计算网格风险分 |
| 空间自相关 | 全局 Moran’s I、局部 LISA、KNN 权重矩阵 | `spatial_analysis/moran_analysis.py` 调用 libpysal/esda，缺依赖时退化为 numpy 版本 |
| 热点识别 | Getis-Ord Gi*（含自身值）、Z 值分级、无显著时按 CRI 兜底 | `spatial_analysis/hotspot_analysis.py`（`G_Local(values, w, star=True)`）+ `services/v2/hotspot_service.py` 分层执行 |
| 趋势检验 | Mann-Kendall | `spatial_analysis/trend_analysis.py` 默认调用 `pymannkendall.original_test` |
| 智能建议 | LLM + 知识库生成网格处置建议 | `services/v2/advice_service.py` + `knowledge_base.py`（KB-1.0.json）+ `llm_provider.py`（DeepSeek） |

### 数据流转说明

1. **数据接入**：`POST /api/v2/batches/trajectory` 上传轨迹 CSV，落盘 `outputs/runtime/v2/trajectories/<batch_id>/`；`POST /api/v2/road-networks` 上传路网（Admin Token）。
2. **流水线执行**：`POST /api/v2/analysis` 创建后台任务（线程 + 内存任务表，不阻塞请求），按 `match → behavior → grid → score → hotspots → moran → summary` 七阶段推进，进度经 `/analysis/<version>/status` 轮询。
3. **版本化产出**：每轮分析写入独立目录 `outputs/runtime/v2/analysis/<analysis_version>/`，含 `grid_metrics.csv`、各图层热点 GeoJSON/CSV、`summary.json`（KPI、事件分布、Moran/LISA 摘要）等，天然支持多轮对比与审计。
4. **前端呈现**：`index_v5.html` 工作台请求 `/api/v2/analysis/<version>/summary`、`/api/v2/hotspots`、`/api/v2/grids/<grid_id>` 渲染 KPI、热点图层与网格钻取；桌面版为同一页面的 PyQt6 内嵌壳。
5. **智能建议与导出**：`POST /api/v2/advice/generate` 结合知识库与 LLM 生成网格处置建议；`GET /api/v2/exports/report|hotspots` 导出报告与热点清单。

### 指标与参数

- 采样网格：默认 0.0045° × 0.0045° ≈ 500 m（可传 `cell_size` 自定义）。
- 超速阈值：85% 分位速度，超过 20 km/h 且持续 10 s 判定超速事件；急加速/急减速按甲方手册阈值逐点判定。
- 风险等级：Gi* Z 值 ≥ 2.58 为高风险（99% 置信度），1.96~2.58 为中风险（95%），1.28~1.96 为低风险（80%）；某层无显著网格时按 CRI 排序兜底取 Top 8（前端标注“兜底”）。

## 目录结构

```
motospeed 2.0/
├─backend/
│  ├─run.py / wsgi.py
│  └─app/
│      ├─__init__.py              # 应用工厂：/ → V2 工作台，/v1 → V1 兼容页
│      ├─config.py
│      ├─routes/
│      │  ├─api_v2/               # V2 手册 15 接口（/api/v2 前缀）
│      │  │  ├─batches.py         # 轨迹批次上传/列表
│      │  │  ├─road_networks.py   # 路网上传/列表（Admin）
│      │  │  ├─analysis.py        # 创建分析/状态/列表/摘要
│      │  │  ├─hotspots.py / grids.py / advice.py / exports.py
│      │  │  └─admin.py           # admin/logs、admin/config
│      │  └─*.py                  # V1 兼容路由（upload/analysis/feedback 等）
│      ├─services/
│      │  ├─v2/                   # V2 服务层（七阶段流水线、建议、知识库）
│      │  └─*.py                  # V1 兼容服务
│      ├─templates/index_v5.html  # V2 工作台页面
│      └─utils/db.py              # 可选数据库连接
├─spatial_analysis/               # 空间统计核心算法
│  ├─hotspot_analysis.py          # Getis-Ord Gi*（star=True）
│  ├─moran_analysis.py            # Global/Local Moran
│  └─trend_analysis.py            # Mann-Kendall 趋势
├─frontend/src/                   # Leaflet 地图组件（MapContainer.vue）
├─ui/main_ui.py                   # PyQt6 桌面壳（全屏内嵌 V2 工作台）
├─scripts/
│  ├─docs/                        # 文档转换脚本
│  └─packaging/                   # 打包/清理脚本与 spec 文件
├─outputs/runtime/v2/             # V2 文件式存储
│  ├─trajectories/<batch_id>/     # 上传轨迹
│  ├─road_networks/               # 上传路网
│  └─analysis/<analysis_version>/ # 每轮分析成果（grid_metrics、热点、summary.json）
├─甲方新需求/                     # 甲方资料：需求手册、任务清单、论文 PDF、示例数据
├─说明文档/                       # 论文、变更记录、维护文档（V1 时代历史归档）
├─setup_v2.bat                    # 一键安装：创建 venv + 安装依赖（仅需一次）
├─start_v2.example.bat            # 启动模板：复制为 start_v2.bat 并填入密钥
├─start_docker.bat                # Docker 一键启动
└─requirements.txt                # V2 依赖清单（Docker 用 requirements-docker.txt）
```

> **数据说明**：`甲方新需求/`（需求手册、算法任务清单、参考论文 PDF、示例轨迹 CSV、亦庄原始路网）已随仓库提供；其中大文件（`北京市.shp/.dbf`，约 287MB）经 **Git LFS** 存储——克隆前请先安装 [git-lfs](https://git-lfs.com) 并执行一次 `git lfs install`，否则大文件只会得到文本指针。`outputs/`（运行数据与分析成果）仍不入库；运行时也可通过 V2 工作台上传自己的轨迹 CSV 与路网。轨迹数据仅限项目相关方使用，请勿对外传播。

## 核心模块

| 模块 | 说明 |
| --- | --- |
| 流水线编排 | `services/v2/pipeline_service.py` 串联七阶段，支持进度回调与阶段缓存（已完成阶段可短路复用，`force=True` 强制重算）。 |
| 地图匹配 | `services/v2/map_match_service.py` + `road_network_service.py`：GPS 点 → 路网路段匹配，产出路段级轨迹。 |
| 风险行为识别 | `services/v2/behavior_service.py`：超速、逆行、急加速、急减速四类事件判定，事件分布写入 summary。 |
| 网格聚合与评分 | `grid_aggregation_service.py` + `scoring_service.py`：500 m 栅格事件聚合、CRI 评分、有效网格筛选。 |
| 热点识别 | `hotspot_service.py` 分层（综合/超速/逆行/急变速）调用 `spatial_analysis/hotspot_analysis.py` 的 Gi*（star=True），显著格不足时按 CRI 兜底 Top 8。 |
| 空间自相关 | `spatial_analysis/moran_analysis.py`：全局 Moran’s I 与 LISA，产出“满天星/成片”形态判据。 |
| 智能处置建议 | `advice_service.py` + `knowledge_base.py`：检索 KB-1.0 知识库，调用 DeepSeek 生成网格级处置建议，附建议依据 `/advice/<grid_id>/basis`。 |
| 成果导出 | `exports.py`：热点 CSV/GeoJSON 与分析报告导出。 |
| 桌面壳 | `ui/main_ui.py`：全屏内嵌 `http://127.0.0.1:5000` 的 V2 工作台，顶部工具栏提供后端状态与重新加载。 |

> V1 兼容层（旧工作台 `/v1`、`/api/upload`、`/api/analysis`、报告/预警/可视化等路由与服务）仍保留在 `backend/app/routes/` 与 `backend/app/services/` 下，不影响 V2 主链路；历史变更见 `说明文档/CHANGELOG_*.md`。

## 快速开始

### 方式 A：一键脚本部署（Windows，推荐）

1. 双击运行 `setup_v2.bat`：自动创建虚拟环境并安装依赖（清华 PyPI 镜像，仅需执行一次）。
2. 复制 `start_v2.example.bat` 为 `start_v2.bat`，填入 `LLM_API_KEY` 与 `V2_ADMIN_TOKEN`（该文件已 gitignore，不会入库）。
3. 双击 `start_v2.bat` 启动后端，浏览器打开 `http://127.0.0.1:5000/`。

### 方式 B：手动部署（Windows / Linux / macOS 通用）

1. **准备环境（建议 Python 3.11+）**
   ```bash
   python -m venv venv
   .\venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```
2. **启动**
   ```bash
   venv\Scripts\python.exe backend\run.py
   ```
   浏览器打开 `http://127.0.0.1:5000/`。
3. 桌面版（可选）：运行 `start_desktop.bat` 自动拉起后端并等待 `/health` 就绪，随后启动 PyQt6 主窗口（后端已在跑时直接复用）。

### 方式 C：Docker 部署

安装 Docker Desktop 后双击 `start_docker.bat`（等价于 `docker-compose up -d`），依赖清单见 `requirements-docker.txt`。

### 体验 V2 API
```bash
curl -F "file=@你的轨迹数据.csv" http://127.0.0.1:5000/api/v2/batches/trajectory
curl -X POST -H "Content-Type: application/json" -d "{\"batch_id\":\"B001\",\"analysis_version\":\"A001\"}" http://127.0.0.1:5000/api/v2/analysis
curl http://127.0.0.1:5000/api/v2/analysis/A001/summary
curl "http://127.0.0.1:5000/api/v2/hotspots?analysis_version=A001&layer=reverse"
```

> `LLM_API_KEY` 未配置时，AI 治理建议自动使用内置知识库模板兜底；`V2_ADMIN_TOKEN` 未配置时管理接口仅开发模式放行。

## API 速查（/api/v2，手册 15 接口）

| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/v2/batches/trajectory` | POST | 上传轨迹批次 CSV（字段自动识别 order_id/time/lon/lat/speed） |
| `/api/v2/batches` | GET | 批次列表；`/batches/<batch_id>` 批次详情 |
| `/api/v2/road-networks` | POST/GET | 路网上传（GeoJSON/SHP 转 GeoJSON）与列表（Admin） |
| `/api/v2/analysis` | POST | 创建分析任务（batch_id、analysis_version、可选 net_id/cell_size），后台线程执行 |
| `/api/v2/analysis/<v>/status` | GET | 任务进度（stage/progress/message） |
| `/api/v2/analysis` | GET | 分析版本列表；`/analysis/<v>/summary` 分析摘要（KPI、事件分布、Moran/LISA、热点分层元数据） |
| `/api/v2/hotspots` | GET | 热点列表（按 analysis_version/layer/risk_level 过滤） |
| `/api/v2/grids/<grid_id>` | GET | 网格详情钻取（事件计数、评分、行为构成） |
| `/api/v2/advice/generate` | POST | LLM 生成网格处置建议（知识库驱动） |
| `/api/v2/advice/<grid_id>/basis` | GET | 建议依据（引用的知识库条目与网格指标） |
| `/api/v2/exports/report` | GET | 导出分析报告 |
| `/api/v2/exports/hotspots` | GET | 导出热点 CSV/GeoJSON |
| `/api/v2/admin/logs` | GET | 操作日志（Admin） |
| `/api/v2/admin/config` | GET/PUT | 运行参数查看与调整（Admin） |
| `/health` | GET | 健康检查 |

> 管理接口（路网、admin）需请求头 `X-Admin-Token`；V1 兼容 API（`/api/upload`、`/api/analysis`、`/api/feedback` 等）仍可用，详见 `backend/app/routes/` 下对应文件。

## 对应论文章节

- **1.1-1.2**：平台简介、痛点描述、警务宗旨与论文研究背景保持一致，强调“新质生产力 + 公安科技”的总体定位。
- **2.2 数据处理**：V2 的地图匹配与行为识别阶段严格执行论文的缺失截断、漂移剔除、地图匹配思路，保证分析粒度与实验可比。
- **3.1 空间自相关**：`spatial_analysis/moran_analysis.py` 与论文公式完全一致，支持 KNN 权重与行标准化。
- **3.2 时空热点**：`hotspot_analysis.py`（Gi* star=True）+ `trend_analysis.py` 输出热点分级与趋势，成果经 V2 工作台展示。
- **4.1-4.2**：知识库 + LLM 建议模块承载预警推送与策略建议；反馈链路对应论文平台原型的用户反馈子系统。
- **附：交互式成果**：`scripts/generate_hotspot_map.py` 与 `outputs/` 下热点 HTML 将论文案例落地为 WGS-84 成果，可直接用于科研答辩或警务简报。

## 端到端使用指南

1. **示例体验**
   - 启动后端 → 浏览器打开 `http://127.0.0.1:5000/`（或双击 `start_desktop.bat` 使用桌面版）。
   - 上传 `data.csv`（或甲方示例 `甲方新需求/TDs_data_20240605_morning_peak.csv`）创建轨迹批次。
   - 创建分析任务，等待七阶段完成（状态接口可见进度）。
   - 在 KPI 区查看事件分布与 Moran’s I；在地图上切换综合/超速/逆行/急变速热点图层；点击网格查看事件构成与 LLM 处置建议。
   - 导出热点清单与分析报告供外部系统引用。
2. **接入真实数据**
   - 上传路网（Admin Token）后在创建分析时指定 `net_id`，启用路段级地图匹配。
   - 按数据格式调整 `services/v2/data_import.py` 的字段候选列表。
3. **拓展研发**
   - 在 `spatial_analysis/` 中加入新的空间统计模型，`pipeline_service` 阶段化编排便于插入新阶段。
   - 知识库 `kb_data/KB-1.0.json` 可扩充治理策略条目，无需改动代码即可影响建议生成。

## 未来拓展

- 引入多源数据（违法、事故、外卖）扩展风险画像。
- 结合大语言模型与时空图神经网络，实现自然语言警情输入。
- 接入任务编排/告警调度模块，打造“数据预警-信号干预-警力调度-违法查处”闭环。
- 实现 WebSocket 实时推送预警信息至警务终端 APP。
- 集成更多可视化图表库（ECharts、D3.js）提升交互体验。
