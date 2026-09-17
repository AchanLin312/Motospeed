# 数治骑迹 V2 后端镜像（Flask + 空间分析流水线）
# 构建：docker build -t motospeed-v2 .
# 运行：docker compose up -d   （浏览器访问 http://localhost:5000）
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

# 时区（基础镜像自带 tzdata，无需 apt 安装；分析时间戳统一为北京时间）
RUN ln -fs /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone

WORKDIR /app

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# 仅复制运行所需代码；数据与文档经 Volume 挂载 / 交付包提供
COPY backend ./backend
COPY spatial_analysis ./spatial_analysis

WORKDIR /app/backend
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=4)" || exit 1

CMD ["python", "run.py"]
