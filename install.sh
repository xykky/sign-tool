#!/bin/bash
set -e

# ========== 配置 ==========
INSTALL_DIR="/opt/sign-tool"
PORT=2087
DOMAIN="${1:-localhost}"

echo "=========================================="
echo "  Sign Tool 一键部署"
echo "  域名: $DOMAIN"
echo "  后端端口: $PORT"
echo "=========================================="

# 1. 安装系统依赖
echo "[1/7] 安装系统依赖..."
if command -v apt &> /dev/null; then
    apt update -qq && apt install -y -qq python3 python3-pip python3-venv nginx curl git
elif command -v yum &> /dev/null; then
    yum install -y python3 python3-pip nginx curl git
elif command -v dnf &> /dev/null; then
    dnf install -y python3 python3-pip nginx curl git
else
    echo "不支持的包管理器，请手动安装: python3 python3-pip python3-venv nginx"
    exit 1
fi

# 2. 创建安装目录并复制文件
echo "[2/7] 复制项目文件..."
mkdir -p $INSTALL_DIR

# 如果是从 git 仓库运行，直接复制
if [ -d ".git" ]; then
    cp -r ./* $INSTALL_DIR/
else
    echo "请先 git clone 项目到本地，然后在项目目录运行此脚本"
    exit 1
fi

cd $INSTALL_DIR

# 3. 创建虚拟环境并安装
echo "[3/7] 安装 Python 依赖..."
python3 -m venv .venv
source .venv/bin/activate
pip install -e . -q

# 4. 创建配置文件（如果不存在）
if [ ! -f config.toml ]; then
    cp config.toml.example config.toml
    echo "已创建配置文件: $INSTALL_DIR/config.toml"
fi

# 5. 安装 systemd 服务
echo "[4/7] 配置系统服务..."
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

# 6. 配置 Nginx
echo "[5/7] 配置 Nginx..."
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

echo "[6/7] 检测 Nginx 配置..."
nginx -t && systemctl reload nginx

# 7. 启动服务
echo "[7/7] 启动服务..."
systemctl daemon-reload
systemctl enable sign-tool
systemctl start sign-tool

echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo ""
echo "  访问地址: http://$DOMAIN"
echo "  配置文件: $INSTALL_DIR/config.toml"
echo ""
echo "  常用命令:"
echo "    查看状态: systemctl status sign-tool"
echo "    查看日志: journalctl -u sign-tool -f"
echo "    重启服务: systemctl restart sign-tool"
echo "    编辑配置: nano $INSTALL_DIR/config.toml"
echo ""
echo "  Cloudflare (可选):"
echo "    1. DNS 添加 A 记录指向本服务器 IP"
echo "    2. 开启橙色云朵 (Proxy)"
echo "    3. SSL/TLS 设置为 Full"
echo ""
