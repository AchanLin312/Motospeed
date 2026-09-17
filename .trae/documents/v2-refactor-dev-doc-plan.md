# 计划：V2 改造实施——外卖电动车多风险识别平台（代码 + 开发文档）

## 一、任务摘要

依据 `甲方新需求/数治骑迹外卖电动车多风险识别与治理辅助平台改造需求手册_V1.0.docx`，**直接改造当前项目代码**，实现：三类风险识别（超速/疑似逆行/急变速）+ IVMM 地图匹配 + 熵权-TOPSIS 评分 + 四套热点图层 + AI 治理建议（规则兜底/LLM 预留）+ API v2 + 双模式。新数据 = 亦庄外卖电动车 2024-06-05 早高峰 CSV；新路网 = 北京市 OSM shapefile（21.7 万条，需裁剪亦庄）。

产出：
1. 可运行的 V2 后端与前端改造（30 条验收标准为主目标）
2. 开发文档 `说明文档/开发文档_外卖多风险识别平台V2改造.md`（含架构、模块、API v2、验收对照）
3. 端到端验证结果

用户已确认：LLM 走预留接口（OpenAI 兼容、环境变量密钥）+ 15 条知识库规则兜底，不绑厂商。

## 二、关键现状（已探明）

- 后端 13 个 service（`backend/app/services/`）+ 11 个 v1 蓝图；`runtime_pipeline.py` 单文件大杂烩，硬编码高德 key（违反 AC30，必须清除）
- 新 CSV 15 列：`TS, COMPANYID, BICYCLEID, POSITIONTIME, LOCKSTATUS, BICYCLE_LNG, BICYCLE_LAT, LOCKID, NEW_BICYCLEID, X_position, Y_position, TID, Distance, Time_consuming, Speed`；**Speed 为 m/s**；`BICYCLE_LNG/LAT` 与 `X/Y` 差约 500m（疑坐标系之别，需勘验）
- 路网 shapefile：WGS84，字段 `osm_id, code, fclass, name, oneway(B/F/T?), maxspeed, fclass_cn, ...`，全北京需裁剪
- Gi*/Moran/LISA 已有（`spatial_analysis/`），可复用；`recommendation.py`、`risk_analysis.py` 等将按手册建议拆分/编排

## 三、实施阶段（每阶段有可验证产出）

### M0 数据勘验与接入（先行，决定后续一切）
1. 只读勘验脚本：双坐标与路网贴合距离分布（选分析坐标）、时间范围确认 07:00–08:59、Speed×3.6 与 Distance/Time_consuming 互验（AC03）、TID/LOCKSTATUS 取值语义
2. 新建 `data_import_service.py`：15 列字段映射+别名、缺失阻断、异常行隔离（超比例阻断）、batch_id、清洗
3. 修改 bootstrap：停止自动加载旧 data.csv/test_data.csv（AC01）
   ✅ 验证：批次创建成功，坐标结论落定

### M1 路网与 IVMM 地图匹配（全新最重模块）
4. `road_network_service.py`：shapefile 成套导入→裁剪亦庄 bbox→WGS84→UTM 50N→构建 **无向图**（networkx，保留每条边方向/oneway/fclass 属性）→路网版本管理
5. `map_match_service.py`：IVMM——候选 r=150m 内 alpha=5 条、beta 动态（相邻点间隔众数 <10s→50，≥10s→200）、投票+路径连续性（非单纯最近投影，AC06）；输出 8 字段（matched_road_id/road_class/road_length_m/oneway/offset_m/matched_lon/matched_lat/match_score）；按道路等级偏移上限表校验
   ✅ 验证：50 条样例叠加检查（AC06/AC07），偏移合规

### M2 三类行为识别
6. `behavior_service.py`：
   - 超速：20km/h + 连续 10s（AC08），m/s×3.6
   - 疑似逆行：单向路方向角差 135°–225°（α_d=45°）；双向路叉积左侧判定；子链 >50% 逆行点判疑似逆行事件（AC09/AC10）
   - 急变速：运动状态判定、采样间隔 ≤6s 不可判定不插值（AC12）、运动样本 85%/15% 分位阈值（AC11）、排除急启动、连续点合并事件（AC13）
   - 输出点级 + 事件级两级结果（手册字段表：batch_id/segment_id/.../rule_version/quality_flag）
   ✅ 验证：手册 8 组边界用例（19.99/20.00/20.01、9.9/10/10.1s、134.9/135/180/225/225.1°、49.9/50/50.1%、5.9/6/6.1s、P85 比较符、0.99/1/1.01km、缓存不变）脚本化自测通过

### M3 网格聚合与评分
7. `grid_aggregation_service.py`：250m 默认网格（100/500 可配，UTM 米制，AC15）、暴露量=有效里程按网格相交长度分配（AC14）、三类事件率（次/100km）
8. `scoring_service.py`：熵权法（三项事件率→权重，和=1，同版本缓存不重算 AC16）+ TOPSIS→CRI 0–100 + 三类危险指数 0–100（AC17）；指标无差异权重 0、急变速样本不足时综合指数不可用（不记 0）
   ✅ 验证：同一分析版本重跑结果一致（可复现性）

### M4 热点分析 v2
9. `hotspot_service.py`（改造）：四图层 Gi*（综合 CRI/超速率/逆行率/急变速率，AC18）、Z 分级 2.58/1.96/1.65、无显著时兜底 top8 `selection_type=top_risk_fallback`（AC19）、缓存 GeoJSON；Moran/LISA/趋势保留（AC25/AC28：单日数据下趋势显示"数据不足"）
   ✅ 验证：四图层切换缓存读取、亦庄定位（AC04）

### M5 API v2 与双模式
10. 新建 `backend/app/routes/api_v2/`：手册 18 接口（批次/路网版本/分析/状态进度/summary/hotspots/grids/advice/basis/exports/admin）+ v1 兼容层（AC28）
11. 分析任务后台线程 + 进度/错误上报（长任务不阻塞、AC26 管理模式）
    ✅ 验证：curl 走通上传→分析→状态→热点→summary 全链

### M6 AI 建议
12. `knowledge_base.py`：15 条规则（KB-G01…KB-F01）+ BASIS 依据种子数据
13. `advice_service.py` + `llm_provider.py`：规则兜底生成（风险判断/现场建议/道路环境/企业协同/宣传教育/复核 六部分）、LLM 预留（白名单外发、45s 超时、缓存键、依据默认隐藏按需显示）（AC21–AC24）
    ✅ 验证：断网/超时返回规则兜底不崩溃；外发白名单无车辆标识（AC22）

### M7 前端双端
14. Web 模板：图层筛选、悬浮指标卡（CRI/三指数/事件数/率/暴露量）、详情侧栏、AI 建议与依据按钮、地图定位亦庄
15. report/chart 升级三类指标+权重+CRI+数据质量+单日限制（AC29）；热点 CSV 导出；趋势模块降级显示
16. PyQt6：接 v2 API、业务/管理模式入口（AC26/AC27）
    ✅ 验证：双端同 analysis_version 指标一致（AC27）

### M8 安全、文档与总验收
17. 清除硬编码 AMAP key→环境变量；日志脱敏；源码无密钥（AC30）
18. 撰写开发文档 `说明文档/开发文档_外卖多风险识别平台V2改造.md`（架构图、模块设计、API v2 表、数据字典、验收对照 AC01–AC30）
19. AC01–AC30 逐条自查表输出
    ✅ 验证：grep 无完整密钥；验收对照全绿或标注遗留

## 四、关键决策记录

| # | 决策 |
|---|---|
| D1 | 直接改代码，文档为产出之一；分 M0–M8 顺序执行，todo 跟踪 |
| D2 | 新逻辑放新文件（`*_service.py` v2、`api_v2/`），v1 文件尽量不动保兼容（AC28） |
| D3 | 存储沿用文件制：`outputs/runtime/v2/<analysis_version>/` 不可变目录 |
| D4 | 投影 UTM 50N（EPSG:32650）做米制网格/里程 |
| D5 | 分析坐标以 M0 勘验结论为准（不臆断双坐标哪套正确） |
| D6 | IVMM 用 networkx 无向图自实现（不引重型 OSMnx，若 venv 已有可复用） |
| D7 | LLM：Provider 抽象+环境变量密钥+规则兜底优先（用户确认） |
| D8 | oneway=B/F/T 语义在 M0 用样例路段实证后落码 |

## 五、风险

- IVMM 性能：21.7 万路段需先裁剪亦庄+空间索引（R-tree/shapely STRtree）
- 单日 2 小时数据：趋势/演化模块只能降级显示（AC25 有明确要求，非缺陷）
- 工程量大：M0–M4 为核心价值优先保证；M5–M8 依次推进，每阶段可停可验
- 改动期间 5000 端口旧服务需重启验证

## 六、验证方式（总）

1. 端到端：上传新 CSV → 路网导入 → IVMM → 三类行为 → 评分 → 四图层 → AI 建议 → 报告导出，全程 API 可查
2. 边界用例脚本全绿（手册 8 组）
3. AC01–AC30 对照表逐条给出通过/遗留结论
4. 开发文档覆盖手册全部表格与接口
