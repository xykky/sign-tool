#!/bin/bash
# ===========================================
#  Sign Tool 一键部署脚本
#  用法: sudo bash install.sh [域名]
#  示例: sudo bash install.sh sign.yourdomain.com
# ===========================================

set -e

INSTALL_DIR="/opt/sign-tool"
PORT=2087
DOMAIN="${1:-_}"
REPO_URL="https://github.com/xykky/sign-tool.git"

echo "=========================================="
echo "  Sign Tool 一键部署"
echo "=========================================="
echo ""
echo "  安装目录: $INSTALL_DIR"
echo "  后端端口: $PORT"
echo "  域名: $([ "$DOMAIN" = "_" ] && echo "(未指定，使用IP访问)" || echo "$DOMAIN")"
echo ""

# 1. 安装系统依赖
echo "[1/6] 安装系统依赖..."
if command -v apt &> /dev/null; then
    apt update -qq
    apt install -y -qq python3 python3-pip python3-venv nginx curl git
elif command -v yum &> /dev/null; then
    yum install -y python3 python3-pip nginx curl git
elif command -v dnf &> /dev/null; then
    dnf install -y python3 python3-pip nginx curl git
else
    echo "错误: 不支持的包管理器，请手动安装 python3 nginx git"
    exit 1
fi

# 2. 克隆或更新项目
echo "[2/6] 获取项目代码..."
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "  已存在 git 仓库，拉取最新代码..."
    cd "$INSTALL_DIR"
    git pull --ff-only || {
        echo "  git pull 失败，尝试 reset..."
        git fetch origin
        git reset --hard origin/master
    }
else
    if [ -d "$INSTALL_DIR" ]; then
        echo "  备份旧目录..."
        mv "$INSTALL_DIR" "${INSTALL_DIR}.bak.$(date +%s)"
    fi
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 3. 创建虚拟环境并安装依赖
echo "[3/6] 安装 Python 依赖..."
python3 -m venv .venv
source .venv/bin/activate
pip install -e . -q

# 4. 创建配置文件（如果不存在）
echo "[4/6] 检查配置文件..."
if [ ! -f config.toml ]; then
    cp config.toml.example config.toml
    echo "  已创建配置文件: $INSTALL_DIR/config.toml"
    echo "  请编辑配置文件填入账号信息"
else
    echo "  配置文件已存在，跳过"
fi

# 5. 安装 systemd 服务
echo "[5/6] 配置系统服务..."
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

systemctl daemon-reload
systemctl enable sign-tool
systemctl restart sign-tool

# 6. 配置 Nginx
echo "[6/6] 配置 Nginx..."
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
nginx -t && systemctl reload nginx

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
echo "    更新程序:   cd $INSTALL_DIR && bash update.sh"
echo "    查看状态:   systemctl status sign-tool"
echo "    查看日志:   journalctl -u sign-tool -f"
echo "    重启服务:   systemctl restart sign-tool"
echo "    编辑配置:   nano $INSTALL_DIR/config.toml"
echo ""
