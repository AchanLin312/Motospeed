# 数治骑迹平台 Docker 镜像
# 支持跨平台部署，无需在目标机器上安装Python环境

FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（geopandas等需要）
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libproj-dev \
    libgeos-dev \
    libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV GDAL_DATA=/usr/share/gdal

# 复制依赖文件
COPY requirements.txt backend/requirements.txt ./

# 安装Python依赖
RUN pip install --no-cache-dir -r backend/requirements.txt && \
    pip install --no-cache-dir gunicorn  # 生产环境WSGI服务器

# 复制项目文件
COPY . .

# 创建必要的目录
RUN mkdir -p outputs/runtime outputs/logs outputs/reports outputs/charts \
    outputs/visualizations outputs/snapshots uploads/images uploads/feedback

# 暴露端口
EXPOSE 5000

# 启动命令（两种方式可选）
# 方式1：直接运行（开发模式）
CMD ["python", "backend/run.py"]

# 方式2：使用Gunicorn（生产模式，取消注释使用）
# CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "backend.wsgi:app"]

