#!/bin/bash
# ===========================================
#  Sign Tool 一键部署脚本
#  用法: sudo bash install.sh [域名]
#  示例: sudo bash install.sh sign.example.com
# ===========================================

set -e

# ========== 配置 ==========
INSTALL_DIR="/opt/sign-tool"
PORT=2087
DOMAIN="${1:-_}"  # 默认 _ 表示匹配所有域名

echo "=========================================="
echo "  Sign Tool 一键部署"
echo "=========================================="
echo ""
echo "  安装目录: $INSTALL_DIR"
echo "  后端端口: $PORT"
echo "  域名: $([ "$DOMAIN" = "_" ] && echo "(未指定，使用IP访问)" || echo "$DOMAIN")"
echo ""

# 1. 安装系统依赖
echo "[1/7] 安装系统依赖..."
if command -v apt &> /dev/null; then
    apt update -qq
    apt install -y -qq python3 python3-pip python3-venv nginx curl
elif command -v yum &> /dev/null; then
    yum install -y python3 python3-pip nginx curl
elif command -v dnf &> /dev/null; then
    dnf install -y python3 python3-pip nginx curl
else
    echo "错误: 不支持的包管理器，请手动安装 python3 nginx"
    exit 1
fi

# 2. 检查 Python 版本
echo "[2/7] 检查 Python 版本..."
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  Python 版本: $PYTHON_VERSION"

# 3. 创建安装目录并复制文件
echo "[3/7] 复制项目文件..."
mkdir -p "$INSTALL_DIR"

# 复制项目文件（排除 .git, __pycache__ 等）
rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.venv' --exclude='sign.db' --exclude='config.toml' \
    ./ "$INSTALL_DIR/" 2>/dev/null || cp -r ./* "$INSTALL_DIR/"

cd "$INSTALL_DIR"

# 4. 创建虚拟环境并安装
echo "[4/7] 安装 Python 依赖..."
python3 -m venv .venv
source .venv/bin/activate
pip install -e . -q

# 5. 创建配置文件（如果不存在）
echo "[5/7] 检查配置文件..."
if [ ! -f config.toml ]; then
    cp config.toml.example config.toml
    echo "  已创建配置文件: $INSTALL_DIR/config.toml"
    echo "  请编辑配置文件填入账号信息"
else
    echo "  配置文件已存在，跳过"
fi

# 6. 安装 systemd 服务
echo "[6/7] 配置系统服务..."
cat > /etc/systemd/system/sign-tool.service << EOF
[Unit]
Description=Sign Tool Web Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python -m sign_tool web --host 127.0.0.1 --port $PORT
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# 7. 配置 Nginx
echo "[7/7] 配置 Nginx..."
cat > /etc/nginx/sites-available/sign-tool << EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # SSE 支持（签到进度实时推送）
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
EOF

ln -sf /etc/nginx/sites-available/sign-tool /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# 测试 Nginx 配置并重载
nginx -t && systemctl reload nginx

# 启动服务
systemctl daemon-reload
systemctl enable sign-tool
systemctl start sign-tool

echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo ""
echo "  访问地址:"
if [ "$DOMAIN" = "_" ]; then
    echo "    http://$(curl -s ifconfig.me 2>/dev/null || echo '你的服务器IP')"
else
    echo "    http://$DOMAIN"
fi
echo ""
echo "  配置文件: $INSTALL_DIR/config.toml"
echo ""
echo "  常用命令:"
echo "    查看状态: systemctl status sign-tool"
echo "    查看日志: journalctl -u sign-tool -f"
echo "    重启服务: systemctl restart sign-tool"
echo "    编辑配置: nano $INSTALL_DIR/config.toml"
echo ""
echo "  Cloudflare 可选配置:"
echo "    1. DNS 添加 A 记录 → 服务器IP，开启橙色云朵"
echo "    2. SSL/TLS 设置为 Full"
echo "    3. 访问: https://$([ "$DOMAIN" = "_" ] && echo "你的域名" || echo "$DOMAIN")"
echo ""
