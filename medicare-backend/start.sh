#!/bin/bash
# 药安守护后端 - 一键启动脚本（macOS / Linux）
set -e

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║        药安守护后端  一键启动脚本          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 检查 Docker 是否运行 ──────────────────────────────────────
if ! docker info > /dev/null 2>&1; then
    echo "[错误] Docker 未运行，请先启动 Docker Desktop（或 Docker 守护进程）再执行本脚本。"
    exit 1
fi
echo "[OK] Docker 已运行"

# ── 检查 .env 文件 ────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "[提示] 未找到 .env 文件，正在从 .env.example 复制..."
    cp .env.example .env
    echo "[提示] 已生成 .env，请填写以下必填项后重新运行："
    echo "        SECRET_KEY        (32位随机字符串，可用: openssl rand -hex 32)"
    echo "        POSTGRES_PASSWORD (数据库密码)"
    echo "        DATABASE_URL      (含上方密码)"
    echo ""
    echo "快速生成 SECRET_KEY："
    echo "  openssl rand -hex 32"
    echo ""
    # 尝试用系统编辑器打开
    if command -v code > /dev/null 2>&1; then
        code .env
    elif command -v nano > /dev/null 2>&1; then
        nano .env
    else
        open .env 2>/dev/null || vi .env
    fi
    exit 0
fi
echo "[OK] .env 文件存在"

# ── 构建最新镜像 ──────────────────────────────────────────────
echo ""
echo "[1/3] 构建镜像（如代码有更新会自动重新构建）..."
docker compose build --quiet
echo "[OK] 镜像构建完成"

# ── 停止旧容器 ────────────────────────────────────────────────
echo ""
echo "[2/3] 停止并移除旧容器..."
docker compose down --remove-orphans > /dev/null 2>&1 || true
echo "[OK] 旧容器已清理"

# ── 启动所有服务 ──────────────────────────────────────────────
echo ""
echo "[3/3] 启动所有服务（postgres / redis / api / worker / beat）..."
docker compose up -d
echo "[OK] 服务已启动"

# ── 等待 API 就绪 ─────────────────────────────────────────────
echo ""
echo "等待 API 服务就绪（最多 30 秒）..."
count=0
until curl -s http://localhost:8000/health > /dev/null 2>&1; do
    count=$((count + 1))
    if [ $count -ge 15 ]; then
        echo "[警告] API 30秒内未就绪，可能仍在初始化，请稍后手动访问。"
        break
    fi
    echo "  还在启动中... ($count/15)"
    sleep 2
done

if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "[OK] API 服务已就绪！"
fi

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║              服务访问地址                 ║"
echo "╠══════════════════════════════════════════╣"
echo "║  API 接口:   http://localhost:8000        ║"
echo "║  接口文档:   http://localhost:8000/docs   ║"
echo "║  健康检查:   http://localhost:8000/health ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "常用命令："
echo "  查看日志:     docker compose logs -f api"
echo "  查看所有日志: docker compose logs -f"
echo "  停止服务:     docker compose down"
echo "  重启 API:     docker compose restart api"
echo ""

# 尝试自动打开浏览器
if command -v open > /dev/null 2>&1; then
    open "http://localhost:8000/docs" 2>/dev/null || true
elif command -v xdg-open > /dev/null 2>&1; then
    xdg-open "http://localhost:8000/docs" 2>/dev/null || true
fi
