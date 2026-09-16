@echo off
chcp 65001 >nul
echo 启动数治骑迹平台 Docker 容器...

REM 检查Docker是否运行
docker info >nul 2>&1
if errorlevel 1 (
    echo 错误: Docker未运行，请先启动Docker Desktop
    pause
    exit /b 1
)

REM 构建并启动
docker-compose up -d

echo 服务已启动！
echo 访问地址: http://localhost:5000
echo.
echo 查看日志: docker-compose logs -f
echo 停止服务: docker-compose down
pause

