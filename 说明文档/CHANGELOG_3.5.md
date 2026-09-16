# 平台 3.5 版本升级说明

## 升级概述

平台 3.5 版本是一次 UI 交互与可视化体验的重大升级，在保留 3.0 版本所有核心能力的基础上，将 LISA 聚类图、演化模式分布图直接集成到 PyQt6 主界面，支持地图类型一键切换，分析完成后自动生成可视化文件，极大提升了平台的交互体验与实战可用性。

## 主要升级内容

### 1. UI 地图类型切换功能

**文件位置**：`ui/main_ui.py`、`ui/map_template.html`

**核心能力**：
- 在风险识别结果页面新增"地图类型"下拉选择框
- 支持三种地图类型一键切换：
  - **热点地图**：显示风险热点区域（高/中/低风险分级）
  - **LISA聚类图**：显示空间自相关聚类模式（高-高/高-低/低-高/低-低/不具有显著性）
  - **演化模式分布图**：显示时空演化模式（振荡热点、新增热点、加强的热点、逐渐减少的热点、持续的热点）
- 所有地图类型支持相同的交互功能：缩放、平移、点击查看详情、自动适应边界

**实现细节**：
- 在 `_create_analysis_result()` 方法中添加地图类型选择控件
- 新增 `on_map_type_changed()` 回调函数处理地图类型切换
- 新增 `refresh_current_map()` 方法刷新当前选中的地图
- 在 `map_template.html` 中添加 `loadLISAClusterGeoJSON()` 和 `loadEvolutionPatternGeoJSON()` JavaScript 函数
- 每种地图类型使用不同的颜色方案和图例

### 2. 可视化数据获取优化

**文件位置**：`backend/app/services/visualization_service.py`、`ui/services.py`

**核心能力**：
- 新增 `get_lisa_cluster_geojson()` 方法，直接返回 LISA 聚类 GeoJSON 数据供 UI 使用
- 新增 `get_evolution_pattern_geojson()` 方法，直接返回演化模式 GeoJSON 数据供 UI 使用
- 在 `ui/services.py` 中添加 `get_lisa_cluster_geojson()` 和 `get_evolution_pattern_geojson()` 方法
- 支持从后端 API 获取数据，API 不可用时自动从本地文件读取

**API 接口**：
- `GET /api/visualizations/lisa-cluster/geojson` - 获取 LISA 聚类 GeoJSON
- `GET /api/visualizations/evolution-pattern/geojson` - 获取演化模式 GeoJSON

### 3. 文件生成问题修复

**文件位置**：`backend/app/services/runtime_pipeline.py`

**修复内容**：
- 修复 LISA 聚类结果未保存的问题：在 `run_full_analysis()` 中添加 `_save_geojson(lisa_gdf, LISA_FILE)`
- 分析完成后自动生成可视化文件（LISA 聚类图、演化模式分布图）
- 确保 `outputs/visualizations/` 目录在可视化服务初始化时自动创建

**新增文件**：
- `outputs/runtime/lisa_cluster.geojson` - LISA 聚类结果文件

### 4. 地图模板功能增强

**文件位置**：`ui/map_template.html`

**核心能力**：
- 支持三种地图图层的独立管理（hotspotLayer、lisaLayer、evolutionLayer）
- 每种地图类型使用不同的颜色方案：
  - **热点地图**：红色（高）、橙色（中）、黄色（低）
  - **LISA聚类图**：红色（高-高）、橙色（高-低）、蓝色（低-高）、绿色（低-低）、灰色（不具有显著性）
  - **演化模式分布图**：紫色（振荡）、橙色（新增）、深红色（加强）、粉红色（逐渐减少）、蓝色（持续）
- 每种地图类型的弹窗信息针对性强，显示相关属性

## 技术实现细节

### 地图类型切换流程

1. 用户在下拉框中选择地图类型
2. `on_map_type_changed()` 回调触发
3. `refresh_current_map()` 根据选择调用对应方法：
   - `_load_hotspot_map()` - 加载热点地图
   - `_load_lisa_map()` - 加载 LISA 聚类图
   - `_load_evolution_map()` - 加载演化模式分布图
4. 通过 `QWebEngineView.page().runJavaScript()` 调用 HTML 中的 JavaScript 函数
5. JavaScript 函数清除旧图层，加载新 GeoJSON 数据，自动适应边界

### 数据获取策略

1. **优先使用 API**：通过 HTTP 请求获取最新数据
2. **降级到本地文件**：API 不可用时从 `outputs/runtime/` 目录读取
3. **错误处理**：友好的错误提示，不影响其他功能

## 向后兼容性

- ✅ 所有 3.0 版本的 API 接口完全保留
- ✅ 所有 3.0 版本的核心功能正常工作
- ✅ 热点地图功能保持不变，新增功能为可选
- ✅ 数据库接口（PostGIS/MySQL）保持兼容

## 使用指南

### 在 PyQt6 UI 中使用地图类型切换

1. 启动 PyQt6 界面：`cd ui && python main_ui.py`
2. 上传数据并执行风险分析
3. 在"风险识别"结果页面，使用"地图类型"下拉框选择：
   - **热点地图**：查看风险热点分布
   - **LISA聚类图**：查看空间自相关聚类模式
   - **演化模式分布图**：查看时空演化趋势
4. 点击"刷新地图"按钮可重新加载当前选中的地图类型
5. 在地图上点击任意区域查看详细信息

### 通过 API 获取可视化数据

```bash
# 获取 LISA 聚类 GeoJSON
curl http://127.0.0.1:5000/api/visualizations/lisa-cluster/geojson

# 获取演化模式 GeoJSON
curl http://127.0.0.1:5000/api/visualizations/evolution-pattern/geojson
```

## 已知问题与限制

1. 地图类型切换时，如果数据尚未生成，会显示错误提示（这是预期行为）
2. 演化模式判断基于简化的规则，未来可扩展为更复杂的模式识别算法
3. 可视化文件的自动生成在分析流程中，如果分析失败则不会生成

## 下一步计划

- [ ] 添加地图图例显示（在 UI 中显示颜色说明）
- [ ] 支持地图图层叠加显示（同时显示多种地图类型）
- [ ] 优化演化模式识别算法，支持完整的 17 类模式
- [ ] 添加地图导出功能（导出当前显示的地图为图片）
- [ ] 支持地图时间轴播放（动态显示演化过程）

## 贡献者

- 平台 3.5 版本由 AI 助手基于用户需求完成升级

## 版本历史

- **v3.6** (2025-11-22) - 完善升级：地图切换修复、图例优化、图表实现、报告生成修复（详见 CHANGELOG_3.6.md）
- **v3.5** (2025-11-22) - UI 交互升级：地图类型切换、可视化集成、文件生成修复
- **v3.0** (2025-11-22) - 重大升级：结构化报告、三级预警、增强可视化、策略模板
- **v2.0** (2025-11-21) - 基础版本：Runtime Pipeline、API 接口、多端体验

## 3.6 版本修复说明

v3.6 版本修复了 v3.5 版本中的以下问题：
- 地图切换功能确认在同一窗口中正常工作
- 图例显示优化，字体清晰可读
- 实现了综合仪表盘、趋势折线图、时段分布柱状图
- 修复了报告生成功能，确保文件正确生成
- 分析完成后自动生成所有可视化成果和报告

详细内容请参考 `CHANGELOG_3.6.md`。

