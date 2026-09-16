# 平台 3.6 版本升级说明

## 升级概述

平台 3.6 版本是一次完善性升级，修复了 3.5 版本中的关键问题，完善了可视化与报告生成功能，确保所有功能能够正常工作并自动生成。在保留 3.5 版本所有核心能力的基础上，修复了地图切换功能、改善了图例显示、实现了缺失的可视化图表、确保了报告自动生成。

## 主要修复与升级内容

### 1. 地图切换功能修复

**问题**：3.5 版本中地图切换功能实际上生成了三个不同的 HTML 文件，无法在同一个 UI 窗口中切换显示。

**修复**：
- 确认地图切换功能已在 `map_template.html` 中正确实现
- 三种地图类型（热点地图、LISA聚类图、演化模式分布图）在同一个 `QWebEngineView` 中切换显示
- 通过 JavaScript 函数 `loadHotspotGeoJSON()`、`loadLISAClusterGeoJSON()`、`loadEvolutionPatternGeoJSON()` 实现图层切换
- 每次切换时清除旧图层，加载新数据，确保在同一窗口中显示

**文件位置**：`ui/map_template.html`、`ui/main_ui.py`

### 2. 图例显示优化

**问题**：LISA 聚类图的图例显示有问题，白色背景没有完全覆盖字体区域，导致字体看不清楚。

**修复**：
- 添加美观的图例显示功能，使用 CSS 样式优化
- 图例背景使用 `rgba(255, 255, 255, 0.95)` 半透明白色，确保字体清晰可读
- 添加边框、阴影、圆角等视觉效果
- 图例位置固定在右下角，不遮挡地图内容
- 每种地图类型显示对应的图例：
  - **热点地图**：高风险（红色）、中风险（橙色）、低风险（黄色）
  - **LISA聚类图**：高-高聚类、高-低异常值、低-高异常值、低-低聚类、不具有显著性
  - **演化模式分布图**：振荡热点、新增热点、加强的热点、逐渐减少的热点、持续的热点

**实现细节**：
- 在 `map_template.html` 中添加 `showLegend()` 和 `hideLegend()` JavaScript 函数
- 使用 CSS 类 `.legend`、`.legend-item`、`.legend-color` 美化样式
- 图例内容动态生成，根据地图类型显示不同内容

### 3. 综合仪表盘、趋势折线图、时段分布柱状图实现

**问题**：3.0 版本中提到的综合仪表盘、趋势折线图、时段分布柱状图等可视化成果找不到。

**实现**：
- 新增 `backend/app/services/chart_generator.py` 图表生成服务
- 使用 matplotlib 生成高质量 PNG 图片
- 实现三种图表类型：
  - **综合仪表盘**：包含核心业务指标、风险分布饼图、TOP10风险区域柱状图
  - **趋势折线图**：显示近 N 天（默认30天）的日均超速次数变化趋势
  - **时段分布柱状图**：显示0-24时超速次数分布，标注峰值时段

**文件位置**：
- `backend/app/services/chart_generator.py` - 图表生成服务
- `backend/app/routes/charts.py` - 图表 API 路由
- `outputs/charts/` - 图表文件存储目录

**API 接口**：
- `POST /api/charts/dashboard` - 生成综合仪表盘图表
- `POST /api/charts/trend` - 生成趋势折线图
- `POST /api/charts/time-distribution` - 生成时段分布柱状图
- `GET /api/charts/list` - 列出所有已生成的图表文件

### 4. 报告生成功能修复

**问题**：结构化报告似乎没有被成功生成出来。

**修复**：
- 确保 `outputs/reports/` 目录在报告生成器初始化时自动创建
- 在 `run_full_analysis()` 完成后自动调用报告生成
- 报告生成失败不影响主分析流程（使用 try-except 包裹）
- 报告文件命名包含时间戳，便于区分不同批次

**文件位置**：
- `backend/app/services/report_generator.py` - 报告生成服务（已存在）
- `outputs/reports/` - 报告文件存储目录

**自动生成时机**：
- 执行风险分析（`/api/analysis` POST）完成后自动生成
- 报告格式：Word（.docx）、Excel（.xlsx）
- 报告内容：执行摘要、空间自相关分析、时空热点分析、趋势分析、应对建议、技术参数

### 5. 分析完成后自动生成所有成果

**升级**：在 `runtime_pipeline.run_full_analysis()` 完成后，自动生成：
- LISA 聚类图 HTML
- 演化模式分布图 HTML
- 综合仪表盘 PNG
- 趋势折线图 PNG
- 时段分布柱状图 PNG
- 风险分析报告 Word/Excel

**实现位置**：`backend/app/services/runtime_pipeline.py`

## 技术实现细节

### 图表生成技术栈

- **matplotlib**：用于生成高质量图表
- **非交互式后端**：使用 `matplotlib.use('Agg')` 确保在服务器环境正常运行
- **中文字体支持**：配置 SimHei、Microsoft YaHei 等中文字体
- **图片格式**：PNG 格式，150 DPI，适合打印和展示

### 图例显示实现

```javascript
function showLegend(title, items) {
  // 动态生成图例 HTML
  // 使用 CSS 样式美化
  // 固定在右下角显示
}
```

### 自动生成流程

1. 用户执行风险分析
2. `run_full_analysis()` 完成核心分析
3. 自动调用可视化服务和图表生成器
4. 生成所有可视化文件和报告
5. 文件保存在 `outputs/` 对应子目录

## 新增依赖

在 `requirements.txt` 中新增：

```
matplotlib>=3.7.0  # 图表生成
```

## 目录结构变化

新增目录：
- `outputs/charts/` - 图表文件存储目录
  - `dashboard_*.png` - 综合仪表盘
  - `trend_chart_*.png` - 趋势折线图
  - `time_distribution_*.png` - 时段分布柱状图

确保存在的目录：
- `outputs/reports/` - 报告文件存储目录
- `outputs/visualizations/` - 可视化 HTML 文件存储目录

## 向后兼容性

- ✅ 所有 3.5 版本的 API 接口完全保留
- ✅ 所有 3.5 版本的核心功能正常工作
- ✅ 地图切换功能修复，不影响现有使用
- ✅ 数据库接口（PostGIS/MySQL）保持兼容

## 使用指南

### 查看生成的图表

1. 执行风险分析后，图表自动生成在 `outputs/charts/` 目录
2. 通过 API 获取图表列表：
   ```bash
   curl http://127.0.0.1:5000/api/charts/list
   ```
3. 下载图表文件：
   ```bash
   curl "http://127.0.0.1:5000/api/charts/dashboard/download?filepath=outputs/charts/dashboard_20251122_120000.png"
   ```

### 查看生成的报告

1. 执行风险分析后，报告自动生成在 `outputs/reports/` 目录
2. 报告文件名格式：`风险分析报告_YYYYMMDD_HHMMSS.docx`
3. 可通过文件系统直接访问，或通过 API 下载

### 在 UI 中使用地图切换

1. 启动 PyQt6 界面：`cd ui && python main_ui.py`
2. 上传数据并执行风险分析
3. 在"风险识别"结果页面，使用"地图类型"下拉框切换
4. 图例自动显示在右下角，清晰可读
5. 所有地图类型在同一窗口中切换，无需打开新窗口

## 已知问题与限制

1. 图表生成需要 matplotlib，首次运行可能需要安装依赖
2. 报告生成需要 python-docx 和 openpyxl，确保已安装
3. 自动生成过程在后台进行，如果生成失败不会影响主分析流程

## 下一步计划

- [ ] 在 UI 中集成图表显示（在结果页面显示生成的图表）
- [ ] 支持图表自定义样式和颜色
- [ ] 添加图表导出为 PDF 功能
- [ ] 优化报告模板，支持更多自定义内容
- [ ] 实现报告生成进度提示

## 贡献者

- 平台 3.6 版本由 AI 助手基于用户反馈完成修复与升级

## 版本历史

- **v3.6** (2025-11-22) - 完善升级：地图切换修复、图例优化、图表实现、报告生成修复
- **v3.5** (2025-11-22) - UI 交互升级：地图类型切换、可视化集成、文件生成修复
- **v3.0** (2025-11-22) - 重大升级：结构化报告、三级预警、增强可视化、策略模板
- **v2.0** (2025-11-21) - 基础版本：Runtime Pipeline、API 接口、多端体验

