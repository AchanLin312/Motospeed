"""
WSGI入口文件，用于生产环境部署（Docker/Gunicorn）
"""
from app import create_app

app = create_app("production")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

