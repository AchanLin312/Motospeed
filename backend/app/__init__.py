"""
Flask 应用初始化。

该模块围绕《论文.md》中“科技驱动、数据赋能、协同共治”的总体思路，
创建后端应用实例并注册路由蓝图，确保所有空间分析与预警能力能够以
API 形式供前端与外部系统调用。
"""
import os

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
from .routes.api_v2 import api_v2_bp
from .services.runtime_pipeline import bootstrap_runtime_assets, MAP_FILE


def _log_security_warnings(app: Flask) -> None:
    """密钥治理（AC26/AC30）：启动时检查敏感配置，仅告警不阻断（开发模式可用）。"""
    if not os.environ.get("V2_ADMIN_TOKEN"):
        app.logger.warning(
            "[密钥治理] 未配置 V2_ADMIN_TOKEN：管理模式接口处于开发放行状态，"
            "生产部署必须通过环境变量设置（请求头 X-Admin-Token 校验）。")
    if not (os.environ.get("LLM_API_BASE") and os.environ.get("LLM_API_KEY")):
        app.logger.warning(
            "[密钥治理] 未配置 LLM_API_BASE/LLM_API_KEY：AI 治理建议将使用"
            "知识库规则模板兜底（不依赖外部 LLM 服务）。")


def create_app(config_name: str = "development") -> Flask:
    """
    构建 Flask 应用。

    :param config_name: 配置段名，默认开发模式。
    """
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    bootstrap_runtime_assets()
    _log_security_warnings(app)

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

    # V2 改造：外卖多风险识别平台（手册 15 接口，/api/v2 前缀；/api 保留 v1 兼容）
    app.register_blueprint(api_v2_bp, url_prefix="/api/v2")

    def _read_template(name: str) -> str | None:
        p = Path(__file__).parent / "templates" / name
        return p.read_text(encoding="utf-8") if p.exists() else None

    @app.route("/")
    def index():
        """V2 平台首页（业务/管理双模式）。"""
        html = _read_template("index_v5.html")
        if html:
            return html
        return render_template_string(
            "<h2>缺少 index_v5.html</h2><p>请检查 backend/app/templates 目录。</p>")

    @app.route("/v1")
    def index_v1():
        """V1 工作台（v4.0，兼容入口）。"""
        html = _read_template("index_v4.html")
        if html:
            return html
        return render_template_string("<h2>缺少 index_v4.html</h2>")

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

