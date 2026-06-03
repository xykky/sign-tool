#!/bin/bash
# ===========================================
#  Sign Tool 卸载脚本
#  用法: sudo bash uninstall.sh [--keep-data]
#
#  --keep-data  保留配置文件和数据库
# ===========================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="sign-tool"
NGINX_CONF="/etc/nginx/sites-available/$SERVICE_NAME"
NGINX_LINK="/etc/nginx/sites-enabled/$SERVICE_NAME"
KEEP_DATA=false

[[ "$1" == "--keep-data" ]] && KEEP_DATA=true

echo "=========================================="
echo "  Sign Tool 卸载"
echo "=========================================="
echo ""

# 1. 停止服务
echo "[1/4] 停止服务..."
systemctl stop "$SERVICE_NAME" 2>/dev/null && echo "  服务已停止" || echo "  服务未运行"
systemctl disable "$SERVICE_NAME" 2>/dev/null && echo "  服务已禁用" || true

# 2. 删除 systemd 服务
echo "[2/4] 删除服务文件..."
rm -f "/etc/systemd/system/$SERVICE_NAME.service"
systemctl daemon-reload
echo "  已删除 systemd 服务"

# 3. 删除 Nginx 配置
echo "[3/4] 删除 Nginx 配置..."
rm -f "$NGINX_CONF" "$NGINX_LINK"
if command -v nginx &>/dev/null; then
    nginx -t 2>/dev/null && systemctl reload nginx 2>/dev/null || true
fi
echo "  已删除 Nginx 配置"

# 4. 处理项目目录
echo "[4/4] 处理项目目录..."
if [ ! -d "$SCRIPT_DIR/.git" ]; then
    echo "  当前目录不是 git 仓库，跳过文件清理"
else
    if $KEEP_DATA; then
        echo "  --keep-data 模式: 仅保留 config.toml 和 sign.db"
        cd "$SCRIPT_DIR"
        find "$SCRIPT_DIR" -mindepth 1 -maxdepth 1 \
            ! -name ".git" \
            ! -name "config.toml" \
            ! -name "sign.db" \
            -exec rm -rf {} + 2>/dev/null || true
        echo "  已清理代码文件"
    else
        echo "  注意: 项目文件未删除（避免误删其他文件）"
        echo "  如需完全删除: rm -rf $SCRIPT_DIR"
    fi
fi

echo ""
echo "=========================================="
echo "  卸载完成！"
echo "=========================================="
echo ""
if $KEEP_DATA; then
    echo "  配置和数据库保留在: $SCRIPT_DIR"
    echo "  重新部署: cd $SCRIPT_DIR && sudo bash install.sh"
fi
echo ""
