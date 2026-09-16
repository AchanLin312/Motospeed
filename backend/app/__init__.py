"""
Flask 应用初始化。

该模块围绕《论文.md》中“科技驱动、数据赋能、协同共治”的总体思路，
创建后端应用实例并注册路由蓝图，确保所有空间分析与预警能力能够以
API 形式供前端与外部系统调用。
"""
from flask import Flask, render_template_string, send_file, jsonify, send_from_directory
from pathlib import Path

from .config import get_config
from .routes.upload import upload_bp
from .routes.analysis import analysis_bp
from .routes.feedback import feedback_bp
from .routes.reports import reports_bp
from .routes.alerts import alerts_bp
from .routes.visualizations import visualizations_bp
from .routes.charts import charts_bp
from .routes.interpretation import interpretation_bp
from .routes.snapshots import snapshots_bp
from .routes.logs import logs_bp
from .services.runtime_pipeline import bootstrap_runtime_assets, MAP_FILE


def create_app(config_name: str = "development") -> Flask:
    """
    构建 Flask 应用。

    :param config_name: 配置段名，默认开发模式。
    """
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    bootstrap_runtime_assets()

    # 蓝图注册
    app.register_blueprint(upload_bp, url_prefix="/api/upload")
    app.register_blueprint(analysis_bp, url_prefix="/api")
    app.register_blueprint(feedback_bp, url_prefix="/api/feedback")
    # 3.0 新增路由
    app.register_blueprint(reports_bp, url_prefix="/api")
    app.register_blueprint(alerts_bp, url_prefix="/api")
    app.register_blueprint(visualizations_bp, url_prefix="/api")
    # 3.6 新增路由
    app.register_blueprint(charts_bp, url_prefix="/api")
    # 4.0 新增路由
    app.register_blueprint(interpretation_bp, url_prefix="/api/interpretation")
    app.register_blueprint(snapshots_bp, url_prefix="/api/snapshots")
    app.register_blueprint(logs_bp, url_prefix="/api/logs")

    @app.route("/")
    def index():
        """交互式控制台首页（v4.0）。"""
        # 加载v4.0主页面
        main_template_path = Path(__file__).parent / "templates" / "index_v4.html"
        if main_template_path.exists():
            with open(main_template_path, "r", encoding="utf-8") as f:
                return f.read()
        # 降级到3.0版本
        html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>数治骑迹 控制台</title>
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            padding: 0;
            font-family: "PingFang SC", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, sans-serif;
            background: #f5f8ff;
            color: #1f2a44;
        }
        header {
            background: linear-gradient(120deg, #165DFF, #3E8BFF);
            color: #fff;
            padding: 32px 24px;
            text-align: center;
        }
        header h1 { margin: 0 0 8px; font-size: 32px; }
        header p { margin: 0; opacity: 0.9; }
        main {
            max-width: 1200px;
            margin: -40px auto 40px;
            padding: 0 16px;
        }
        section {
            background: #fff;
            border-radius: 16px;
            box-shadow: 0 12px 24px rgba(22,93,255,0.08);
            padding: 24px;
            margin-bottom: 24px;
        }
        h2 {
            margin-top: 0;
            font-size: 20px;
            color: #0E1E5B;
        }
        form { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
        input, select, button, textarea {
            font: inherit;
            border: 1px solid #cfd8ff;
            border-radius: 8px;
            padding: 10px 14px;
        }
        input[type="file"] {
            border: 1px dashed #a3b5ff;
            padding: 14px;
            width: 320px;
        }
        button {
            background: #165DFF;
            color: white;
            border: none;
            cursor: pointer;
            transition: 0.2s;
        }
        button.secondary { background: #fff; color: #165DFF; border: 1px solid #165DFF; }
        button:hover { opacity: 0.9; }
        #mapFrame {
            width: 100%;
            height: 420px;
            border: none;
            border-radius: 12px;
            background: #f0f2ff;
        }
        .status {
            margin-top: 12px;
            padding: 12px;
            border-radius: 8px;
            background: #f5f8ff;
            font-size: 14px;
            white-space: pre-wrap;
        }
        .status.ok { border-left: 4px solid #28a745; }
        .status.err { border-left: 4px solid #d93025; color: #b11c1c; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
            font-size: 14px;
        }
        th, td {
            border-bottom: 1px solid #eff2ff;
            padding: 8px 6px;
            text-align: left;
        }
        th {
            color: #5b6da7;
            font-weight: 600;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 12px;
            margin-top: 12px;
        }
        .card {
            background: #f8faff;
            border-radius: 12px;
            padding: 16px;
            border: 1px solid #e2e8ff;
        }
        .card strong { display: block; color: #165DFF; font-size: 24px; }
        textarea { width: 100%; min-height: 90px; resize: vertical; }
        @media (max-width: 768px) {
            form { flex-direction: column; align-items: stretch; }
            input[type="file"] { width: 100%; }
        }
    </style>
</head>
<body>
    <header>
        <h1>数治骑迹 控制台</h1>
        <p>上传 → 分析 → 导出 → 反馈 一站式演示</p>
    </header>
    <main>
        <section>
            <h2>📁 上传轨迹 CSV</h2>
            <form id="uploadForm">
                <input type="file" name="file" accept=".csv" required />
                <button type="submit">开始上传</button>
                <button type="button" class="secondary" id="loadSummaryBtn">读取最新分析</button>
            </form>
            <div id="uploadStatus" class="status"></div>
        </section>

        <section>
            <h2>🔍 执行风险分析</h2>
            <form id="analysisForm">
                <label>超速阈值 (km/h)
                    <input type="number" id="thresholdInput" value="20" step="1" />
                </label>
                <label>网格大小 (度)
                    <input type="number" id="cellSizeInput" value="0.0045" step="0.0005" />
                </label>
                <button type="button" id="analysisBtn">运行分析</button>
            </form>
            <div class="grid" id="summaryGrid"></div>
            <div id="analysisStatus" class="status"></div>
        </section>

        <section>
            <h2>🌐 热点地图</h2>
            <iframe id="mapFrame" title="热点地图（高德底图）"></iframe>
            <div class="status" id="mapHint">执行一次风险分析后自动刷新最新地图。</div>
        </section>

        <section>
            <h2>📊 热点列表</h2>
            <div>
                <label>风险等级筛选
                    <select id="riskFilter">
                        <option value="all">全部</option>
                        <option value="high">高风险</option>
                        <option value="medium">中风险</option>
                        <option value="low">低风险</option>
                    </select>
                </label>
                <button type="button" id="hotspotRefresh">刷新</button>
                <button type="button" id="exportBtn" class="secondary">导出 CSV</button>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>区域名称</th>
                        <th>等级</th>
                        <th>Z 值</th>
                        <th>轨迹数</th>
                        <th>时间段</th>
                    </tr>
                </thead>
                <tbody id="hotspotTable">
                    <tr><td colspan="5">暂无数据</td></tr>
                </tbody>
            </table>
            <div id="hotspotStatus" class="status"></div>
        </section>

        <section>
            <h2>💬 上传反馈</h2>
            <form id="feedbackForm">
                <input type="text" id="feedbackArea" placeholder="关联热点 ID（可选）" />
                <input type="text" id="feedbackLon" placeholder="经度 113.0" />
                <input type="text" id="feedbackLat" placeholder="纬度 28.1" />
                <textarea id="feedbackContent" placeholder="现场情况/处置建议" required></textarea>
                <button type="submit">提交反馈</button>
            </form>
            <div id="feedbackStatus" class="status"></div>
        </section>
    </main>

    <script>
        const uploadForm = document.getElementById("uploadForm");
        const uploadStatus = document.getElementById("uploadStatus");
        const analysisStatus = document.getElementById("analysisStatus");
        const mapFrame = document.getElementById("mapFrame");
        const mapHint = document.getElementById("mapHint");
        const summaryGrid = document.getElementById("summaryGrid");
        const hotspotTable = document.getElementById("hotspotTable");
        const hotspotStatus = document.getElementById("hotspotStatus");
        const feedbackForm = document.getElementById("feedbackForm");
        const feedbackStatus = document.getElementById("feedbackStatus");

        function setStatus(el, message, ok = true) {
            if (!el) return;
            el.textContent = message || "";
            el.className = "status " + (message ? (ok ? "ok" : "err") : "");
        }

        async function fetchJSON(url, options = {}) {
            const resp = await fetch(url, options);
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(data.error || resp.statusText);
            return data;
        }

        uploadForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const formData = new FormData(uploadForm);
            try {
                setStatus(uploadStatus, "正在上传...", true);
                const result = await fetchJSON("/api/upload", {
                    method: "POST",
                    body: formData
                });
                setStatus(uploadStatus, "上传成功：共 " + result.uploaded_rows + " 行", true);
            } catch (err) {
                setStatus(uploadStatus, "上传失败：" + err.message, false);
            }
        });

        document.getElementById("analysisBtn").addEventListener("click", async () => {
            const threshold = Number(document.getElementById("thresholdInput").value) || 20;
            const cellSize = Number(document.getElementById("cellSizeInput").value) || 0.0045;
            try {
                setStatus(analysisStatus, "正在执行分析...", true);
                const result = await fetchJSON("/api/analysis", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        overspeed_threshold: threshold,
                        cell_size_deg: cellSize
                    })
                });
                renderSummary(result);
                refreshMap();
                loadHotspots();
                setStatus(analysisStatus, "分析完成（热点数量：" + result.hotspot_count + "）", true);
            } catch (err) {
                setStatus(analysisStatus, "分析失败：" + err.message, false);
            }
        });

        document.getElementById("loadSummaryBtn").addEventListener("click", loadSummary);

        document.getElementById("hotspotRefresh").addEventListener("click", () => {
            loadHotspots();
        });

        document.getElementById("exportBtn").addEventListener("click", async () => {
            const level = document.getElementById("riskFilter").value;
            try {
                setStatus(hotspotStatus, "正在导出...", true);
                const result = await fetchJSON(`/api/export?riskLevel=${level}`);
                setStatus(hotspotStatus, "导出成功，文件路径：" + result.csv_path, true);
            } catch (err) {
                setStatus(hotspotStatus, "导出失败：" + err.message, false);
            }
        });

        feedbackForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const payload = {
                area_id: document.getElementById("feedbackArea").value || null,
                lon: document.getElementById("feedbackLon").value,
                lat: document.getElementById("feedbackLat").value,
                content: document.getElementById("feedbackContent").value
            };
            try {
                setStatus(feedbackStatus, "提交中...", true);
                const result = await fetchJSON("/api/feedback", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                setStatus(feedbackStatus, "提交成功，反馈ID：" + result.feedback_id, true);
                feedbackForm.reset();
            } catch (err) {
                setStatus(feedbackStatus, "反馈失败：" + err.message, false);
            }
        });

        async function loadSummary() {
            try {
                setStatus(analysisStatus, "正在读取最新分析...", true);
                const result = await fetchJSON("/api/analysis");
                renderSummary(result);
                refreshMap();
                loadHotspots();
                setStatus(analysisStatus, "已加载最近一次分析结果。", true);
            } catch (err) {
                setStatus(analysisStatus, "暂无分析记录：" + err.message, false);
            }
        }

        function renderSummary(data) {
            if (!data) {
                summaryGrid.innerHTML = "";
                return;
            }
            summaryGrid.innerHTML = `
                <div class="card"><span>网格数量</span><strong>${data.grid_count || "-"}</strong></div>
                <div class="card"><span>热点数量</span><strong>${data.hotspot_count || "-"}</strong></div>
                <div class="card"><span>全局 Moran's I</span><strong>${data.global_moran?.moran_i?.toFixed?.(3) ?? "-"}</strong></div>
                <div class="card"><span>趋势结果</span><strong>${data.trend?.trend || "-"}</strong></div>
            `;
        }

        async function loadHotspots() {
            const level = document.getElementById("riskFilter").value;
            try {
                setStatus(hotspotStatus, "加载中...", true);
                const geojson = await fetchJSON(`/api/hotspots/geojson?riskLevel=${level}`);
                const rows = geojson.features || [];
                if (!rows.length) {
                    hotspotTable.innerHTML = "<tr><td colspan='5'>当前没有热点数据，请先执行风险分析。</td></tr>";
                } else {
                    hotspotTable.innerHTML = rows.map((feature) => {
                        const props = feature.properties || {};
                        return `
                            <tr>
                                <td>${props.area_name || props.areaName || feature.id || "-"}</td>
                                <td>${props.risk_level || "-"}</td>
                                <td>${props.gi_score?.toFixed?.(2) ?? "-"}</td>
                                <td>${props.trajectory_count ?? "-"}</td>
                                <td>${props.time_slice || "-"}</td>
                            </tr>
                        `;
                    }).join("");
                }
                setStatus(hotspotStatus, "已加载热点：" + rows.length + " 条", true);
            } catch (err) {
                hotspotTable.innerHTML = "<tr><td colspan='5'>无法获取热点：" + err.message + "</td></tr>";
                setStatus(hotspotStatus, "热点获取失败：" + err.message, false);
            }
        }

        function refreshMap() {
            mapFrame.src = "/map/latest?ts=" + Date.now();
            mapHint.textContent = "若地图未显示，请先执行一次分析以生成最新 HTML。";
        }

        loadSummary();
    </script>
</body>
</html>
        """
        return render_template_string(html_template)

    @app.get("/map/latest")
    def latest_map():
        """返回最新热点 HTML 地图。"""
        if not MAP_FILE.exists():
            return jsonify({"error": "尚未生成风险地图，请先执行分析"}), 404
        return send_file(MAP_FILE)
    
    @app.route("/templates/<path:filename>")
    def serve_template(filename):
        """提供模板文件服务（用于v4.0模块化加载）。"""
        template_dir = Path(__file__).parent / "templates"
        file_path = template_dir / filename
        if file_path.exists() and file_path.is_file():
            return send_file(file_path)
        return jsonify({"error": "文件不存在"}), 404
    
    @app.route("/uploads/images/<path:filename>")
    def serve_uploaded_image(filename):
        """提供上传的图片文件服务。"""
        from pathlib import Path
        upload_dir = Path(app.config.get("UPLOAD_DIR", "uploads"))
        image_dir = upload_dir / "images"
        file_path = image_dir / filename
        if file_path.exists() and file_path.is_file():
            return send_file(str(file_path))
        return jsonify({"error": f"图片文件不存在: {file_path}"}), 404
    
    @app.route("/uploads/feedback/<path:filename>")
    def serve_feedback_image(filename):
        """提供反馈的图片文件服务。"""
        from pathlib import Path
        upload_dir = Path(app.config.get("UPLOAD_DIR", "uploads"))
        feedback_dir = upload_dir / "feedback"
        file_path = feedback_dir / filename
        if file_path.exists() and file_path.is_file():
            return send_file(str(file_path))
        return jsonify({"error": f"图片文件不存在: {file_path}"}), 404

    @app.route("/health")
    def health_check():
        """基础健康检查，便于部署验证。"""
        return {"status": "ok"}

    return app

