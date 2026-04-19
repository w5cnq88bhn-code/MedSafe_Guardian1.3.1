@echo off
chcp 65001 >nul
title 药安守护 - Docker 一键启动

echo.
echo ╔══════════════════════════════════════════╗
echo ║        药安守护后端  一键启动脚本          ║
echo ╚══════════════════════════════════════════╝
echo.

:: ── 检查 Docker 是否运行 ──────────────────────────────────────
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] Docker Desktop 未运行，请先启动 Docker Desktop 再执行本脚本。
    pause
    exit /b 1
)
echo [OK] Docker 已运行

:: ── 检查 .env 文件 ────────────────────────────────────────────
if not exist ".env" (
    echo [提示] 未找到 .env 文件，正在从 .env.example 复制...
    copy ".env.example" ".env" >nul
    echo [提示] 已生成 .env，请用记事本打开并填写以下必填项后重新运行：
    echo         SECRET_KEY        ^(32位随机字符串^)
    echo         POSTGRES_PASSWORD ^(数据库密码^)
    echo         DATABASE_URL      ^(含上方密码^)
    echo.
    echo 快速生成 SECRET_KEY 的方法：
    echo   在 PowerShell 中运行：
    echo   -join ((1..32) ^| ForEach-Object { '{0:x}' -f (Get-Random -Max 16) })
    echo.
    notepad ".env"
    pause
    exit /b 0
)
echo [OK] .env 文件存在

:: ── 拉取/构建最新镜像 ─────────────────────────────────────────
echo.
echo [1/3] 构建镜像（如代码有更新会自动重新构建）...
docker compose build --quiet
if %errorlevel% neq 0 (
    echo [错误] 镜像构建失败，请检查 Dockerfile 和网络连接。
    pause
    exit /b 1
)
echo [OK] 镜像构建完成

:: ── 停止旧容器（如有）────────────────────────────────────────
echo.
echo [2/3] 停止并移除旧容器...
docker compose down --remove-orphans >nul 2>&1
echo [OK] 旧容器已清理

:: ── 启动所有服务 ──────────────────────────────────────────────
echo.
echo [3/3] 启动所有服务（postgres / redis / api / worker / beat）...
docker compose up -d
if %errorlevel% neq 0 (
    echo [错误] 服务启动失败，请查看日志：docker compose logs
    pause
    exit /b 1
)

:: ── 等待 API 就绪 ─────────────────────────────────────────────
echo.
echo 等待 API 服务就绪（最多 30 秒）...
set /a count=0
:wait_loop
timeout /t 2 /nobreak >nul
curl -s http://localhost:8000/health >nul 2>&1
if %errorlevel% equ 0 goto ready
set /a count+=1
if %count% lss 15 (
    echo   还在启动中... ^(%count%/15^)
    goto wait_loop
)
echo [警告] API 30秒内未就绪，可能仍在初始化，请稍后手动访问。
goto show_info

:ready
echo [OK] API 服务已就绪！

:show_info
echo.
echo ╔══════════════════════════════════════════╗
echo ║              服务访问地址                 ║
echo ╠══════════════════════════════════════════╣
echo ║  API 接口:   http://localhost:8000        ║
echo ║  接口文档:   http://localhost:8000/docs   ║
echo ║  健康检查:   http://localhost:8000/health ║
echo ╚══════════════════════════════════════════╝
echo.
echo 常用命令：
echo   查看日志:     docker compose logs -f api
echo   查看所有日志: docker compose logs -f
echo   停止服务:     docker compose down
echo   重启 API:     docker compose restart api
echo.

:: 自动在浏览器打开接口文档（DEBUG 模式下可用）
start "" "http://localhost:8000/docs" >nul 2>&1

pause
