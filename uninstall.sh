#!/bin/bash
# ===========================================
#  Sign Tool 卸载脚本
#  用法: sudo bash uninstall.sh [--keep-data]
# ===========================================

set -e

INSTALL_DIR="/opt/sign-tool"
SERVICE_NAME="sign-tool"
NGINX_CONF_AVAIL="/etc/nginx/sites-available/$SERVICE_NAME"
NGINX_CONF_ENABL="/etc/nginx/sites-enabled/$SERVICE_NAME"
KEEP_DATA=false

if [[ "$1" == "--keep-data" ]]; then
    KEEP_DATA=true
fi

echo "=========================================="
echo "  Sign Tool 卸载"
echo "=========================================="
echo ""

# 1. 停止并禁用服务
echo "[1/5] 停止服务..."
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl stop "$SERVICE_NAME"
    echo "  服务已停止"
else
    echo "  服务未运行，跳过"
fi

if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    echo "  服务已禁用"
fi

# 2. 删除 systemd 服务文件
echo "[2/5] 删除服务文件..."
if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
    rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    systemctl daemon-reload
    echo "  已删除 /etc/systemd/system/$SERVICE_NAME.service"
else
    echo "  服务文件不存在，跳过"
fi

# 3. 删除 Nginx 配置
echo "[3/5] 删除 Nginx 配置..."
if [ -f "$NGINX_CONF_AVAIL" ]; then
    rm -f "$NGINX_CONF_AVAIL"
    echo "  已删除 $NGINX_CONF_AVAIL"
else
    echo "  Nginx 可用配置不存在，跳过"
fi
if [ -L "$NGINX_CONF_ENABL" ]; then
    rm -f "$NGINX_CONF_ENABL"
    echo "  已删除 $NGINX_CONF_ENABL"
fi

# 重载 Nginx
if command -v nginx &>/dev/null; then
    nginx -t 2>/dev/null && systemctl reload nginx 2>/dev/null || true
    echo "  Nginx 已重载"
fi

# 4. 备份并删除安装目录
echo "[4/5] 处理安装目录 $INSTALL_DIR ..."
if [ -d "$INSTALL_DIR" ]; then
    if $KEEP_DATA; then
        # 只删除代码，保留配置和数据库
        echo "  --keep-data 模式: 保留 config.toml 和 sign.db"
        # 删除配置和数据库之外的所有文件
        find "$INSTALL_DIR" -mindepth 1 \
            ! -name "config.toml" \
            ! -name "sign.db" \
            ! -name ".git" \
            -exec rm -rf {} + 2>/dev/null || true
        echo "  已清理代码文件，配置和数据库保留在 $INSTALL_DIR"
    else
        rm -rf "$INSTALL_DIR"
        echo "  已删除 $INSTALL_DIR"
    fi
else
    echo "  安装目录不存在，跳过"
fi

# 5. 完成
echo "[5/5] 卸载完成"
echo ""
echo "=========================================="
echo "  卸载完成！"
echo "=========================================="
echo ""
if $KEEP_DATA; then
    echo "  配置和数据库保留在: $INSTALL_DIR"
    echo "  如需完全删除: sudo rm -rf $INSTALL_DIR"
else
    echo "  所有文件已删除"
fi
echo ""
